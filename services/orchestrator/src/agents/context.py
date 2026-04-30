"""Context agent — retrieves relevant codebase snippets for the current step.

The agent runs a manual tool-calling loop (max 5 iterations) using two tools:
- ``search_codebase``: semantic search via the ContextService gRPC API.
- ``read_file``: reads a specific file from the project repository.

Both tools have graceful fallbacks for the pre-M22/M23 placeholder period when
the gRPC stub and file_ops module are not yet wired up.
"""

from __future__ import annotations

import functools
import logging
import os
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage  # type: ignore[import]
from langchain_core.tools import tool  # type: ignore[import]

from src.config import settings
from src.state.workflow import WorkflowState

log = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

MAX_TOOL_CALLS = 5

# ---------------------------------------------------------------------------
# Module-level gRPC channel cache (lazy, reused across calls)
# ---------------------------------------------------------------------------

_grpc_channel: Any = None


def _get_grpc_channel() -> Any:
    """Return a cached async gRPC channel to the ContextService."""
    global _grpc_channel  # noqa: PLW0603
    if _grpc_channel is None:
        try:
            import grpc  # type: ignore[import]

            _grpc_channel = grpc.aio.insecure_channel(settings.CONTEXT_GRPC_URL)
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not create gRPC channel (%s) — context gRPC unavailable", exc)
    return _grpc_channel


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------


@tool
async def search_codebase(query: str, top_k: int = 10) -> list[dict]:
    """Search the project codebase semantically and return the most relevant chunks.

    Args:
        query: Natural-language search query.
        top_k: Maximum number of results to return (default 10).

    Returns:
        List of dicts with keys ``file_path``, ``content``, and ``score``.
        Returns an empty list when the ContextService is unreachable.
    """
    try:
        import grpc  # type: ignore[import]

        channel = _get_grpc_channel()
        if channel is None:
            log.warning("search_codebase: no gRPC channel — returning empty results")
            return []

        # Placeholder stub import — will succeed once M23 is implemented.
        from src.proto.context_pb2 import RetrieveContextRequest  # type: ignore[import]
        from src.proto.context_pb2_grpc import ContextServiceStub  # type: ignore[import]

        stub = ContextServiceStub(channel)
        request = RetrieveContextRequest(query=query, top_k=top_k)
        response = await stub.RetrieveContext(request, timeout=10)

        return [
            {
                "file_path": chunk.file_path,
                "content": chunk.content,
                "score": chunk.score,
            }
            for chunk in response.chunks
        ]
    except Exception as exc:  # noqa: BLE001
        log.warning("search_codebase failed (%s) — returning empty results", exc)
        return []


@tool
def read_file(file_path: str) -> str:
    """Read the contents of a file from the project repository.

    Args:
        file_path: Relative or absolute path to the file.

    Returns:
        File contents as a string, or an error message if the file cannot be read.
    """
    try:
        # Resolve to absolute path and guard against traversal attacks.
        resolved = Path(file_path).resolve()
        workspace_root = Path(os.environ.get("WORKSPACE_ROOT", "/workspace")).resolve()

        # Allow either rooted inside the workspace or a relative path that stays
        # within the workspace after resolution.
        if not str(resolved).startswith(str(workspace_root)):
            # Fallback: try interpreting as workspace-relative
            candidate = (workspace_root / file_path).resolve()
            if not str(candidate).startswith(str(workspace_root)):
                return f"Error: path traversal detected for '{file_path}'"
            resolved = candidate

        if not resolved.exists():
            return f"Error: file not found — '{file_path}'"

        if not resolved.is_file():
            return f"Error: path is not a regular file — '{file_path}'"

        return resolved.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        log.warning("read_file failed for '%s': %s", file_path, exc)
        return f"Error reading file '{file_path}': {exc}"


# ---------------------------------------------------------------------------
# LLM factory
# ---------------------------------------------------------------------------


def _get_context_llm() -> Any:
    """Return a ChatModel bound to the context tools."""
    model = settings.WORKER_MODEL
    if "claude" in model.lower() or "anthropic" in model.lower():
        from langchain_anthropic import ChatAnthropic  # type: ignore[import]

        llm = ChatAnthropic(model=model, api_key=settings.ANTHROPIC_API_KEY)
    else:
        from langchain_openai import ChatOpenAI  # type: ignore[import]

        llm = ChatOpenAI(model=model, api_key=settings.OPENAI_API_KEY)
    return llm.bind_tools([search_codebase, read_file])


