"""
Allowlisted tool definitions with argument and path validation.

Each tool is a named operation that the agent may invoke inside the
guest via the `effectctl` utility.  Tools are partitioned into two
tiers:

  **Read-only tools** (list_files, read_file):
    Safe observations that never mutate the guest filesystem.

  **Effect tools** (effect_append, effect_status, grant_status):
    Mutating or status-query operations that go through the kernel
    effect ABI and are therefore idempotent and auditable.

The agent's planner may only select tools from TOOL_REGISTRY.
Arbitrary shell commands are never generated.
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


# ---------------------------------------------------------------------------
# Path validation
# ---------------------------------------------------------------------------

# xv6 paths: no '..' components, max 128 chars, no NUL bytes, no '//'.
_SAFE_PATH_RE = re.compile(r"^[a-zA-Z0-9_./-]{1,127}$")
_DOTDOT_RE = re.compile(r"(^|/)\.\.(/|$)")


def validate_path(path: str) -> str:
    """Return the path unchanged if safe, else raise ValueError."""
    if not path or "\x00" in path:
        raise ValueError(f"path contains NUL or is empty: {path!r}")
    if _DOTDOT_RE.search(path):
        raise ValueError(f"path contains '..': {path!r}")
    if "//" in path:
        raise ValueError(f"path contains '//': {path!r}")
    if not _SAFE_PATH_RE.match(path):
        raise ValueError(f"path has disallowed characters or is too long: {path!r}")
    return path


def validate_int(value: Any, *, name: str, lo: int = 0, hi: int = 2**63) -> int:
    """Coerce to int and range-check."""
    try:
        v = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name}: expected integer, got {type(value).__name__}")
    if not (lo <= v <= hi):
        raise ValueError(f"{name}: {v} not in [{lo}, {hi}]")
    return v


def validate_payload(data: str, *, max_len: int = 512) -> str:
    """Validate an effect payload string (max EFFECT_MAX_PAYLOAD=512)."""
    if len(data.encode("utf-8", errors="replace")) > max_len:
        raise ValueError(f"payload exceeds {max_len} bytes")
    return data


# ---------------------------------------------------------------------------
# Tool schema
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ToolParam:
    name: str
    type: str  # "path", "string", "int"
    description: str
    required: bool = True
    default: Any = None


@dataclass(frozen=True)
class ToolDef:
    """A single allowlisted tool the agent may invoke."""

    name: str
    description: str
    category: str  # "read" or "effect"
    params: List[ToolParam] = field(default_factory=list)
    guest_command: str = ""  # the effectctl subcommand

    def validate_args(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and normalize arguments. Raises ValueError on bad input."""
        validated: Dict[str, Any] = {}
        for p in self.params:
            raw = args.get(p.name, p.default if not p.required else None)
            if raw is None and p.required:
                raise ValueError(f"missing required argument: {p.name}")
            if raw is None:
                continue
            if p.type == "path":
                validated[p.name] = validate_path(str(raw))
            elif p.type == "int":
                validated[p.name] = validate_int(raw, name=p.name)
            elif p.type == "string":
                validated[p.name] = str(raw)
            else:
                validated[p.name] = raw
        # Reject unknown arguments.
        known = {p.name for p in self.params}
        for k in args:
            if k not in known:
                raise ValueError(f"unknown argument: {k}")
        return validated


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

TOOL_REGISTRY: Dict[str, ToolDef] = {}


def _register(tool: ToolDef) -> ToolDef:
    TOOL_REGISTRY[tool.name] = tool
    return tool


# -- Read-only tools --------------------------------------------------------

_register(ToolDef(
    name="list_files",
    description="List files in the guest filesystem root (or a subdirectory).",
    category="read",
    params=[
        ToolParam("path", "path", "Directory to list (default: '.')", required=False, default="."),
    ],
    guest_command="ls",
))

_register(ToolDef(
    name="read_file",
    description="Read the contents of a file in the guest filesystem.",
    category="read",
    params=[
        ToolParam("path", "path", "Path of the file to read."),
    ],
    guest_command="cat",
))

# -- Effect / status tools --------------------------------------------------

_register(ToolDef(
    name="effect_append",
    description="Append data to a file via the effect ABI (idempotent, auditable).",
    category="effect",
    params=[
        ToolParam("path", "path", "Target file path."),
        ToolParam("data", "string", "Payload to append (max 512 bytes)."),
        ToolParam("grant_id", "int", "Grant ID authorizing this append.", required=False),
        ToolParam("req_id", "int", "Unique request ID for idempotency.", required=False),
    ],
    guest_command="append",
))

_register(ToolDef(
    name="effect_status",
    description="Query the status of a previously executed effect.",
    category="effect",
    params=[
        ToolParam("key", "int", "Base key or req_id to look up."),
        ToolParam("grant_id", "int", "Grant ID (for extended lookup).", required=False),
    ],
    guest_command="status",
))

_register(ToolDef(
    name="grant_status",
    description="Query the lifecycle state of a grant.",
    category="effect",
    params=[
        ToolParam("grant_id", "int", "Grant ID to inspect."),
    ],
    guest_command="grantstatus",
))
