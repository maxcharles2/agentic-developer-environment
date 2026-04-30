"""Codegen agent — generates or modifies source code files for a workflow step.

The agent runs a manual ReAct tool-calling loop (max 10 iterations) using
three tools:
- ``write_file``: writes a file to the workspace (defined here).
- ``read_file``: reads an existing file (imported from the context agent).
- ``search_codebase``: semantic search via the ContextService gRPC API
  (imported from the context agent).

Written files are collected into ``CodeArtifact`` objects and persisted to the
Supabase ``code_artifacts`` table (best-effort).
"""

from __future__ import annotations

import functools
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage  # type: ignore[import]
from langchain_core.tools import tool  # type: ignore[import]

from ade_types.artifact import CodeArtifact
from src.agents.context import read_file, search_codebase
from src.config import settings
from src.state.workflow import WorkflowState

log = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

MAX_TOOL_CALLS = 10

# ---------------------------------------------------------------------------
# Module-level tracker for files written during a ReAct loop
# ---------------------------------------------------------------------------

# Each entry: {"file_path": str, "content": str}
_written_files: list[dict[str, str]] = []


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------


@tool
def write_file(file_path: str, content: str) -> str:
    """Write or overwrite a file inside the workspace.

    Args:
        file_path: Workspace-relative or absolute path to the destination file.
        content: Complete file content to write (never partial snippets).

    Returns:
        Confirmation string on success, or an error message on failure.
    """
    try:
        workspace_root = Path(os.environ.get("WORKSPACE_ROOT", "/workspace")).resolve()

        # Resolve to absolute path; guard against path traversal.
        resolved = Path(file_path).resolve()
        if not str(resolved).startswith(str(workspace_root)):
            candidate = (workspace_root / file_path).resolve()
            if not str(candidate).startswith(str(workspace_root)):
                return f"Error: path traversal detected for '{file_path}'"
            resolved = candidate

        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")

        _written_files.append({"file_path": str(resolved), "content": content})
        log.info("write_file: wrote %d bytes to '%s'", len(content), resolved)
        return f"Successfully wrote {len(content)} bytes to '{resolved}'"
    except Exception as exc:  # noqa: BLE001
        log.warning("write_file failed for '%s': %s", file_path, exc)
        return f"Error writing file '{file_path}': {exc}"


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

_EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".json": "json",
    ".md": "markdown",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".sh": "shell",
    ".bash": "shell",
    ".html": "html",
    ".css": "css",
    ".sql": "sql",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".tf": "terraform",
}


def _detect_language(file_path: str) -> str:
    """Return a language string based on the file extension."""
    suffix = Path(file_path).suffix.lower()
    return _EXTENSION_TO_LANGUAGE.get(suffix, "plaintext")


# ---------------------------------------------------------------------------
# LLM factory
# ---------------------------------------------------------------------------


def _get_codegen_llm() -> Any:
    """Return a ChatModel bound to the codegen tools."""
    model = settings.WORKER_MODEL
    if "claude" in model.lower() or "anthropic" in model.lower():
        from langchain_anthropic import ChatAnthropic  # type: ignore[import]

        llm = ChatAnthropic(model=model, api_key=settings.ANTHROPIC_API_KEY)
    else:
        from langchain_openai import ChatOpenAI  # type: ignore[import]

        llm = ChatOpenAI(model=model, api_key=settings.OPENAI_API_KEY)
    return llm.bind_tools([write_file, read_file, search_codebase])


# ---------------------------------------------------------------------------
# System prompt loader
# ---------------------------------------------------------------------------


@functools.lru_cache(maxsize=1)
def _load_system_prompt() -> str:
    """Read and cache the codegen agent system prompt from ``prompts/codegen.md``."""
    prompt_path = _PROMPTS_DIR / "codegen.md"
    return prompt_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Tool executor
# ---------------------------------------------------------------------------


async def _execute_tool_call(tool_name: str, tool_args: dict) -> str:
    """Dispatch a codegen tool call by name and return its string result."""
    if tool_name == "write_file":
        return write_file.invoke(tool_args)
    elif tool_name == "read_file":
        return read_file.invoke(tool_args)
    elif tool_name == "search_codebase":
        result = await search_codebase.ainvoke(tool_args)
        if not result:
            return "No results found."
        lines = [
            f"[{i + 1}] {chunk['file_path']} (score={chunk.get('score', 'n/a')})\n{chunk['content']}"
            for i, chunk in enumerate(result)
        ]
        return "\n\n".join(lines)
    else:
        return f"Unknown tool: {tool_name}"


