import operator
from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from ade_types import CodeArtifact, ExecutionResult, TaskStep


class WorkflowState(TypedDict):
    task_id: str
    project_id: str
    prompt: str
    steps: Annotated[list[TaskStep], operator.add]
    current_step_index: int
    context_chunks: Annotated[list[str], operator.add]
    artifacts: Annotated[list[CodeArtifact], operator.add]
    execution_results: Annotated[list[ExecutionResult], operator.add]
    messages: Annotated[list[BaseMessage], add_messages]
    next_agent: str
    retry_count: int
    requires_approval: bool
    error: str | None


def create_initial_state(task_id: str, project_id: str, prompt: str) -> WorkflowState:
    return WorkflowState(
        task_id=task_id,
        project_id=project_id,
        prompt=prompt,
        steps=[],
        current_step_index=0,
        context_chunks=[],
        artifacts=[],
        execution_results=[],
        messages=[],
        next_agent="",
        retry_count=0,
        requires_approval=False,
        error=None,
    )


def get_current_step(state: WorkflowState) -> TaskStep | None:
    steps = state["steps"]
    index = state["current_step_index"]
    if not steps or index < 0 or index >= len(steps):
        return None
    return steps[index]


def advance_step(state: WorkflowState) -> WorkflowState:
    return {**state, "current_step_index": state["current_step_index"] + 1}


def set_error(state: WorkflowState, error_msg: str) -> WorkflowState:
    return {**state, "error": error_msg}
