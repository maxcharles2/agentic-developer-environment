"""Execution subgraph — provisions a sandbox, runs the executor agent, tears down.

Graph topology::

    START → setup_sandbox → execute → teardown_sandbox → END
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, START, StateGraph

from src.state.workflow import WorkflowState

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


async def _setup_sandbox_node(state: WorkflowState) -> dict[str, Any]:
    """Provision a sandbox via gRPC and store the sandbox_id in the executor module.

    The runtime is detected from the artifacts already in state so the sandbox
    is created with the correct language environment before the agent runs.
    Returns an empty dict — sandbox_id is a transient field kept outside state.
    """
    from src.agents import executor as _executor_module
    from src.agents.executor import _detect_runtime

    artifacts = state.get("artifacts") or []
    runtime = _detect_runtime(artifacts)

    channel = _executor_module._get_grpc_channel()
    if channel is None:
        log.warning("setup_sandbox: gRPC channel unavailable — executor will run without sandbox")
        return {}

    try:
        from src.proto.sandbox_pb2 import SandboxConfig  # type: ignore[import]
        from src.proto.sandbox_pb2_grpc import SandboxServiceStub  # type: ignore[import]

        stub = SandboxServiceStub(channel)
        config = SandboxConfig(
            runtime=runtime,
            cpu_cores=1,
            memory_mb=512,
            timeout_s=60,
        )
        info = stub.CreateSandbox(config, timeout=30)
        _executor_module._current_sandbox_id = info.sandbox_id
        log.info(
            "setup_sandbox: created sandbox_id=%s runtime=%s for task_id=%s",
            info.sandbox_id,
            runtime,
            state.get("task_id"),
        )
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "setup_sandbox: CreateSandbox failed for task_id=%s (%s) — continuing without sandbox",
            state.get("task_id"),
            exc,
        )

    return {}


async def _execute_node(state: WorkflowState) -> dict[str, Any]:
    """Delegate to the executor agent."""
    from src.agents.executor import run_executor_agent  # local import for loose coupling

    return await run_executor_agent(state)


async def _teardown_sandbox_node(state: WorkflowState) -> dict[str, Any]:
    """Destroy the sandbox and clear the module-level sandbox_id.

    Wrapped in a broad try/except so a teardown failure never aborts the
    workflow — the execution results are already collected at this point.
    """
    from src.agents import executor as _executor_module

    sandbox_id = _executor_module._current_sandbox_id
    _executor_module._current_sandbox_id = ""

    if not sandbox_id:
        return {}

    channel = _executor_module._get_grpc_channel()
    if channel is None:
        return {}

    try:
        from src.proto.sandbox_pb2 import SandboxId  # type: ignore[import]
        from src.proto.sandbox_pb2_grpc import SandboxServiceStub  # type: ignore[import]

        stub = SandboxServiceStub(channel)
        stub.DestroySandbox(SandboxId(id=sandbox_id), timeout=15)
        log.info(
            "teardown_sandbox: destroyed sandbox_id=%s for task_id=%s",
            sandbox_id,
            state.get("task_id"),
        )
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "teardown_sandbox: DestroySandbox failed for sandbox_id=%s (%s) — ignoring",
            sandbox_id,
            exc,
        )

    return {}


# ---------------------------------------------------------------------------
# Subgraph factory
# ---------------------------------------------------------------------------


def create_execution_subgraph() -> Any:
    """Build and compile the execution subgraph."""
    graph = StateGraph(WorkflowState)

    graph.add_node("setup_sandbox", _setup_sandbox_node)
    graph.add_node("execute", _execute_node)
    graph.add_node("teardown_sandbox", _teardown_sandbox_node)

    graph.add_edge(START, "setup_sandbox")
    graph.add_edge("setup_sandbox", "execute")
    graph.add_edge("execute", "teardown_sandbox")
    graph.add_edge("teardown_sandbox", END)

    return graph.compile()


# ---------------------------------------------------------------------------
# Public entry point (imported by supervisor.py)
# ---------------------------------------------------------------------------


async def run_executor(state: WorkflowState) -> dict[str, Any]:
    """Invoke the execution subgraph and return the relevant state fields.

    This is the function imported by ``supervisor.py``'s ``executor_node``.
    It propagates ``execution_results`` and optionally ``error`` back to the
    parent workflow state.
    """
    subgraph = create_execution_subgraph()
    result: WorkflowState = await subgraph.ainvoke(state)

    update: dict[str, Any] = {
        "execution_results": result.get("execution_results") or [],
    }

    error = result.get("error")
    if error is not None:
        update["error"] = error

    log.info(
        "Execution subgraph finished: results=%d error=%s task_id=%s",
        len(update["execution_results"]),
        update.get("error"),
        state.get("task_id"),
    )
    return update
