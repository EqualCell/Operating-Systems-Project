"""The agent loop:  goal -> planner -> VALIDATOR -> tool -> observation -> planner.

Every step is appended to `self.trace` (the evidence the handout asks for):
request, proposed tool call, validated call or refusal, guest command,
guest output, observation. Side-effecting calls go through the journal so a
lost reply or a crash is retried with the SAME key and arguments.
"""
import re

from . import config
from .bridge import GuestBridge
from .journal import Journal
from .planner import Obs, RulePlanner
from .tools import ValidationError, is_side_effect, validate_action


def summarize_text(text, max_sentences=2):
    """Tiny deterministic host-side 'summarizer': the first sentences, trimmed."""
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+|\n+", text) if p.strip()]
    return " ".join(parts[:max_sentences])


class Report:
    def __init__(self, goal):
        self.goal = goal
        self.outcome = "OK"        # OK | REFUSED | PENDING | ERROR | UNSUPPORTED
        self.final = ""
        self.refusals = []         # ValidationError.code list
        self.effects = []          # journal ops touched by this goal

    def as_dict(self):
        return dict(goal=self.goal, outcome=self.outcome, final=self.final,
                    refusals=self.refusals, effects=self.effects)


class Agent:
    def __init__(self, bridge: GuestBridge, journal: Journal, planner=None):
        self.bridge = bridge
        self.journal = journal
        self.planner = planner or RulePlanner()
        self.trace = []

    def _log(self, kind, **kw):
        self.trace.append(dict(kind=kind, **kw))

    # ------------------------------------------------------------------
    def handle(self, goal):
        rep = Report(goal)
        self._log("request", goal=goal)
        gen = self.planner.plan(goal)
        try:
            proposed = next(gen)
        except StopIteration:
            rep.outcome, rep.final = "UNSUPPORTED", "unsupported request"
            self._log("unsupported", goal=goal)
            return rep
        while True:
            self._log("proposed", action=proposed)
            try:
                action = validate_action(proposed)
            except ValidationError as e:
                self._log("refused", code=e.code, message=e.message, action=proposed)
                rep.refusals.append(e.code)
                rep.outcome = "REFUSED"
                obs = Obs(False, f"REFUSED: {e.code}", refused=True)
            else:
                self._log("validated", action=action)
                obs = self._execute(action, rep)
                if obs.meta.get("pending"):
                    rep.outcome = "PENDING"
            rep.final = obs.text
            try:
                proposed = gen.send(obs)
            except StopIteration:
                break
        self._log("done", outcome=rep.outcome, final=rep.final)
        return rep

    # ------------------------------------------------------------------
    def _execute(self, action, rep):
        tool, args = action["tool"], action["args"]
        if tool == "summarize":
            s = summarize_text(args["text"])
            self._log("observation", tool=tool, text=s)
            return Obs(True, s)
        if is_side_effect(tool):
            return self._execute_effect(tool, args, rep)
        reply = self.bridge.call(tool, args)
        self._log("guest", tool=tool, reply=reply.as_dict())
        if reply.status == "OK":
            return Obs(True, reply.text)
        return Obs(False, f"{reply.status}: {reply.reason or reply.guest_status}")

    def _execute_effect(self, tool, args, rep):
        # 1. key + arguments are made DURABLE before the first send
        op = self.journal.begin(tool, args)
        rep.effects.append(op["op"])
        self._log("journal-begin", op=op["op"], key=op["key"], tool=tool, args=args)
        return self._drive(op, rep)

    def _drive(self, op, rep=None):
        key = int(op["key"], 16)
        for attempt in range(1, config.MAX_ATTEMPTS + 1):
            self.bridge.recover()                     # reboot guest (same disk) if it died
            reply = self.bridge.call(op["tool"], op["args"], key=key)
            self.journal.attempt(op["op"], reply.comm_id)
            self._log("guest", op=op["op"], attempt=attempt, key=op["key"], reply=reply.as_dict())
            if reply.status == "OK":
                self.journal.result(op["op"], "done", outcome=reply.outcome, rc=reply.rc)
                return Obs(True, f"{op['tool']} {reply.outcome} rc={reply.rc} key={op['key']}",
                           op=op["op"], outcome=reply.outcome, rc=reply.rc, attempts=attempt)
            if reply.status == "ERR":                 # definitive: kernel/guest said no
                self.journal.result(op["op"], "failed", outcome=reply.guest_status, rc=reply.rc)
                return Obs(False, f"{op['tool']} FAILED {reply.guest_status} rc={reply.rc}",
                           op=op["op"], rc=reply.rc, attempts=attempt)
            # UNKNOWN: lost reply / crash / timeout. Effect may or may not have
            # happened. Do NOT call this failure; retry with the SAME key.
            self.journal.result(op["op"], "unknown", reason=reply.reason)
        return Obs(False, f"{op['tool']} PENDING key={op['key']} (outcome unknown after "
                          f"{config.MAX_ATTEMPTS} attempts; resume to retry with the same key)",
                   op=op["op"], pending=True)

    def resume(self):
        """Retry every journaled request that never reached a final state."""
        results = []
        for op in self.journal.pending():
            self._log("resume", op=op["op"], key=op["key"])
            results.append((op["op"], self._drive(op)))
        return results
