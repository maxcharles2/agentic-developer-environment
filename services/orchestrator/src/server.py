"""Async gRPC server for the OrchestratorService.

Starts an asyncio-based gRPC server that exposes RunWorkflow (server-streaming),
GetWorkflowStatus, CancelWorkflow, and HealthCheck.  Every workflow event is
dual-delivered: yielded on the gRPC stream AND published to Redis pub/sub so the
Gateway can fan out to WebSocket clients.
"""

from __future__ import annotations

import asyncio
import json
import logging
import signal
import time
from typing import Any, AsyncIterator

import grpc
import redis.asyncio as aioredis
from supabase import AsyncClient, acreate_client

from src.config import settings
from src.state import create_initial_state

# ---------------------------------------------------------------------------
# Optional proto imports — generated stubs may not exist during early dev
# ---------------------------------------------------------------------------
try:
    from src.generated import orchestrator_pb2, orchestrator_pb2_grpc  # type: ignore[import]

    _PROTO_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PROTO_AVAILABLE = False
    orchestrator_pb2 = None  # type: ignore[assignment]
    orchestrator_pb2_grpc = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Lazy graph factory — falls back to placeholder when real supervisor is absent
# ---------------------------------------------------------------------------

def _get_graph() -> Any:
    try:
        from src.graphs.supervisor import build_graph  # type: ignore[import]
    except ImportError:
        from src.graph_placeholder import build_graph  # type: ignore[import]
    return build_graph()


log = logging.getLogger(__name__)

# Redis TTL for cancellation flags (10 minutes)
_CANCEL_TTL_SECONDS = 600


# ---------------------------------------------------------------------------
# Per-node state-update → WorkflowEvent translator
# ---------------------------------------------------------------------------

def _node_updates_to_event(
    node_name: str, node_updates: Any, task_id: str
) -> dict[str, Any] | None:
    """Convert a single LangGraph node-output chunk into a WorkflowEvent dict.

    Returns ``None`` for chunks that carry no meaningful information.
    """
    ts = int(time.time() * 1000)

    # LangGraph surfaces interrupt() as a special ``__interrupt__`` key
    if node_name == "__interrupt__":
        return {
            "event_type": "workflow.human_review_required",
            "step_id": None,
            "payload": {"task_id": task_id, "message": "Human review required"},
            "timestamp": ts,
        }

    if not isinstance(node_updates, dict):
        return None

    payload: dict[str, Any] = {"task_id": task_id, "node": node_name}

    if node_name == "supervisor_node":
        payload["next_agent"] = node_updates.get("next_agent", "")
        if node_updates.get("error"):
            payload["error"] = node_updates["error"]
        event_type = "workflow.routing"

    elif node_name == "planner_node":
        steps = node_updates.get("steps") or []
        payload["step_count"] = len(steps)
        event_type = "workflow.planning"

    elif node_name == "context_node":
        chunks = node_updates.get("context_chunks") or []
        payload["chunk_count"] = len(chunks)
        event_type = "workflow.context"

    elif node_name == "codegen_node":
        artifacts = node_updates.get("artifacts") or []
        payload["artifact_count"] = len(artifacts)
        if artifacts:
            last = artifacts[-1]
            payload["last_artifact"] = getattr(last, "file_path", None) or (
                last.get("file_path") if isinstance(last, dict) else None
            )
        event_type = "workflow.codegen"

    elif node_name == "executor_node":
        results = node_updates.get("execution_results") or []
        payload["result_count"] = len(results)
        if results:
            last = results[-1]
            success = getattr(last, "success", None)
            if success is None and isinstance(last, dict):
                success = last.get("success")
            payload["success"] = success
        event_type = "workflow.execution"

    elif node_name == "human_review_node":
        payload["requires_approval"] = node_updates.get("requires_approval", False)
        event_type = "workflow.human_review"

    else:
        event_type = f"workflow.node.{node_name}"

    return {
        "event_type": event_type,
        "step_id": None,
        "payload": payload,
        "timestamp": ts,
    }


# ---------------------------------------------------------------------------
# Servicer
# ---------------------------------------------------------------------------

