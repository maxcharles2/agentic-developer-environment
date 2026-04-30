"""Codegen subgraph with quality gate and retry loop.

Graph topology::

    START → codegen_node → quality_gate_node ─┬─→ END          (pass or retries ≥ 3)
                                ↑              └─→ codegen_node  (fail + retries < 3)
"""

from __future__ import annotations

import ast
import logging
import re
from typing import Any

from langgraph.graph import END, START, StateGraph

from src.state.workflow import WorkflowState

log = logging.getLogger(__name__)

MAX_RETRIES = 3

# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


async def _codegen_node(state: WorkflowState) -> dict[str, Any]:
    """Run the codegen agent to generate or modify source files."""
    from src.agents.codegen import run_codegen as _agent_run_codegen  # local import

    return await _agent_run_codegen(state)


def _quality_gate_node(state: WorkflowState) -> dict[str, Any]:
    """Deterministic quality check on the most recently produced artifacts.

    Checks:
    - ``.py`` files: ``ast.parse`` to catch syntax errors.
    - ``.ts`` / ``.tsx`` / ``.js`` / ``.jsx`` files: regex heuristics for
      obvious structural problems (unmatched braces, unterminated strings).
    - All other extensions: skipped (pass by default).

    Returns a partial state update with ``error`` (None on pass, message on
    fail) and, on failure, an incremented ``retry_count``.
    """
    artifacts = state.get("artifacts") or []

    errors: list[str] = []

    for artifact in artifacts:
        file_path: str = getattr(artifact, "file_path", "") or ""
        content: str = getattr(artifact, "content", "") or ""
        ext = _file_extension(file_path)

        if ext == ".py":
            err = _check_python_syntax(file_path, content)
            if err:
                errors.append(err)
        elif ext in {".ts", ".tsx", ".js", ".jsx"}:
            err = _check_js_ts_heuristics(file_path, content)
            if err:
                errors.append(err)
        # Other extensions pass without checks.

    if not errors:
        log.info("Quality gate: all %d artifact(s) passed", len(artifacts))
        return {"error": None}

    error_msg = "Quality gate failed:\n" + "\n".join(f"  - {e}" for e in errors)
    new_retry_count = (state.get("retry_count") or 0) + 1
    log.warning(
        "Quality gate: %d error(s) found, retry_count → %d: %s",
        len(errors),
        new_retry_count,
        error_msg,
    )
    return {"error": error_msg, "retry_count": new_retry_count}


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


def _route_after_quality_gate(state: WorkflowState) -> str:
    """Return the next node name after the quality gate runs.

    - ``"end"``   → quality passed, or we've exhausted retries.
    - ``"retry"`` → quality failed and retries remain.
    """
    if state.get("error") is None:
        return "end"
    if (state.get("retry_count") or 0) >= MAX_RETRIES:
        log.warning(
            "Quality gate: MAX_RETRIES=%d reached for task_id=%s — giving up",
            MAX_RETRIES,
            state.get("task_id"),
        )
        return "end"
    return "retry"


# ---------------------------------------------------------------------------
# Static syntax helpers
# ---------------------------------------------------------------------------


def _file_extension(file_path: str) -> str:
    """Return the lowercase file extension including the leading dot."""
    if "." not in file_path.rsplit("/", 1)[-1]:
        return ""
    return "." + file_path.rsplit(".", 1)[-1].lower()


def _check_python_syntax(file_path: str, content: str) -> str | None:
    """Return an error string if ``content`` has a Python syntax error."""
    try:
        ast.parse(content)
        return None
    except SyntaxError as exc:
        return f"{file_path}: Python SyntaxError at line {exc.lineno}: {exc.msg}"


def _check_js_ts_heuristics(file_path: str, content: str) -> str | None:
    """Return an error string if ``content`` has obvious JS/TS structural issues."""
    # Check for unmatched curly braces (after stripping string literals and comments).
    stripped = _strip_strings_and_comments(content)
    open_braces = stripped.count("{")
    close_braces = stripped.count("}")
    if open_braces != close_braces:
        return (
            f"{file_path}: unmatched curly braces "
            f"(open={open_braces}, close={close_braces})"
        )

    # Detect unterminated template literals in the raw content (backtick count must be even).
    backtick_count = content.count("`")
    if backtick_count % 2 != 0:
        return f"{file_path}: odd number of backticks — possible unterminated template literal"

    return None


def _strip_strings_and_comments(source: str) -> str:
    """Very roughly strip string literals and line/block comments from JS/TS source."""
    # Remove block comments.
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    # Remove line comments.
    source = re.sub(r"//[^\n]*", "", source)
    # Remove double-quoted strings (no multiline).
    source = re.sub(r'"(?:[^"\\]|\\.)*"', '""', source)
    # Remove single-quoted strings (no multiline).
    source = re.sub(r"'(?:[^'\\]|\\.)*'", "''", source)
    # Remove template literals (simplified; handles most common cases).
    source = re.sub(r"`(?:[^`\\]|\\.)*`", "``", source)
    return source


# ---------------------------------------------------------------------------
# Subgraph factory
# ---------------------------------------------------------------------------


def create_codegen_subgraph() -> Any:
    """Build and compile the codegen subgraph with its quality-gate retry loop."""
    graph = StateGraph(WorkflowState)

    graph.add_node("codegen_node", _codegen_node)
    graph.add_node("quality_gate_node", _quality_gate_node)

    graph.add_edge(START, "codegen_node")
    graph.add_edge("codegen_node", "quality_gate_node")
    graph.add_conditional_edges(
        "quality_gate_node",
        _route_after_quality_gate,
        {
            "end": END,
            "retry": "codegen_node",
        },
    )

    return graph.compile()


# ---------------------------------------------------------------------------
# Public entry point (imported by supervisor.py)
# ---------------------------------------------------------------------------


async def run_codegen(state: WorkflowState) -> dict[str, Any]:
    """Invoke the codegen subgraph and return the relevant state fields.

    This is the function imported by ``supervisor.py``'s ``codegen_node``.
    It propagates ``artifacts``, ``error``, and ``retry_count`` back to the
    parent workflow state.
    """
    subgraph = create_codegen_subgraph()
    result: WorkflowState = await subgraph.ainvoke(state)

    update: dict[str, Any] = {
        "artifacts": result.get("artifacts") or [],
    }

    error = result.get("error")
    if error is not None:
        update["error"] = error

    retry_count = result.get("retry_count")
    if retry_count is not None:
        update["retry_count"] = retry_count

    log.info(
        "Codegen subgraph finished: artifacts=%d error=%s retry_count=%s",
        len(update["artifacts"]),
        update.get("error"),
        update.get("retry_count"),
    )
    return update
