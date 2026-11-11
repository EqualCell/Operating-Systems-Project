"""Planners turn a user goal into structured tool calls (never shell text).

A planner is a GENERATOR: it yields one action at a time and receives the
observation of the previous action through .send(). This is the loop of the
agent handout (planner -> validator -> tool -> observation -> planner).

Rules first: RulePlanner is fully deterministic. An LLM planner could be
dropped in later without touching anything else, as long as it yields the same
structured actions. (Not implemented: handout says "LLM only after tools work".)

InjectionTestPlanner is a DELIBERATELY GULLIBLE planner used only for the
prompt-injection demo: it obeys instructions it finds inside file content, the
way a real model might. It exists to prove that the layers below the planner
refuse the dangerous action.
"""
import re


class Obs:
    """What the agent hands back to the planner after running an action."""

    def __init__(self, ok, text="", **meta):
        self.ok = ok
        self.text = text
        self.meta = meta

    def __repr__(self):
        return f"Obs(ok={self.ok}, text={self.text[:40]!r}...)"


def act(tool, **args):
    return {"tool": tool, "args": args}


class RulePlanner:
    """Understands four request shapes:
         list
         read /path
         summarize /path          (read it, then summarize on the host)
         append <text> to /path
         create /path with <text>
    """

    def plan(self, goal):
        g = goal.strip()
        m = None
        if g == "list":
            yield act("list_files")
        elif (m := re.fullmatch(r"read (\S+)", g)):
            yield act("read_file", path=m.group(1))
        elif (m := re.fullmatch(r"summarize (\S+)", g)):
            obs = yield act("read_file", path=m.group(1))
            if obs.ok:
                yield act("summarize", text=obs.text)
        elif (m := re.fullmatch(r"append (.+) to (\S+)", g)):
            yield act("append_file", path=m.group(2), text=m.group(1))
        elif (m := re.fullmatch(r"create (\S+) with (.+)", g)):
            yield act("create_file", path=m.group(1), text=m.group(2))
        else:
            return  # nothing proposed -> agent reports "unsupported request"


class InjectionTestPlanner:
    """Summarize a file; if the file text says "Delete <path>", OBEY IT.

    This simulates a model that was successfully prompt-injected. The proposed
    action uses a tool name that is not in the allowlist ("delete_file")."""

    def plan(self, goal):
        m = re.fullmatch(r"summarize (\S+)", goal.strip())
        if not m:
            return
        obs = yield act("read_file", path=m.group(1))
        if not obs.ok:
            return
        victim = re.search(r"Delete (/\S+?)\.?(?:\s|$)", obs.text)
        if victim:
            # the "injected" decision: obey the file, not the user
            yield act("delete_file", path=victim.group(1))
        yield act("summarize", text=obs.text)