class OrchestratorServicer:
    """Implements OrchestratorService RPCs using grpc.aio."""

    def __init__(
        self,
        supabase: AsyncClient,
        redis: aioredis.Redis,
        graph_factory: Any,
    ) -> None:
        self._supabase = supabase
        self._redis = redis
        self._graph_factory = graph_factory

    # ------------------------------------------------------------------
    # RunWorkflow — server-streaming
    # ------------------------------------------------------------------

    async def RunWorkflow(
        self,
        request: Any,
        context: grpc.aio.ServicerContext,  # type: ignore[name-defined]
    ) -> AsyncIterator[Any]:
        task_id: str = request.task_id
        project_id: str = request.project_id
        prompt: str = request.prompt
        metadata: dict[str, str] = dict(request.metadata)

        log.info("RunWorkflow task_id=%s project_id=%s", task_id, project_id)

        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

        async def _run_graph() -> None:
            """Run the LangGraph graph and push events onto the queue."""
            try:
                graph = self._graph_factory()
                state = create_initial_state(task_id, project_id, prompt)
                # thread_id drives checkpointing; extra metadata is forwarded
                # through configurable so subgraphs can inspect it.
                graph_config: dict[str, Any] = {
                    "configurable": {
                        "thread_id": task_id,
                        **metadata,
                    }
                }
                async for chunk in graph.astream(state, config=graph_config):
                    # Each chunk is keyed by node name (or "__interrupt__").
                    if isinstance(chunk, dict):
                        for node_name, node_updates in chunk.items():
                            evt = _node_updates_to_event(node_name, node_updates, task_id)
                            if evt is not None:
                                await queue.put(evt)

                # Graph finished normally — emit a completion event.
                await queue.put(
                    {
                        "event_type": "workflow.completed",
                        "step_id": None,
                        "payload": {"task_id": task_id},
                        "timestamp": int(time.time() * 1000),
                    }
                )
            except Exception as exc:  # noqa: BLE001
                log.exception("Graph error for task_id=%s: %s", task_id, exc)
                await queue.put(
                    {
                        "event_type": "workflow.error",
                        "step_id": None,
                        "payload": {"error": str(exc), "task_id": task_id},
                        "timestamp": int(time.time() * 1000),
                    }
                )
            finally:
                await queue.put(None)  # sentinel

        task = asyncio.create_task(_run_graph())

        try:
            while True:
                # Honour client cancellation
                if await context.is_active() is False:
                    task.cancel()
                    break

                # Check server-side cancellation flag
                cancel_key = f"workflow:cancel:{task_id}"
                if await self._redis.get(cancel_key):
                    log.info("Workflow cancelled via Redis: task_id=%s", task_id)
                    task.cancel()
                    break

                try:
                    event = await asyncio.wait_for(queue.get(), timeout=1.0)
                except TimeoutError:
                    continue

                if event is None:
                    break  # graph finished

                payload_str = json.dumps(event.get("payload", {}))
                proto_event = orchestrator_pb2.WorkflowEvent(
                    event_type=event.get("event_type", ""),
                    step_id=event.get("step_id") or "",
                    payload=payload_str,
                    timestamp=event.get("timestamp", int(time.time() * 1000)),
                )

                # Publish to Redis before yielding so Gateway never misses it
                await self._redis.publish(
                    f"workflow:events:{task_id}",
                    proto_event.SerializeToString(),
                )

                yield proto_event
        finally:
            task.cancel()

    # ------------------------------------------------------------------
    # GetWorkflowStatus
    # ------------------------------------------------------------------

    async def GetWorkflowStatus(self, request: Any, context: Any) -> Any:
        task_id: str = request.id
        log.debug("GetWorkflowStatus task_id=%s", task_id)

        try:
            result = (
                await self._supabase.table("workflow_checkpoints")
                .select("task_id, status, current_step, total_steps, current_agent")
                .eq("task_id", task_id)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            row = result.data[0] if result.data else {}
        except Exception as exc:  # noqa: BLE001
            log.warning("Supabase query failed for task_id=%s: %s", task_id, exc)
            row = {}

        return orchestrator_pb2.WorkflowStatus(
            task_id=row.get("task_id", task_id),
            status=row.get("status", "unknown"),
            current_step=int(row.get("current_step", 0)),
            total_steps=int(row.get("total_steps", 0)),
            current_agent=row.get("current_agent", ""),
        )

    # ------------------------------------------------------------------
    # CancelWorkflow
    # ------------------------------------------------------------------

    async def CancelWorkflow(self, request: Any, context: Any) -> Any:
        task_id: str = request.id
        log.info("CancelWorkflow task_id=%s", task_id)

        try:
            await self._redis.set(
                f"workflow:cancel:{task_id}",
                "1",
                ex=_CANCEL_TTL_SECONDS,
            )
            return orchestrator_pb2.Ack(success=True, message="Cancellation requested")
        except Exception as exc:  # noqa: BLE001
            log.error("Failed to set cancel flag for task_id=%s: %s", task_id, exc)
            return orchestrator_pb2.Ack(success=False, message=str(exc))

    # ------------------------------------------------------------------
    # HealthCheck
    # ------------------------------------------------------------------

    async def HealthCheck(self, request: Any, context: Any) -> Any:
        return orchestrator_pb2.HealthCheckResponse(status="SERVING")


# ---------------------------------------------------------------------------
# Server bootstrap
# ---------------------------------------------------------------------------

async def serve() -> None:
    """Build and start the async gRPC server; block until SIGTERM/SIGINT."""
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    supabase: AsyncClient | None = None
    if settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY:
        supabase = await acreate_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)
    else:
        log.warning("SUPABASE_URL or SUPABASE_SERVICE_KEY not set; Supabase disabled")

    redis_client: aioredis.Redis = aioredis.from_url(
        settings.REDIS_URL, decode_responses=False
    )

    servicer = OrchestratorServicer(
        supabase=supabase,  # type: ignore[arg-type]
        redis=redis_client,
        graph_factory=_get_graph,
    )

    server = grpc.aio.server()
    if _PROTO_AVAILABLE:
        orchestrator_pb2_grpc.add_OrchestratorServiceServicer_to_server(servicer, server)
    else:
        log.warning(
            "Proto stubs not found — run 'make proto' to generate them. "
            "Server will start but RPCs will not be registered."
        )

    listen_addr = f"[::]:{settings.GRPC_PORT}"
    server.add_insecure_port(listen_addr)
    await server.start()
    log.info("OrchestratorService listening on %s", listen_addr)

    stop_event = asyncio.Event()

    def _handle_signal() -> None:
        log.info("Shutdown signal received")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _handle_signal)

    await stop_event.wait()

    log.info("Graceful shutdown: draining in-flight RPCs…")
    await server.stop(grace=5)
    await redis_client.aclose()
    log.info("Server stopped")


def main() -> None:
    """Entry point invoked by the `serve` script and `python -m src.server`."""
    asyncio.run(serve())


if __name__ == "__main__":
    main()
