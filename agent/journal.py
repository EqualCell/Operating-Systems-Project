"""Durable journal of side-effecting requests  ("write-ahead" on the host).

WHY: the whole point of the kernel's idempotency key is that a RETRY carries
the SAME key. If the agent forgot its key when the host restarted or a reply
was lost, it would invent a new one and the effect would happen twice. So:

    1. generate the logical key ONCE,
    2. write {key, tool, args} to this journal and fsync   <- before sending,
    3. send (maybe many times, always the same key + args),
    4. record the final result.

A communication-attempt id (one per send) is NOT the logical key; attempts are
logged separately. The file is append-only JSON lines; an unterminated last
line is truncated and fsynced before another append; middle corruption fails closed.
"""
import copy
import fcntl
import json
import os
import secrets
import time
import uuid


def new_key():
    """Random non-zero 64-bit idempotency key (0 means 'empty slot' in the kernel)."""
    while True:
        k = secrets.randbits(64)
        if k:
            return k


class Journal:
    def __init__(self, path, keygen=new_key):
        self.path = path
        self.keygen = keygen
        self.ops = {}      # op id -> dict(key, tool, args, state, ...)
        self._load()

    # ---- persistence ----
    def _read_locked(self, f):
        self.ops = {}
        f.seek(0)
        offset = 0
        lines = f.readlines()
        for i, line in enumerate(lines):
            if not line.endswith(b"\n"):
                # Only an unterminated final record is recoverable. Even valid
                # JSON without its newline was never a complete journal record.
                if i != len(lines) - 1:
                    raise ValueError("unterminated middle journal record")
                f.truncate(offset)
                f.flush()
                os.fsync(f.fileno())
                break
            try:
                self._apply(json.loads(line))
            except (ValueError, KeyError, TypeError) as e:
                raise ValueError(f"corrupt journal at byte {offset}: {e}") from e
            offset += len(line)

    def _append(self, rec):
        rec = copy.deepcopy(rec)
        rec["ts"] = round(time.time(), 3)
        with open(self.path, "a+b") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            self._read_locked(f)
            self._apply(rec)  # validate references and transitions BEFORE write
            f.write((json.dumps(rec, sort_keys=True) + "\n").encode())
            f.flush()
            os.fsync(f.fileno())
        # Also persist the directory entry when this is a newly created file.
        fd = os.open(os.path.dirname(os.path.abspath(self.path)), os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def _load(self):
        self.ops = {}
        if not os.path.exists(self.path):
            return
        with open(self.path, "r+b") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            self._read_locked(f)

    def _apply(self, rec):
        ev, op = rec["ev"], rec["op"]
        if ev == "begin":
            if op in self.ops or not isinstance(rec["args"], dict):
                raise ValueError("duplicate begin or invalid arguments")
            key = int(rec["key"], 16)
            if not 0 < key < 2**64:
                raise ValueError("invalid request key")
            self.ops[op] = dict(op=op, key=rec["key"], tool=rec["tool"],
                                args=copy.deepcopy(rec["args"]), state="pending", attempts=0,
                                outcome=None, rc=None, reason=None,
                                grant_id=rec.get("grant_id"))
        elif ev in ("attempt", "result"):
            o = self.ops[op]  # unknown references are corruption, never ignored
            if o["state"] != "pending":
                raise ValueError("event after final result")
            if ev == "attempt":
                if not isinstance(rec["comm_id"], int):
                    raise ValueError("invalid attempt id")
                o["attempts"] += 1
            else:
                if rec["state"] not in ("done", "failed", "unknown"):
                    raise ValueError("invalid result state")
                if rec["state"] != "unknown":
                    o["state"] = rec["state"]
                o.update(outcome=rec.get("outcome"), rc=rec.get("rc"), reason=rec.get("reason"))
        else:
            raise ValueError("unknown journal event")

    # ---- API ----
    def begin(self, tool, args, grant_id=None):
        """Create a new logical request with a fresh key. Durable on return."""
        op = "op-" + uuid.uuid4().hex
        key = self.keygen()
        self._append(dict(ev="begin", op=op, key=f"0x{key:016x}", tool=tool, args=args, grant_id=grant_id))
        return self.ops[op]

    def attempt(self, op, comm_id):
        self._append(dict(ev="attempt", op=op, comm_id=comm_id))

    def result(self, op, state, outcome=None, rc=None, reason=None):
        """state: done | failed (final)  or  unknown (still pending)."""
        self._append(dict(ev="result", op=op, state=state, outcome=outcome, rc=rc, reason=reason))

    def pending(self):
        return [o for o in self.ops.values() if o["state"] == "pending"]
