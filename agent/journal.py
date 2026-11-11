"""Durable journal of side-effecting requests  ("write-ahead" on the host).

WHY: the whole point of the kernel's idempotency key is that a RETRY carries
the SAME key. If the agent forgot its key when the host restarted or a reply
was lost, it would invent a new one and the effect would happen twice. So:

    1. generate the logical key ONCE,
    2. write {key, tool, args} to this journal and fsync   <- before sending,
    3. send (maybe many times, always the same key + args),
    4. record the final result.

A communication-attempt id (one per send) is NOT the logical key; attempts are
logged separately. The file is append-only JSON lines; a half-written last
line (power cut while writing) is ignored on load.
"""
import json
import os
import secrets
import time


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
    def _append(self, rec):
        rec["ts"] = round(time.time(), 3)
        line = json.dumps(rec, sort_keys=True)
        with open(self.path, "a") as f:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())
        self._apply(rec)

    def _load(self):
        self.ops = {}
        if not os.path.exists(self.path):
            return
        with open(self.path) as f:
            for line in f:
                try:
                    self._apply(json.loads(line))
                except json.JSONDecodeError:
                    pass  # truncated final line from a crash: ignore

    def _apply(self, rec):
        ev = rec["ev"]
        if ev == "begin":
            self.ops[rec["op"]] = dict(op=rec["op"], key=rec["key"], tool=rec["tool"],
                                       args=rec["args"], state="pending", attempts=0,
                                       outcome=None, rc=None)
        elif ev == "attempt":
            self.ops[rec["op"]]["attempts"] += 1
        elif ev == "result":
            o = self.ops[rec["op"]]
            if rec["state"] in ("done", "failed"):
                o["state"] = rec["state"]
            o["outcome"] = rec.get("outcome")
            o["rc"] = rec.get("rc")

    # ---- API ----
    def begin(self, tool, args):
        """Create a new logical request with a fresh key. Durable on return."""
        op = f"op-{len(self.ops) + 1:04d}"
        key = self.keygen()
        self._append(dict(ev="begin", op=op, key=f"0x{key:016x}", tool=tool, args=args))
        return self.ops[op]

    def attempt(self, op, comm_id):
        self._append(dict(ev="attempt", op=op, comm_id=comm_id))

    def result(self, op, state, outcome=None, rc=None, reason=None):
        """state: done | failed (final)  or  unknown (still pending)."""
        self._append(dict(ev="result", op=op, state=state, outcome=outcome, rc=rc, reason=reason))

    def pending(self):
        return [o for o in self.ops.values() if o["state"] == "pending"]
