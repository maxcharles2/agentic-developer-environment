"""Supabase-backed LangGraph checkpoint saver for the ADE orchestrator.

The ``SupabaseCheckpointer`` persists every LangGraph node transition into the
``workflow_checkpoints`` table and stores pending channel writes in the
companion ``checkpoint_writes`` table (mirrors the official
``langgraph-checkpoint-postgres`` design).

Serialization is handled by :class:`ADEJsonEncoder`, which teaches
``json.JSONEncoder`` how to deal with the three non-native types that appear
throughout ``WorkflowState``:

* :class:`uuid.UUID`            → ``str``
* :class:`datetime.datetime`   → ISO-8601 string via ``.isoformat()``
* :class:`pydantic.BaseModel`  → plain ``dict`` via ``.model_dump()``
"""

from __future__ import annotations

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, AsyncIterator, Iterator, Sequence
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
from pydantic import BaseModel
from supabase import AsyncClient, create_async_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


class ADEJsonEncoder(json.JSONEncoder):
    """JSON encoder that handles the non-native types present in WorkflowState.

    Handles, in priority order:
    - :class:`uuid.UUID`          → ``str`` representation
    - :class:`datetime.datetime`  → ISO-8601 string (timezone-aware safe)
    - :class:`pydantic.BaseModel` → ``dict`` via ``.model_dump()``

    Any other non-serializable type falls through to the standard
    ``JSONEncoder.default``, which raises ``TypeError``.
    """

    def default(self, obj: Any) -> Any:
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, BaseModel):
            # model_dump() recursively converts nested models to plain dicts,
            # but nested UUIDs / datetimes still need encoder passes, so we
            # round-trip through json.loads(json.dumps(..., cls=ADEJsonEncoder)).
            # To avoid infinite recursion we use the dict representation and
            # let the encoder handle its leaf values on the next pass.
            return obj.model_dump()
        return super().default(obj)


def _dumps(obj: Any) -> str:
    """Serialize ``obj`` to a JSON string using :class:`ADEJsonEncoder`."""
    return json.dumps(obj, cls=ADEJsonEncoder)


def _to_jsonb(obj: Any) -> Any:
    """Round-trip through JSON so that the result is safe to pass to Supabase
    as a JSONB value (plain Python dict/list, all leaves are JSON-native)."""
    return json.loads(_dumps(obj))


def _deserialize_checkpoint(data: str | dict[str, Any]) -> Checkpoint:
    """Reconstruct a :class:`Checkpoint` from its stored representation.

    Supabase returns JSONB columns as plain Python dicts; raw strings are
    also accepted for forward-compatibility.
    """
    if isinstance(data, str):
        return json.loads(data)
    # Already a dict from Supabase JSONB column — return as-is.
    return data  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Configurable helpers
# ---------------------------------------------------------------------------


def _get_configurable(config: RunnableConfig) -> dict[str, Any]:
    return config.get("configurable") or {}


# ---------------------------------------------------------------------------
# Checkpointer
# ---------------------------------------------------------------------------


