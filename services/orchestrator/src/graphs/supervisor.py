"""Supervisor graph for the ADE orchestrator.

The supervisor is the central routing brain: it reads the current
``WorkflowState``, decides which specialist subgraph to invoke next, and
returns control after each agent completes — it never executes work itself.

Graph topology::

    START → supervisor_node ─┬─→ planner_node     ─┐
                              ├─→ context_node      ├─→ supervisor_node
                              ├─→ codegen_node      │
                              ├─→ executor_node    ─┘
                              ├─→ human_review_node ─→ supervisor_node
                              └─→ END
"""

from __future__ import annotations

import logging
from typing import Any, Literal

import redis.asyncio as aioredis
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import BaseModel

from src.config import settings
from src.state.workflow import WorkflowState

log = logging.getLogger(__name__)

MAX_ITERATIONS = 20


# ---------------------------------------------------------------------------
# Structured routing decision
# ---------------------------------------------------------------------------


class SupervisorDecision(BaseModel):
    """Structured output from the supervisor LLM."""

    next: Literal["planner", "context", "codegen", "executor", "human_review", "done"]
    reasoning: str


# ---------------------------------------------------------------------------
# LLM factory
# ---------------------------------------------------------------------------


def _get_supervisor_llm() -> Any:
    """Return a structured-output LLM client for the configured supervisor model."""
    model = settings.SUPERVISOR_MODEL
    if "claude" in model.lower() or "anthropic" in model.lower():
        from langchain_anthropic import ChatAnthropic

        llm = ChatAnthropic(model=model, api_key=settings.ANTHROPIC_API_KEY)
    else:
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(model=model, api_key=settings.OPENAI_API_KEY)
    return llm.with_structured_output(SupervisorDecision)


# ---------------------------------------------------------------------------
# Supervisor system prompt
# ---------------------------------------------------------------------------

SUPERVISOR_SYSTEM_PROMPT = """\
You are the Supervisor for the Agentic Developer Environment (ADE).
Your sole responsibility is to decide which specialist agent to invoke next
based on the current workflow state.  You NEVER execute tasks yourself.

Available agents
----------------
- planner       : Decomposes the user's prompt into an ordered list of TaskSteps.
                  Use first, or when the plan needs revision.
- context       : Retrieves relevant code snippets / documentation from the
                  project's vector store.  Use when codegen or planner needs
                  more context.
- codegen       : Generates or edits source code for the current step.
                  Use after the plan and context are ready.
- executor      : Runs the generated code in an isolated sandbox and captures
                  test results / output.  Use after codegen produces artifacts.
- human_review  : Pauses the workflow and requests human approval.  Use when
                  the task involves destructive operations, security-sensitive
                  changes, or when confidence is low after repeated retries.
- done          : Signals workflow completion (success or unrecoverable failure).

Routing rules
-------------
1. If no steps exist → planner.
2. If the current step needs code context → context.
3. If the current step has context but no artifacts → codegen.
4. If artifacts exist for the current step and no execution result yet → executor.
5. If execution succeeded and more steps remain → advance and return to planner
   (or supervisor can send to codegen directly for the next step).
6. If retry_count > 2 for the same step → human_review.
7. If all steps are complete with passing results → done.
8. Always set `reasoning` to a one-sentence explanation of your decision.
"""


# ---------------------------------------------------------------------------
# State summary formatter
# ---------------------------------------------------------------------------


