"""Planning subgraph for the ADE orchestrator.

A single-node subgraph that delegates to the planner agent and returns the
resulting TaskSteps as a WorkflowState update.

Graph topology::

    START → plan → END
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, START, StateGraph

from src.state.workflow import WorkflowState

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------


async def _plan_node(state: WorkflowState) -> dict[str, Any]:
    """Thin wrapper that calls the planner agent."""
    from src.agents.planner import run_planner  # local import for loose coupling

    return await run_planner(state)


# ---------------------------------------------------------------------------
# Subgraph factory
# ---------------------------------------------------------------------------


def create_planning_subgraph() -> Any:
    """Build and compile the planning subgraph."""
    graph = StateGraph(WorkflowState)
    graph.add_node("plan", _plan_node)
    graph.add_edge(START, "plan")
    graph.add_edge("plan", END)
    return graph.compile()


# ---------------------------------------------------------------------------
# Public entry point (imported by supervisor.py)
# ---------------------------------------------------------------------------


async def run_planner(state: WorkflowState) -> dict[str, Any]:
    """Invoke the planning subgraph and return its state update.

    This is the function imported by ``supervisor.py``'s ``planner_node``.
    """
    subgraph = create_planning_subgraph()
    result = await subgraph.ainvoke(state)
    return {"steps": result.get("steps", [])}