# ---------------------------------------------------------------------------
# System prompt loader
# ---------------------------------------------------------------------------


@functools.lru_cache(maxsize=1)
def _load_system_prompt() -> str:
    """Read and cache the context agent system prompt from ``prompts/context.md``."""
    prompt_path = _PROMPTS_DIR / "context.md"
    return prompt_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Tool executor
# ---------------------------------------------------------------------------


async def _execute_tool_call(tool_name: str, tool_args: dict) -> str:
    """Dispatch a tool call by name and return its string result."""
    if tool_name == "search_codebase":
        result = await search_codebase.ainvoke(tool_args)
        if not result:
            return "No results found."
        lines = [
            f"[{i + 1}] {chunk['file_path']} (score={chunk.get('score', 'n/a')})\n{chunk['content']}"
            for i, chunk in enumerate(result)
        ]
        return "\n\n".join(lines)
    elif tool_name == "read_file":
        return read_file.invoke(tool_args)
    else:
        return f"Unknown tool: {tool_name}"


# ---------------------------------------------------------------------------
# Core agent function
# ---------------------------------------------------------------------------


async def run_context(state: WorkflowState) -> dict[str, Any]:
    """Retrieve relevant codebase context for the current workflow step.

    Runs a manual tool-calling loop (max ``MAX_TOOL_CALLS`` iterations) so that
    costs and latency stay bounded.  All retrieved content is collected and
    returned as ``context_chunks`` which are appended to the workflow state via
    the ``operator.add`` reducer.

    Returns:
        A partial state update ``{"context_chunks": [str, ...]}``.
    """
    system_prompt = _load_system_prompt()

    # Build the initial user message describing what context is needed.
    steps = state.get("steps") or []
    idx = state.get("current_step_index", 0)
    current_step = steps[idx] if steps and 0 <= idx < len(steps) else None

    step_description = ""
    if current_step is not None:
        step_description = getattr(current_step, "description", None) or (
            current_step.get("description") if isinstance(current_step, dict) else ""
        ) or ""

    user_content_parts = [f"Task: {state['prompt']}"]
    if step_description:
        user_content_parts.append(f"Current step: {step_description}")
    user_content_parts.append(
        "Retrieve the codebase context most relevant to implementing this step."
    )
    user_message = "\n\n".join(user_content_parts)

    messages: list[BaseMessage] = [
        {"role": "system", "content": system_prompt},  # type: ignore[arg-type]
        {"role": "user", "content": user_message},  # type: ignore[arg-type]
    ]

    llm = _get_context_llm()
    collected_chunks: list[str] = []
    tool_calls_made = 0

    for iteration in range(MAX_TOOL_CALLS):
        response: AIMessage = await llm.ainvoke(messages)
        messages.append(response)

        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            # LLM has finished — no more tool use requested.
            log.info(
                "Context agent finished after %d tool call(s) for task_id=%s",
                tool_calls_made,
                state["task_id"],
            )
            break

        for tc in tool_calls:
            if tool_calls_made >= MAX_TOOL_CALLS:
                log.warning(
                    "Context agent reached MAX_TOOL_CALLS=%d — stopping early (task_id=%s)",
                    MAX_TOOL_CALLS,
                    state["task_id"],
                )
                break

            tool_name = tc["name"]
            tool_args = tc.get("args") or {}
            tool_call_id = tc.get("id") or f"call_{tool_calls_made}"

            log.debug(
                "Context agent: invoking %s(args=%s) [call %d/%d]",
                tool_name,
                tool_args,
                tool_calls_made + 1,
                MAX_TOOL_CALLS,
            )

            tool_result = await _execute_tool_call(tool_name, tool_args)
            tool_calls_made += 1

            # Accumulate non-empty results as context chunks.
            if tool_result and not tool_result.startswith("Error") and tool_result != "No results found.":
                collected_chunks.append(tool_result)

            messages.append(
                ToolMessage(content=tool_result, tool_call_id=tool_call_id)
            )

        if tool_calls_made >= MAX_TOOL_CALLS:
            log.info(
                "Context agent: MAX_TOOL_CALLS=%d reached at iteration %d (task_id=%s)",
                MAX_TOOL_CALLS,
                iteration + 1,
                state["task_id"],
            )
            break
    else:
        log.warning(
            "Context agent loop exhausted without LLM finishing (task_id=%s)",
            state["task_id"],
        )

    log.info(
        "Context agent returning %d chunk(s) for task_id=%s",
        len(collected_chunks),
        state["task_id"],
    )
    return {"context_chunks": collected_chunks}
