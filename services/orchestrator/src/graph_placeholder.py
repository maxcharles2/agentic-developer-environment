"""Minimal placeholder LangGraph graph used before the real supervisor is built.

The graph accepts WorkflowState, immediately emits a single "workflow.placeholder"
event, and terminates.  server.py imports build_graph() via a lazy factory; if this
module is unavailable the factory falls back to a no-op callable.
"""

from __future__ import annotations

import time
from typing import Annotated, Any
from typing_extensions import TypedDict

from langgraph.graph import END, START, StateGraph


def _append(left: list[Any], right: list[Any]) -> list[Any]:
    """Reducer: append new events to the existing list."""
    return left + right


class WorkflowState(TypedDict):
    task_id: str
    project_id: str
    prompt: str
    # Accumulated events — uses append reducer so concurrent nodes are safe.
    events: Annotated[list[dict[str, Any]], _append]
    status: str
    metadata: dict[str, Any]


def placeholder_node(state: WorkflowState) -> dict[str, Any]:
    """Single graph node: emit one placeholder event and mark the workflow done."""
    event: dict[str, Any] = {
        "event_type": "workflow.placeholder",
        "step_id": None,
        "payload": {
            "message": "Orchestrator is online. Real supervisor graph not yet installed.",
            "task_id": state["task_id"],
        },
        "timestamp": int(time.time() * 1000),
    }
    return {
        "events": [event],
        "status": "completed",
    }


def build_graph() -> Any:
    """Return a compiled LangGraph graph that streams a single placeholder event."""
    builder: StateGraph = StateGraph(WorkflowState)
    builder.add_node("placeholder", placeholder_node)
    builder.add_edge(START, "placeholder")
    builder.add_edge("placeholder", END)
    return builder.compile()
