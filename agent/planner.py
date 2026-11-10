"""
Deterministic planner — dispatches tool calls without an LLM.

The planner takes a high-level task description (a simple JSON
instruction) and maps it to a sequence of allowlisted tool invocations.
No language model is involved: the mapping is a fixed lookup table.

An LLM adapter can be layered on top *after* deterministic integration
works (see agent/llm_adapter.py).
"""

from __future__ import annotations
import hashlib
import time
from typing import Any, Dict, List, Optional, Tuple

from agent.journal import RequestJournal, JournalEntry
from agent.tools import TOOL_REGISTRY, ToolDef
from agent.bridge import QEMUBridge
from agent.protocol import validate_correlation_id


def _make_correlation_id(tool_name: str, args: Dict[str, Any]) -> str:
    """Deterministic correlation ID from tool name + arguments.

    This ensures that the *same* logical request always gets the *same*
    correlation ID, so an ambiguous retry reuses the existing identity
    rather than generating a fresh one.
    """
    import json

    blob = json.dumps(
        {"tool": tool_name, "args": args}, sort_keys=True, separators=(",", ":")
    )
    h = hashlib.sha256(blob.encode()).hexdigest()[:16]
    return h


class PlanStep:
    """One step in a deterministic plan."""

    def __init__(self, tool_name: str, arguments: Dict[str, Any]):
        self.tool_name = tool_name
        self.arguments = arguments
        self.correlation_id = _make_correlation_id(tool_name, arguments)


class DeterministicPlanner:
    """Execute tool calls against the guest via the bridge.

    Usage:
        planner = DeterministicPlanner(bridge, journal)
        result = planner.execute("list_files", {"path": "."})
        result = planner.execute("read_file", {"path": "README"})
        result = planner.execute("effect_append", {
            "path": "output.txt",
            "data": "hello\\n",
        })
    """

    def __init__(self, bridge: QEMUBridge, journal: RequestJournal):
        self.bridge = bridge
        self.journal = journal

    def execute(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Validate, journal, dispatch, and record a single tool call.

        Returns the tool's result string.

        Raises:
            ValueError: if the tool or arguments are invalid.
            ConnectionError: if the bridge is down.
            TimeoutError: if the guest does not respond.
        """
        # 1. Look up tool in allowlist.
        tool = TOOL_REGISTRY.get(tool_name)
        if tool is None:
            raise ValueError(f"tool not in allowlist: {tool_name!r}")

        # 2. Validate arguments.
        validated = tool.validate_args(arguments)

        # 3. Compute deterministic correlation ID.
        corr_id = _make_correlation_id(tool_name, validated)

        # 4. Check journal: if this exact request was already completed,
        #    return the cached result (no re-dispatch).
        existing = self.journal.get(corr_id)
        if existing and existing.status == JournalEntry.COMPLETED:
            return existing.response or ""

        # 5. Journal the request *before* dispatching.
        if existing is None:
            self.journal.record_request(corr_id, tool_name, validated)
        # If existing is pending, we are resuming — reuse its identity.

        # 6. Build the argument string for effectctl.
        args_str = self._build_args_str(tool, validated)

        # 7. Dispatch via bridge.
        try:
            result = self.bridge.invoke_tool(
                tool_name, tool.guest_command, args_str, corr_id
            )
        except TimeoutError:
            self.journal.complete(corr_id, "timeout", JournalEntry.TIMEOUT)
            raise
        except ConnectionError:
            self.journal.complete(corr_id, "crash", JournalEntry.CRASH)
            raise

        # 8. Check for error responses.
        if result.startswith("ERROR:"):
            self.journal.complete(corr_id, result, JournalEntry.ERROR)
            return result

        # 9. Success — record and return.
        self.journal.complete(corr_id, result, JournalEntry.COMPLETED)
        return result

    def resume_pending(self) -> List[Tuple[str, str]]:
        """Re-dispatch all pending requests from a previous session.

        Returns list of (correlation_id, result) for each resumed request.
        """
        results = []
        for entry in self.journal.pending():
            tool = TOOL_REGISTRY.get(entry.tool_name)
            if tool is None:
                self.journal.complete(
                    entry.correlation_id,
                    f"tool no longer in registry: {entry.tool_name}",
                    JournalEntry.ERROR,
                )
                continue
            args_str = self._build_args_str(tool, entry.arguments)
            try:
                result = self.bridge.invoke_tool(
                    entry.tool_name,
                    tool.guest_command,
                    args_str,
                    entry.correlation_id,
                )
                status = (
                    JournalEntry.ERROR
                    if result.startswith("ERROR:")
                    else JournalEntry.COMPLETED
                )
                self.journal.complete(entry.correlation_id, result, status)
                results.append((entry.correlation_id, result))
            except (TimeoutError, ConnectionError) as exc:
                self.journal.complete(
                    entry.correlation_id, str(exc), JournalEntry.CRASH
                )
                results.append((entry.correlation_id, str(exc)))
        return results

    @staticmethod
    def _build_args_str(tool: ToolDef, args: Dict[str, Any]) -> str:
        """Serialize validated arguments into a positional string for effectctl."""
        parts = []
        for p in tool.params:
            v = args.get(p.name)
            if v is not None:
                parts.append(str(v))
        return " ".join(parts)
