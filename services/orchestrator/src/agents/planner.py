"""Planner agent — decomposes a task prompt into ordered TaskSteps.

The planner receives the current WorkflowState, calls a structured-output
LLM to produce a plan, converts each planned step into a ``TaskStep``, batch-
inserts them into Supabase, and returns the steps as a state update.

The planner has NO tools; it only generates structured output.
"""

from __future__ import annotations

import functools
import logging
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel

from ade_types.task import AgentType, StepStatus, TaskStep
from src.config import settings
from src.state.workflow import WorkflowState

log = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


# ---------------------------------------------------------------------------
# Structured output schema
# ---------------------------------------------------------------------------


class PlannedStep(BaseModel):
    title: str
    description: str
    agent_type: Literal["codegen", "executor", "context"]


class PlannerOutput(BaseModel):
    steps: list[PlannedStep]


# ---------------------------------------------------------------------------
# LLM factory
# ---------------------------------------------------------------------------


def _get_planner_llm() -> Any:
    """Return a structured-output LLM bound to ``PlannerOutput``."""
    model = settings.WORKER_MODEL
    if "claude" in model.lower() or "anthropic" in model.lower():
        from langchain_anthropic import ChatAnthropic

        llm = ChatAnthropic(model=model, api_key=settings.ANTHROPIC_API_KEY)
    else:
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(model=model, api_key=settings.OPENAI_API_KEY)
    return llm.with_structured_output(PlannerOutput)


# ---------------------------------------------------------------------------
# System prompt loader
# ---------------------------------------------------------------------------


@functools.lru_cache(maxsize=1)
def _load_system_prompt() -> str:
    """Read and cache the planner system prompt from ``prompts/planner.md``."""
    prompt_path = _PROMPTS_DIR / "planner.md"
    return prompt_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Core agent function
# ---------------------------------------------------------------------------


async def run_planner(state: WorkflowState) -> dict[str, Any]:
    """Decompose the workflow prompt into ``TaskStep`` objects.

    Steps are batch-inserted into the ``task_steps`` Supabase table when
    credentials are available.  If Supabase is unreachable the steps are
    still returned in state so the workflow can continue without persistence.

    Returns:
        A partial state update ``{"steps": [TaskStep, ...]}``.
    """
    system_prompt = _load_system_prompt()

    user_parts: list[str] = [f"Task: {state['prompt']}"]
    context_chunks = state.get("context_chunks") or []
    if context_chunks:
        joined = "\n\n".join(context_chunks)
        user_parts.append(f"Context:\n{joined}")
    user_message = "\n\n".join(user_parts)

    llm = _get_planner_llm()
    result: PlannerOutput = await llm.ainvoke(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
    )

    task_uuid = UUID(state["task_id"])
    task_steps: list[TaskStep] = [
        TaskStep(
            id=uuid4(),
            task_id=task_uuid,
            ordinal=i + 1,
            title=step.title,
            description=step.description,
            status=StepStatus.PENDING,
            agent_type=AgentType(step.agent_type),
        )
        for i, step in enumerate(result.steps)
    ]

    _persist_steps(task_steps)

    log.info(
        "Planner produced %d steps for task_id=%s", len(task_steps), state["task_id"]
    )
    return {"steps": task_steps}


# ---------------------------------------------------------------------------
# Supabase persistence (best-effort)
# ---------------------------------------------------------------------------


def _persist_steps(steps: list[TaskStep]) -> None:
    """Batch-insert steps into ``task_steps``.  Non-fatal on failure."""
    if not (settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY):
        log.warning("Supabase not configured — skipping step persistence")
        return

    try:
        from supabase import create_client

        client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)
        rows = [
            {
                "id": str(step.id),
                "task_id": str(step.task_id),
                "ordinal": step.ordinal,
                "title": step.title,
                "description": step.description,
                "status": step.status.value,
                "agent_type": step.agent_type.value,
                "input_data": step.input_data,
                "output_data": step.output_data,
            }
            for step in steps
        ]
        client.table("task_steps").insert(rows).execute()
        log.info("Persisted %d task steps to Supabase", len(steps))
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not persist steps to Supabase (%s) — continuing", exc)
