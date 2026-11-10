"""
Persistent client journal for durable pending-operation identity.

Every request the host dispatches is written to a JSON-lines journal
*before* it is sent to the guest.  The journal records:

  - correlation_id  (the request's unique identity)
  - tool_name       (which allowlisted tool)
  - arguments       (validated tool arguments)
  - status          (pending → completed | error | timeout | crash)
  - response        (the guest's reply, once received)

On host restart the journal is replayed: any request still in 'pending'
state is re-sent with the *same* correlation_id, so the guest kernel's
idempotency layer (effect_store) deduplicates it.  A fresh identity is
never generated for an ambiguous retry.
"""

from __future__ import annotations
import json
import os
import time
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional


class JournalEntry:
    """One logical request and its lifecycle."""

    __slots__ = (
        "correlation_id",
        "tool_name",
        "arguments",
        "status",
        "response",
        "created_at",
        "updated_at",
    )

    # Valid status values.
    PENDING = "pending"
    COMPLETED = "completed"
    ERROR = "error"
    TIMEOUT = "timeout"
    CRASH = "crash"

    def __init__(
        self,
        correlation_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        status: str = "pending",
        response: Optional[str] = None,
        created_at: Optional[float] = None,
        updated_at: Optional[float] = None,
    ):
        self.correlation_id = correlation_id
        self.tool_name = tool_name
        self.arguments = arguments
        self.status = status
        self.response = response
        self.created_at = created_at or time.time()
        self.updated_at = updated_at or self.created_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "correlation_id": self.correlation_id,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "status": self.status,
            "response": self.response,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "JournalEntry":
        return cls(**d)


class RequestJournal:
    """Append-only, crash-safe request journal backed by a JSONL file.

    Thread-safe: all mutations hold an internal lock and flush to disk
    before returning.
    """

    def __init__(self, path: str | Path):
        self._path = Path(path)
        self._lock = threading.Lock()
        self._entries: Dict[str, JournalEntry] = {}
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_request(
        self,
        correlation_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> JournalEntry:
        """Persist a new pending request *before* dispatching it."""
        entry = JournalEntry(
            correlation_id=correlation_id,
            tool_name=tool_name,
            arguments=arguments,
        )
        with self._lock:
            if correlation_id in self._entries:
                raise ValueError(
                    f"duplicate correlation_id: {correlation_id}"
                )
            self._entries[correlation_id] = entry
            self._append(entry)
        return entry

    def complete(
        self, correlation_id: str, response: str, status: str = JournalEntry.COMPLETED
    ) -> None:
        """Mark a pending request as completed (or error/timeout/crash)."""
        with self._lock:
            entry = self._entries.get(correlation_id)
            if entry is None:
                raise KeyError(f"unknown correlation_id: {correlation_id}")
            entry.status = status
            entry.response = response
            entry.updated_at = time.time()
            self._append(entry)

    def pending(self) -> List[JournalEntry]:
        """Return all entries still in 'pending' status."""
        with self._lock:
            return [
                e for e in self._entries.values() if e.status == JournalEntry.PENDING
            ]

    def get(self, correlation_id: str) -> Optional[JournalEntry]:
        with self._lock:
            return self._entries.get(correlation_id)

    def all_entries(self) -> List[JournalEntry]:
        with self._lock:
            return list(self._entries.values())

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Replay the JSONL file to reconstruct in-memory state.

        Because the file is append-only, later lines for the same
        correlation_id overwrite earlier ones (this is how status
        transitions are recorded).
        """
        if not self._path.exists():
            return
        with open(self._path, "r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    entry = JournalEntry.from_dict(d)
                    self._entries[entry.correlation_id] = entry
                except (json.JSONDecodeError, TypeError, KeyError) as exc:
                    # Corrupted line — skip but warn.
                    import sys
                    print(
                        f"journal: skipping corrupt line {lineno}: {exc}",
                        file=sys.stderr,
                    )

    def _append(self, entry: JournalEntry) -> None:
        """Append one JSON line and flush to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict(), separators=(",", ":")) + "\n")
            f.flush()
            os.fsync(f.fileno())
