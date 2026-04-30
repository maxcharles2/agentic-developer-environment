"""Executor agent — runs generated artifacts inside a sandbox and reports results.

The agent runs a manual ReAct tool-calling loop (max 10 iterations) using
two tools:
- ``run_command``: executes a shell command inside the sandbox via gRPC.
- ``read_file``: reads an existing file (imported from the context agent).

Execution results are collected into ``ExecutionResult`` objects and persisted
to the Supabase ``execution_results`` table (best-effort).

The module exposes ``_current_sandbox_id`` which is written by the execution
subgraph's ``setup_sandbox`` node before invoking this agent, and cleared by
``teardown_sandbox`` afterwards.  This avoids extending ``WorkflowState`` with
a transient field that only lives for one subgraph invocation.
"""

from __future__ import annotations

import functools
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage  # type: ignore[import]
from langchain_core.tools import tool  # type: ignore[import]

from ade_types.artifact import ExecutionResult
from src.agents.context import read_file
from src.config import settings
from src.state.workflow import WorkflowState

log = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

MAX_TOOL_CALLS = 10

# ---------------------------------------------------------------------------
# Module-level sandbox state (set/cleared by the execution subgraph)
# ---------------------------------------------------------------------------

# Written by graphs/execution.py _setup_sandbox_node before calling run_executor_agent.
# Cleared by _teardown_sandbox_node afterwards.
_current_sandbox_id: str = ""

# Accumulated raw results during a single ReAct loop invocation.
_execution_results: list[dict[str, Any]] = []

# ---------------------------------------------------------------------------
# Module-level gRPC channel cache (lazy, reused across calls)
# ---------------------------------------------------------------------------

_grpc_channel: Any = None


def _get_grpc_channel() -> Any:
    """Return a cached synchronous gRPC channel to the SandboxService."""
    global _grpc_channel  # noqa: PLW0603
    if _grpc_channel is None:
        try:
            import grpc  # type: ignore[import]

            _grpc_channel = grpc.insecure_channel(settings.SANDBOX_GRPC_URL)
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not create gRPC channel to SandboxService (%s)", exc)
    return _grpc_channel


# ---------------------------------------------------------------------------
# Runtime detection helpers
# ---------------------------------------------------------------------------

_EXTENSION_TO_RUNTIME: dict[str, str] = {
    ".py": "python3.12",
    ".ts": "node22",
    ".tsx": "node22",
    ".js": "node22",
    ".jsx": "node22",
    ".mjs": "node22",
    ".cjs": "node22",
}

_DEFAULT_RUNTIME = "python3.12"


def _detect_runtime(artifacts: list[Any]) -> str:
    """Infer the sandbox runtime from the file extensions of the given artifacts."""
    for artifact in artifacts:
        file_path = getattr(artifact, "file_path", None) or (
            artifact.get("file_path") if isinstance(artifact, dict) else None
        )
        if not file_path:
            continue
        suffix = Path(file_path).suffix.lower()
        runtime = _EXTENSION_TO_RUNTIME.get(suffix)
        if runtime:
            return runtime
    return _DEFAULT_RUNTIME


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------