# ---------------------------------------------------------------------------
# Core agent function
# ---------------------------------------------------------------------------


async def run_codegen(state: WorkflowState) -> dict[str, Any]:
    """Generate or modify source code files for the current workflow step.

    Runs a manual ReAct tool-calling loop (max ``MAX_TOOL_CALLS`` iterations).
    All files written by the LLM are collected into ``CodeArtifact`` objects,
    persisted to Supabase, and returned as ``artifacts`` appended to state.

    Returns:
        A partial state update ``{"artifacts": [CodeArtifact, ...]}``.
    """
    global _written_files  # noqa: PLW0603
    _written_files = []

    system_prompt = _load_system_prompt()

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

    context_chunks = state.get("context_chunks") or []
    if context_chunks:
        user_content_parts.append("Relevant context:\n" + "\n\n".join(context_chunks))

    prior_error = state.get("error")
    if prior_error:
        user_content_parts.append(
            f"Previous attempt failed with the following error — fix it:\n{prior_error}"
        )

    user_content_parts.append(
        "Implement the current step by writing the required files using write_file."
    )
    user_message = "\n\n".join(user_content_parts)

    messages: list[BaseMessage] = [
        {"role": "system", "content": system_prompt},  # type: ignore[arg-type]
        {"role": "user", "content": user_message},  # type: ignore[arg-type]
    ]

    llm = _get_codegen_llm()
    tool_calls_made = 0

    for iteration in range(MAX_TOOL_CALLS):
        response: AIMessage = await llm.ainvoke(messages)
        messages.append(response)

        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            log.info(
                "Codegen agent finished after %d tool call(s) for task_id=%s",
                tool_calls_made,
                state["task_id"],
            )
            break

        for tc in tool_calls:
            if tool_calls_made >= MAX_TOOL_CALLS:
                log.warning(
                    "Codegen agent reached MAX_TOOL_CALLS=%d — stopping early (task_id=%s)",
                    MAX_TOOL_CALLS,
                    state["task_id"],
                )
                break

            tool_name = tc["name"]
            tool_args = tc.get("args") or {}
            tool_call_id = tc.get("id") or f"call_{tool_calls_made}"

            log.debug(
                "Codegen agent: invoking %s(args=%s) [call %d/%d]",
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
                "Codegen agent: MAX_TOOL_CALLS=%d reached at iteration %d (task_id=%s)",
                MAX_TOOL_CALLS,
                iteration + 1,
                state["task_id"],
            )
            break
    else:
        log.warning(
            "Codegen agent loop exhausted without LLM finishing (task_id=%s)",
            state["task_id"],
        )

    # Build CodeArtifact objects for every file the LLM wrote.
    task_uuid = UUID(state["task_id"])
    run_uuid = uuid4()
    now = datetime.now(timezone.utc)

    artifacts: list[CodeArtifact] = [
        CodeArtifact(
            id=uuid4(),
            run_id=run_uuid,
            task_id=task_uuid,
            file_path=entry["file_path"],
            content=entry["content"],
            language=_detect_language(entry["file_path"]),
            version=1,
            created_at=now,
        )
        for entry in _written_files
    ]

    _persist_artifacts(artifacts)

    log.info(
        "Codegen agent returning %d artifact(s) for task_id=%s",
        len(artifacts),
        state["task_id"],
    )
    return {"artifacts": artifacts}


# ---------------------------------------------------------------------------
# Supabase persistence (best-effort)
# ---------------------------------------------------------------------------


def _persist_artifacts(artifacts: list[CodeArtifact]) -> None:
    """Batch-insert code artifacts into ``code_artifacts``.  Non-fatal on failure."""
    if not artifacts:
        return

    if not (settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY):
        log.warning("Supabase not configured — skipping artifact persistence")
        return

    try:
        from supabase import create_client  # type: ignore[import]

        client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)
        rows = [
            {
                "id": str(artifact.id),
                "run_id": str(artifact.run_id),
                "task_id": str(artifact.task_id),
                "file_path": artifact.file_path,
                "content": artifact.content,
                "diff": artifact.diff,
                "language": artifact.language,
                "version": artifact.version,
                "created_at": artifact.created_at.isoformat(),
            }
            for artifact in artifacts
        ]
        client.table("code_artifacts").insert(rows).execute()
        log.info("Persisted %d code artifact(s) to Supabase", len(artifacts))
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not persist artifacts to Supabase (%s) — continuing", exc)
