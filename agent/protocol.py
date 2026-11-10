"""
Bridge protocol framing and message types.

Every message exchanged between host and guest is a single line of text
terminated by '\\n'.  The format is:

    TYPE:CORRELATION_ID:PAYLOAD

TYPE is one of the symbolic tags defined below.  CORRELATION_ID is a
hex string that uniquely identifies a request/response pair and is
persisted in the host journal.  PAYLOAD is type-specific (may be empty).

The protocol distinguishes six message categories:
  BOOT     — guest kernel has started (guest → host)
  READY    — effectctl is waiting for a command (guest → host)
  REQUEST  — host sends a tool invocation to the guest (host → guest)
  RESPONSE — guest replies with a tool result (guest → host)
  ERROR    — guest reports a structured error (guest → host)
  CRASH    — host detects the guest process died (synthesized by host)
"""

from __future__ import annotations
import enum
import re
import dataclasses
from typing import Optional


class MsgType(enum.Enum):
    BOOT = "BOOT"
    READY = "READY"
    REQUEST = "REQUEST"
    RESPONSE = "RESPONSE"
    ERROR = "ERROR"
    CRASH = "CRASH"


# A valid correlation ID is 1–32 lowercase hex characters.
_CORR_RE = re.compile(r"^[0-9a-f]{1,32}$")

# Maximum raw line length we will ever accept (defense-in-depth).
MAX_LINE_BYTES = 4096


@dataclasses.dataclass(frozen=True)
class BridgeMessage:
    """A single framed message on the host↔guest link."""

    msg_type: MsgType
    correlation_id: str
    payload: str

    def encode(self) -> bytes:
        """Serialize to a newline-terminated UTF-8 line."""
        line = f"{self.msg_type.value}:{self.correlation_id}:{self.payload}\n"
        raw = line.encode("utf-8", errors="replace")
        if len(raw) > MAX_LINE_BYTES:
            raise ValueError(f"encoded message exceeds {MAX_LINE_BYTES} bytes")
        return raw

    @classmethod
    def decode(cls, raw: bytes) -> "BridgeMessage":
        """Parse a raw line into a BridgeMessage.

        Raises ValueError on any malformed input — callers must catch
        and treat the line as untrusted / tainted.
        """
        if len(raw) > MAX_LINE_BYTES:
            raise ValueError("line exceeds maximum length")
        text = raw.decode("utf-8", errors="replace").rstrip("\n\r")
        parts = text.split(":", 2)
        if len(parts) != 3:
            raise ValueError(f"expected 3 colon-separated fields, got {len(parts)}")
        type_str, corr_id, payload = parts
        try:
            msg_type = MsgType(type_str)
        except ValueError:
            raise ValueError(f"unknown message type: {type_str!r}")
        if not _CORR_RE.match(corr_id):
            raise ValueError(f"invalid correlation id: {corr_id!r}")
        return cls(msg_type=msg_type, correlation_id=corr_id, payload=payload)


def validate_correlation_id(corr_id: str) -> bool:
    """Return True if corr_id is well-formed."""
    return bool(_CORR_RE.match(corr_id))