@tool
def run_command(command: str, runtime: str = "python3.12") -> str:
    """Execute a shell command inside the sandbox via gRPC.

    Args:
        command: The shell command to run (e.g. ``pytest tests/`` or ``node index.js``).
        runtime: Sandbox runtime identifier.  Use ``python3.12`` for Python
            files and ``node22`` for TypeScript/JavaScript files.

    Returns:
        A formatted string containing stdout, stderr, exit code, and duration.
        Returns an error message if the sandbox is unreachable or no sandbox
        has been provisioned for this session.
    """
    if not _current_sandbox_id:
        return "Error: no active sandbox — run_command cannot execute outside a sandbox session"

    channel = _get_grpc_channel()
    if channel is None:
        return "Error: gRPC channel to SandboxService is unavailable"

    try:
        from src.proto.sandbox_pb2 import ExecutionRequest  # type: ignore[import]
        from src.proto.sandbox_pb2_grpc import SandboxServiceStub  # type: ignore[import]

        stub = SandboxServiceStub(channel)
        request = ExecutionRequest(
            sandbox_id=_current_sandbox_id,
            command=command,
        )

        t0 = time.monotonic()
        response = stub.Execute(request, timeout=65)
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        _execution_results.append(
            {
                "command": command,
                "stdout": response.stdout,
                "stderr": response.stderr,
                "exit_code": response.exit_code,
                "duration_ms": response.duration_ms or elapsed_ms,
                "sandbox_id": _current_sandbox_id,
            }
        )

        lines = [
            f"exit_code: {response.exit_code}",
            f"duration_ms: {response.duration_ms or elapsed_ms}",
        ]
        if response.stdout:
            lines.append(f"stdout:\n{response.stdout}")
        if response.stderr:
            lines.append(f"stderr:\n{response.stderr}")
        return "\n".join(lines)

    except Exception as exc:  # noqa: BLE001
        log.warning("run_command failed for command=%r: %s", command, exc)
        return f"Error executing command '{command}': {exc}"


# ---------------------------------------------------------------------------
# LLM factory
# ---------------------------------------------------------------------------


def _get_executor_llm() -> Any:
    """Return a ChatModel bound to the executor tools."""
    model = settings.WORKER_MODEL
    if "claude" in model.lower() or "anthropic" in model.lower():
        from langchain_anthropic import ChatAnthropic  # type: ignore[import]

        llm = ChatAnthropic(model=model, api_key=settings.ANTHROPIC_API_KEY)
    else:
        from langchain_openai import ChatOpenAI  # type: ignore[import]

        llm = ChatOpenAI(model=model, api_key=settings.OPENAI_API_KEY)
    return llm.bind_tools([run_command, read_file])


# ---------------------------------------------------------------------------
# System prompt loader
# ---------------------------------------------------------------------------


@functools.lru_cache(maxsize=1)
def _load_system_prompt() -> str:
    """Read and cache the executor agent system prompt from ``prompts/executor.md``."""
    prompt_path = _PROMPTS_DIR / "executor.md"
    return prompt_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Tool executor
# ---------------------------------------------------------------------------


async def _execute_tool_call(tool_name: str, tool_args: dict) -> str:
    """Dispatch an executor tool call by name and return its string result."""
    if tool_name == "run_command":
        return run_command.invoke(tool_args)
    elif tool_name == "read_file":
        return read_file.invoke(tool_args)
    else:
        return f"Unknown tool: {tool_name}"


# ---------------------------------------------------------------------------
# Core agent function
# ---------------------------------------------------------------------------