def _format_state_summary(state: WorkflowState) -> str:
    """Produce a concise text summary of the workflow state for the LLM."""
    lines: list[str] = [
        f"Task ID   : {state['task_id']}",
        f"Prompt    : {state['prompt']}",
        f"Retry cnt : {state['retry_count']}",
        f"Error     : {state.get('error') or 'none'}",
        f"Requires approval: {state['requires_approval']}",
    ]

    steps = state.get("steps") or []
    idx = state.get("current_step_index", 0)
    lines.append(f"Steps     : {len(steps)} total, current index={idx}")
    if steps:
        current = steps[idx] if 0 <= idx < len(steps) else None
        if current is not None:
            # TaskStep is a Pydantic model; access via attribute or dict
            desc = getattr(current, "description", None) or (
                current.get("description") if isinstance(current, dict) else ""
            )
            lines.append(f"Current step: {desc}")

    artifacts = state.get("artifacts") or []
    if artifacts:
        recent = artifacts[-3:]
        paths = []
        for a in recent:
            p = getattr(a, "file_path", None) or (
                a.get("file_path") if isinstance(a, dict) else "?"
            )
            paths.append(str(p))
        lines.append(f"Recent artifacts ({len(artifacts)} total): {', '.join(paths)}")

    exec_results = state.get("execution_results") or []
    if exec_results:
        last = exec_results[-1]
        success = getattr(last, "success", None)
        if success is None and isinstance(last, dict):
            success = last.get("success")
        lines.append(f"Last execution success: {success}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Node functions
# ---------------------------------------------------------------------------


async def supervisor_node(
    state: WorkflowState, config: RunnableConfig
) -> dict[str, Any]:
    """LLM routing brain — reads state and decides which agent runs next."""
    # --- Iteration guard via supervisor messages in history ---
    messages = state.get("messages") or []
    supervisor_turns = sum(
        1 for m in messages if getattr(m, "name", None) == "supervisor"
    )
    if supervisor_turns >= MAX_ITERATIONS:
        log.warning(
            "Max iterations (%d) reached for task_id=%s", MAX_ITERATIONS, state["task_id"]
        )
        return {"next_agent": "done", "error": "Max iterations exceeded"}

    # --- Redis cancellation check ---
    task_id = state["task_id"]
    try:
        redis_client: aioredis.Redis = aioredis.from_url(
            settings.REDIS_URL, decode_responses=True
        )
        cancel_flag = await redis_client.get(f"workflow:cancel:{task_id}")
        await redis_client.aclose()
        if cancel_flag:
            log.info("Workflow cancelled via Redis flag: task_id=%s", task_id)
            return {"next_agent": "done", "error": "Workflow cancelled"}
    except Exception as exc:  # noqa: BLE001
        log.warning("Redis check failed (non-fatal): %s", exc)

    # --- Unrecoverable error guard ---
    if state.get("error") and state.get("retry_count", 0) > 3:
        log.warning(
            "Forcing done: error=%s retry_count=%d", state["error"], state["retry_count"]
        )
        return {"next_agent": "done"}

    # --- LLM routing call ---
    state_summary = _format_state_summary(state)
    llm = _get_supervisor_llm()
    decision: SupervisorDecision = await llm.ainvoke(
        [
            {"role": "system", "content": SUPERVISOR_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Current workflow state:\n\n{state_summary}",
            },
        ]
    )

    log.info(
        "Supervisor decision: next=%s reasoning=%s task_id=%s",
        decision.next,
        decision.reasoning,
        task_id,
    )

    # Record the supervisor turn so we can count iterations.
    supervisor_message = HumanMessage(
        content=f"Route to {decision.next}: {decision.reasoning}",
        name="supervisor",
    )

    return {
        "next_agent": decision.next,
        "messages": [supervisor_message],
    }


async def planner_node(state: WorkflowState) -> dict[str, Any]:
    """Delegate to the planning subgraph (lazy import for loose coupling)."""
    try:
        from src.graphs.planning import run_planner  # type: ignore[import]

        return await run_planner(state)
    except ImportError:
        log.info("planner subgraph not yet implemented — passing through")
        return {}


async def context_node(state: WorkflowState) -> dict[str, Any]:
    """Delegate to the context-retrieval agent (lazy import)."""
    try:
        from src.agents.context import run_context  # type: ignore[import]

        return await run_context(state)
    except ImportError:
        log.info("context agent not yet implemented — passing through")
        return {}


async def codegen_node(state: WorkflowState) -> dict[str, Any]:
    """Delegate to the code-generation subgraph (lazy import)."""
    try:
        from src.graphs.codegen import run_codegen  # type: ignore[import]

        return await run_codegen(state)
    except ImportError:
        log.info("codegen subgraph not yet implemented — passing through")
        return {}


async def executor_node(state: WorkflowState) -> dict[str, Any]:
    """Delegate to the execution subgraph (lazy import)."""
    try:
        from src.graphs.execution import run_executor  # type: ignore[import]

        return await run_executor(state)
    except ImportError:
        log.info("execution subgraph not yet implemented — passing through")
        return {}


async def human_review_node(state: WorkflowState) -> dict[str, Any]:
    """Pause the graph and wait for human approval via LangGraph interrupt."""
    log.info("Requesting human review for task_id=%s", state["task_id"])
    interrupt("Human review required")
    # Execution resumes here after the operator posts approval.
    return {"requires_approval": False}


# ---------------------------------------------------------------------------
# Conditional edge router
# ---------------------------------------------------------------------------


def _route_next(state: WorkflowState) -> str:
    """Return the `next_agent` value so the graph can select the correct edge."""
    return state["next_agent"]


# ---------------------------------------------------------------------------
# Graph factory
# ---------------------------------------------------------------------------


def create_supervisor_graph(checkpointer: Any | None = None) -> Any:
    """Build and compile the supervisor StateGraph.

    Args:
        checkpointer: A LangGraph ``BaseCheckpointSaver`` instance (e.g.
            ``SupabaseCheckpointer``).  Pass ``None`` to compile without
            persistence (useful for unit tests).

    Returns:
        A compiled LangGraph ``CompiledStateGraph``.
    """
    graph = StateGraph(WorkflowState)

    # Nodes
    graph.add_node("supervisor_node", supervisor_node)
    graph.add_node("planner_node", planner_node)
    graph.add_node("context_node", context_node)
    graph.add_node("codegen_node", codegen_node)
    graph.add_node("executor_node", executor_node)
    graph.add_node("human_review_node", human_review_node)

    # Entry point
    graph.add_edge(START, "supervisor_node")

    # Conditional routing from supervisor
    graph.add_conditional_edges(
        "supervisor_node",
        _route_next,
        {
            "planner": "planner_node",
            "context": "context_node",
            "codegen": "codegen_node",
            "executor": "executor_node",
            "human_review": "human_review_node",
            "done": END,
        },
    )

    # All agent nodes return to the supervisor for the next routing decision
    for node_name in (
        "planner_node",
        "context_node",
        "codegen_node",
        "executor_node",
        "human_review_node",
    ):
        graph.add_edge(node_name, "supervisor_node")

    compile_kwargs: dict[str, Any] = {}
    if checkpointer is not None:
        compile_kwargs["checkpointer"] = checkpointer

    return graph.compile(**compile_kwargs)


def build_graph() -> Any:
    """Convenience entry point called by ``server.py``.

    Creates a ``SupabaseCheckpointer`` when credentials are available,
    otherwise compiles without persistence (development / testing fallback).
    """
    checkpointer = None
    if settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY:
        try:
            from src.state.checkpointer import SupabaseCheckpointer

            checkpointer = SupabaseCheckpointer(
                supabase_url=settings.SUPABASE_URL,
                supabase_key=settings.SUPABASE_SERVICE_KEY,
            )
            log.info("Supervisor graph: using SupabaseCheckpointer")
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not create SupabaseCheckpointer (%s) — running without persistence", exc)
    else:
        log.warning(
            "SUPABASE_URL or SUPABASE_SERVICE_KEY not configured — "
            "supervisor graph running without checkpoint persistence"
        )

    return create_supervisor_graph(checkpointer=checkpointer)
