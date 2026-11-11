"""Tool definitions and the VALIDATOR.

This is "Layer 1" of the defence (the agent handout, section 6.1): an
allowlist plus argument checking. It reduces mistakes and blocks obviously
bad requests, but it is NOT the final security boundary - a different program
could call the system call directly. (Real enforcement would live in the
kernel, e.g. taint tracking, which is out of scope for this 60% milestone.)

A tool call looks like:  {"tool": "read_file", "args": {"path": "/report.txt"}}
Model/planner output is treated as UNTRUSTED: validate_action() either returns
a clean copy or raises ValidationError. Nothing here executes anything.
"""
import re

from . import config


class ValidationError(Exception):
    """The proposed action was refused. `code` is a stable machine-readable reason."""

    def __init__(self, code, message):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


# name -> schema. "required" are the only allowed argument names (no extras).
# "side_effect": True means the call changes guest state and therefore must
# carry a durable idempotency key (see journal.py).
TOOLS = {
    "list_files":  {"required": {},                             "side_effect": False, "where": "guest"},
    "read_file":   {"required": {"path": "path"},               "side_effect": False, "where": "guest"},
    "summarize":   {"required": {"text": "text"},               "side_effect": False, "where": "host"},
    "append_file": {"required": {"path": "wpath", "text": "payload"}, "side_effect": True,  "where": "guest"},
    "create_file": {"required": {"path": "newpath", "text": "payload"}, "side_effect": True, "where": "guest"},
}

_PATH = re.compile(config.PATH_REGEX)


def _check_value(kind, value, argname):
    if not isinstance(value, str):
        raise ValidationError("bad-type", f"argument '{argname}' must be a string, got {type(value).__name__}")
    if kind in ("path", "wpath", "newpath"):
        if not _PATH.match(value):
            raise ValidationError("bad-path", f"path {value!r} is outside the allowed exercise area")
        if kind == "wpath" and value not in config.WRITABLE_PATHS:
            raise ValidationError("not-writable", f"{value!r} is not in the writable allowlist {config.WRITABLE_PATHS}")
        if kind == "newpath" and value not in config.WRITABLE_PATHS:
            raise ValidationError("not-writable", f"{value!r} may not be created (allowlist {config.WRITABLE_PATHS})")
    elif kind == "payload":
        if not (1 <= len(value) <= config.MAX_TEXT):
            raise ValidationError("bad-length", f"'{argname}' must be 1..{config.MAX_TEXT} characters")
        if not all(0x20 <= ord(c) <= 0x7E for c in value):
            raise ValidationError("bad-chars", f"'{argname}' must be printable ASCII")
    elif kind == "text":
        if len(value) > config.MAX_SUMMARY_INPUT:
            raise ValidationError("too-long", f"'{argname}' exceeds {config.MAX_SUMMARY_INPUT} characters")
    return value


def validate_action(action):
    """Return a validated copy of `action` or raise ValidationError."""
    if not isinstance(action, dict):
        raise ValidationError("bad-shape", "action must be an object")
    if set(action.keys()) != {"tool", "args"}:
        raise ValidationError("bad-shape", f"action must have exactly the fields 'tool' and 'args', got {sorted(action.keys())}")
    name = action["tool"]
    if not isinstance(name, str) or name not in TOOLS:
        raise ValidationError("unknown-tool", f"tool {name!r} is not in the allowlist {sorted(TOOLS)}")
    args = action["args"]
    if not isinstance(args, dict):
        raise ValidationError("bad-shape", "'args' must be an object")
    schema = TOOLS[name]["required"]
    missing = [a for a in schema if a not in args]
    if missing:
        raise ValidationError("missing-arg", f"tool {name} requires {missing}")
    extra = [a for a in args if a not in schema]
    if extra:
        raise ValidationError("unexpected-arg", f"tool {name} does not accept {extra}")
    clean = {a: _check_value(kind, args[a], a) for a, kind in schema.items()}
    return {"tool": name, "args": clean}


def is_side_effect(tool):
    return TOOLS[tool]["side_effect"]