async def run_executor_agent(state: WorkflowState) -> dict[str, Any]:
    """Run generated artifacts inside the sandbox and report execution results.

    Runs a manual ReAct tool-calling loop (max ``MAX_TOOL_CALLS`` iterations).
    All commands executed by the LLM are collected into ``ExecutionResult``
    objects, persisted to Supabase, and returned as ``execution_results``
    appended to state.

    Returns:
        A partial state update ``{"execution_results": [ExecutionResult, ...]}``.
    """
    global _execution_results  # noqa: PLW0603
    _execution_results = []

    system_prompt = _load_system_prompt()

    steps = state.get("steps") or []
    idx = state.get("current_step_index", 0)
    current_step = steps[idx] if steps and 0 <= idx < len(steps) else None

    step_description = ""
    if current_step is not None:
        step_description = getattr(current_step, "description", None) or (
            current_step.get("description") if isinstance(current_step, dict) else ""
        ) or ""

    artifacts = state.get("artifacts") or []
    artifact_paths = [
        getattr(a, "file_path", None) or (a.get("file_path") if isinstance(a, dict) else None)
        for a in artifacts
    ]
    artifact_paths = [p for p in artifact_paths if p]

    detected_runtime = _detect_runtime(artifacts)

    user_content_parts = [f"Task: {state['prompt']}"]
    if step_description:
        user_content_parts.append(f"Current step: {step_description}")
    if artifact_paths:
        user_content_parts.append(
            "Generated artifact paths:\n" + "\n".join(f"- {p}" for p in artifact_paths)
        )
    user_content_parts.append(
        f"Detected runtime: {detected_runtime}\n"
        "Inspect the artifacts, determine the appropriate test commands, "
        "and run them using run_command. Report the full results."
    )

    user_message = "\n\n".join(user_content_parts)

    messages: list[BaseMessage] = [
        {"role": "system", "content": system_prompt},  # type: ignore[arg-type]
        {"role": "user", "content": user_message},  # type: ignore[arg-type]
    ]

    llm = _get_executor_llm()
    tool_calls_made = 0

    for iteration in range(MAX_TOOL_CALLS):
        response: AIMessage = await llm.ainvoke(messages)
        messages.append(response)

        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            log.info(
                "Executor agent finished after %d tool call(s) for task_id=%s",
                tool_calls_made,
                state["task_id"],
            )
            break

        for tc in tool_calls:
            if tool_calls_made >= MAX_TOOL_CALLS:
                log.warning(
                    "Executor agent reached MAX_TOOL_CALLS=%d — stopping early (task_id=%s)",
                    MAX_TOOL_CALLS,
                    state["task_id"],
                )
                break

            tool_name = tc["name"]
            tool_args = tc.get("args") or {}
            tool_call_id = tc.get("id") or f"call_{tool_calls_made}"

            log.debug(
                "Executor agent: invoking %s(args=%s) [call %d/%d]",
                tool_name,
                tool_args,
                tool_calls_made + 1,
                MAX_TOOL_CALLS,
            )

            tool_result = await _execute_tool_call(tool_name, tool_args)
            tool_calls_made += 1

            messages.append(
                ToolMessage(content=tool_result, tool_call_id=tool_call_id)
            )

        if tool_calls_made >= MAX_TOOL_CALLS:
            log.info(
                "Executor agent: MAX_TOOL_CALLS=%d reached at iteration %d (task_id=%s)",
                MAX_TOOL_CALLS,
                iteration + 1,
                state["task_id"],
            )
            break
    else:
        log.warning(
            "Executor agent loop exhausted without LLM finishing (task_id=%s)",
            state["task_id"],
        )

    task_uuid = UUID(state["task_id"])
    run_uuid = uuid4()
    now = datetime.now(timezone.utc)

    results: list[ExecutionResult] = [
        ExecutionResult(
            id=uuid4(),
            run_id=run_uuid,
            task_id=task_uuid,
            command=entry["command"],
            stdout=entry["stdout"],
            stderr=entry["stderr"],
            exit_code=entry["exit_code"],
            duration_ms=entry["duration_ms"],
            sandbox_id=entry["sandbox_id"],
            created_at=now,
        )
        for entry in _execution_results
    ]

    _persist_results(results)

    log.info(
        "Executor agent returning %d result(s) for task_id=%s",
        len(results),
        state["task_id"],
    )
    return {"execution_results": results}


# ---------------------------------------------------------------------------
# Supabase persistence (best-effort)
# ---------------------------------------------------------------------------


def _persist_results(results: list[ExecutionResult]) -> None:
    """Batch-insert execution results into ``execution_results``.  Non-fatal on failure."""
    if not results:
        return

    if not (settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY):
        log.warning("Supabase not configured — skipping execution result persistence")
        return

    try:
        from supabase import create_client  # type: ignore[import]

        client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)
        rows = [
            {
                "id": str(r.id),
                "run_id": str(r.run_id),
                "task_id": str(r.task_id),
                "command": r.command,
                "stdout": r.stdout,
                "stderr": r.stderr,
                "exit_code": r.exit_code,
                "duration_ms": r.duration_ms,
                "sandbox_id": r.sandbox_id,
                "created_at": r.created_at.isoformat(),
            }
            for r in results
        ]
        client.table("execution_results").insert(rows).execute()
        log.info("Persisted %d execution result(s) to Supabase", len(results))
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not persist execution results to Supabase (%s) — continuing", exc)