class SupabaseCheckpointer(BaseCheckpointSaver):
    """LangGraph :class:`BaseCheckpointSaver` backed by Supabase.

    Checkpoints are stored in ``workflow_checkpoints``; pending channel writes
    go into ``checkpoint_writes`` (FK → ``workflow_checkpoints.id`` with
    ``ON DELETE CASCADE``).

    Usage::

        checkpointer = SupabaseCheckpointer(
            supabase_url=settings.supabase_url,
            supabase_key=settings.supabase_service_key,
        )
        graph = build_graph().compile(checkpointer=checkpointer)
        async for event in graph.astream(state, config):
            ...
    """

    def __init__(self, supabase_url: str, supabase_key: str) -> None:
        super().__init__()
        self._url = supabase_url
        self._key = supabase_key
        self._client: AsyncClient | None = None

    # ------------------------------------------------------------------
    # Supabase client (lazy singleton)
    # ------------------------------------------------------------------

    async def _get_client(self) -> AsyncClient:
        if self._client is None:
            self._client = await create_async_client(self._url, self._key)
        return self._client

    # ------------------------------------------------------------------
    # Async methods — real Supabase I/O
    # ------------------------------------------------------------------

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: dict[str, Any],
    ) -> RunnableConfig:
        """Persist a checkpoint and return an updated config carrying the new id."""
        cfg = _get_configurable(config)
        thread_id: str = cfg["thread_id"]
        checkpoint_ns: str = cfg.get("checkpoint_ns", "")
        task_id: str = cfg.get("task_id", "")

        client = await self._get_client()

        # Determine next step_number (MAX + 1 per thread/namespace).
        step_result = (
            await client.table("workflow_checkpoints")
            .select("step_number")
            .eq("thread_id", thread_id)
            .eq("checkpoint_ns", checkpoint_ns)
            .order("step_number", desc=True)
            .limit(1)
            .execute()
        )
        prev_step: int = step_result.data[0]["step_number"] if step_result.data else -1
        step_number = prev_step + 1

        row = {
            "task_id": task_id,
            "thread_id": thread_id,
            "checkpoint_ns": checkpoint_ns,
            "node_name": metadata.get("source", ""),
            "state_snapshot": _to_jsonb(checkpoint),
            "metadata": _to_jsonb(metadata),
            "new_versions": _to_jsonb(new_versions),
            "step_number": step_number,
        }

        insert_result = await client.table("workflow_checkpoints").insert(row).execute()
        inserted_id: str = insert_result.data[0]["id"]

        return {
            **config,
            "configurable": {
                **cfg,
                "checkpoint_id": inserted_id,
                "checkpoint_ns": checkpoint_ns,
            },
        }

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        """Fetch the latest (or a specific) checkpoint for ``thread_id``."""
        cfg = _get_configurable(config)
        thread_id: str = cfg["thread_id"]
        checkpoint_ns: str = cfg.get("checkpoint_ns", "")
        checkpoint_id: str | None = cfg.get("checkpoint_id")

        client = await self._get_client()

        query = (
            client.table("workflow_checkpoints")
            .select("*")
            .eq("thread_id", thread_id)
            .eq("checkpoint_ns", checkpoint_ns)
        )
        if checkpoint_id:
            query = query.eq("id", checkpoint_id)
        else:
            query = query.order("step_number", desc=True).limit(1)

        result = await query.execute()
        if not result.data:
            return None

        row = result.data[0]
        checkpoint = _deserialize_checkpoint(row["state_snapshot"])
        metadata: CheckpointMetadata = row.get("metadata") or {}

        # Load pending writes for this checkpoint.
        writes_result = (
            await client.table("checkpoint_writes")
            .select("*")
            .eq("checkpoint_id", row["id"])
            .execute()
        )
        pending_writes: list[tuple[str, str, Any]] = [
            (w["task_id"], w["channel"], w["value"])
            for w in writes_result.data
        ]

        # Derive parent config from the previous step number.
        parent_config: RunnableConfig | None = None
        if row["step_number"] > 0:
            parent_result = (
                await client.table("workflow_checkpoints")
                .select("id")
                .eq("thread_id", thread_id)
                .eq("checkpoint_ns", checkpoint_ns)
                .eq("step_number", row["step_number"] - 1)
                .execute()
            )
            if parent_result.data:
                parent_config = {
                    **config,
                    "configurable": {
                        **cfg,
                        "checkpoint_id": parent_result.data[0]["id"],
                        "checkpoint_ns": checkpoint_ns,
                    },
                }

        checkpoint_config: RunnableConfig = {
            **config,
            "configurable": {
                **cfg,
                "checkpoint_id": row["id"],
                "checkpoint_ns": checkpoint_ns,
            },
        }

        return CheckpointTuple(
            config=checkpoint_config,
            checkpoint=checkpoint,
            metadata=metadata,
            parent_config=parent_config,
            pending_writes=pending_writes,
        )

    async def alist(
        self,
        config: RunnableConfig,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        """Yield checkpoints for ``thread_id`` ordered by step_number DESC."""
        cfg = _get_configurable(config)
        thread_id: str = cfg["thread_id"]
        checkpoint_ns: str = cfg.get("checkpoint_ns", "")

        client = await self._get_client()

        query = (
            client.table("workflow_checkpoints")
            .select("*")
            .eq("thread_id", thread_id)
            .eq("checkpoint_ns", checkpoint_ns)
            .order("step_number", desc=True)
        )

        if before:
            before_cfg = _get_configurable(before)
            if "checkpoint_id" in before_cfg:
                before_step_result = (
                    await client.table("workflow_checkpoints")
                    .select("step_number")
                    .eq("id", before_cfg["checkpoint_id"])
                    .execute()
                )
                if before_step_result.data:
                    query = query.lt("step_number", before_step_result.data[0]["step_number"])

        if limit is not None:
            query = query.limit(limit)

        result = await query.execute()

        for row in result.data:
            checkpoint = _deserialize_checkpoint(row["state_snapshot"])
            metadata: CheckpointMetadata = row.get("metadata") or {}

            writes_result = (
                await client.table("checkpoint_writes")
                .select("*")
                .eq("checkpoint_id", row["id"])
                .execute()
            )
            pending_writes: list[tuple[str, str, Any]] = [
                (w["task_id"], w["channel"], w["value"])
                for w in writes_result.data
            ]

            yield CheckpointTuple(
                config={
                    **config,
                    "configurable": {
                        **cfg,
                        "checkpoint_id": row["id"],
                        "checkpoint_ns": checkpoint_ns,
                    },
                },
                checkpoint=checkpoint,
                metadata=metadata,
                parent_config=None,
                pending_writes=pending_writes,
            )

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        """Append pending channel writes for a checkpoint (pure-append, no contention)."""
        cfg = _get_configurable(config)
        checkpoint_id: str | None = cfg.get("checkpoint_id")
        if not checkpoint_id:
            logger.warning(
                "aput_writes called without checkpoint_id in config — skipping"
            )
            return

        client = await self._get_client()

        rows = [
            {
                "checkpoint_id": checkpoint_id,
                "task_id": task_id,
                "task_path": task_path,
                "channel": channel,
                "value": _to_jsonb(value),
            }
            for channel, value in writes
        ]
        if rows:
            await client.table("checkpoint_writes").insert(rows).execute()

    # ------------------------------------------------------------------
    # Sync methods — delegate to async
    # ------------------------------------------------------------------

    @staticmethod
    def _run_async(coro: Any) -> Any:
        """Run an async coroutine from a synchronous context.

        When an event loop is already running (e.g. inside Jupyter or a
        running asyncio application) we spin up a worker thread with its own
        loop to avoid "cannot run nested event loops" errors.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()

        return asyncio.run(coro)

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: dict[str, Any],
    ) -> RunnableConfig:
        return self._run_async(self.aput(config, checkpoint, metadata, new_versions))

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        return self._run_async(self.aget_tuple(config))

    def list(
        self,
        config: RunnableConfig,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        async def _collect() -> list[CheckpointTuple]:
            return [
                item
                async for item in self.alist(
                    config, filter=filter, before=before, limit=limit
                )
            ]

        return iter(self._run_async(_collect()))

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        self._run_async(self.aput_writes(config, writes, task_id, task_path))
