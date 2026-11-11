#!/usr/bin/env python3
"""End-to-end demonstration (plan section 10), narrated.

  python3 demo.py                 # crash AFTER the commit point (default)
  python3 demo.py --crash pre     # crash BEFORE the commit point
  python3 demo.py --crash lost    # no crash: the reply is simply lost
  python3 demo.py --crash none    # happy path

Everything is real: QEMU + xv6 + our kernel, the Python agent, the bridge, the
agentcall utility and the effect() syscall. The crash hooks are armed from the
test console, NOT through the agent (the agent has no tool for that).
"""
import argparse
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent.agent import Agent  # noqa: E402
from agent.bridge import GuestBridge  # noqa: E402
from agent.journal import Journal  # noqa: E402
from agent.planner import InjectionTestPlanner, RulePlanner  # noqa: E402
from tests.lib.fsimage import Image, entries_by_key  # noqa: E402

REPO = os.path.dirname(os.path.abspath(__file__))


def say(n, text):
    print(f"\n=== {n}. {text}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--crash", choices=["post", "pre", "lost", "none"], default="post")
    ap.add_argument("--workdir", default=os.path.join(REPO, "runs", "demo"))
    a = ap.parse_args()
    shutil.rmtree(a.workdir, ignore_errors=True)
    os.makedirs(a.workdir)
    img = os.path.join(a.workdir, "demo.img")
    shutil.copy(os.path.join(REPO, "fs.img"), img)          # the ONE disk used for the whole demo
    journal = os.path.join(a.workdir, "journal.jsonl")

    with GuestBridge(img, log_dir=a.workdir) as bridge:
        agent = Agent(bridge, Journal(journal), RulePlanner())

        say(1, "xv6 is booted in QEMU (kernel with effect(), persistent table, crashat/crashhook)")
        say(2, "/log.txt initially contains a known value")
        print(agent.handle("read /log.txt").final)

        say(3, "User asks the agent:  append demo-entry to /log.txt")
        if a.crash in ("post", "pre"):
            arm = "crashctl stage 2" if a.crash == "post" else "crashctl at 2"
            where = ("AFTER the commit point (log header durable, blocks not yet installed)" if a.crash == "post"
                     else "BEFORE the commit point (nothing durable yet)")
            print(f"    [test console] arming a kernel crash {where}: `{arm}`")
            bridge.vm.run(arm)
        elif a.crash == "lost":
            print("    [test fault] the reply of the first attempt will be dropped")
            bridge.drop_replies = 1
        rep = agent.handle("append demo-entry to /log.txt")

        say(4, "Structured tool call, validation, and what the bridge/guest did")
        for t in agent.trace:
            k = t["kind"]
            if k in ("proposed", "validated"):
                print(f"    {k:10} {t['action']}")
            elif k == "journal-begin":
                print(f"    journal    op={t['op']} key={t['key']} saved BEFORE sending")
            elif k == "guest":
                r = t["reply"]
                print(f"    guest      attempt={t.get('attempt')} status={r['status']:7} outcome={r['outcome']} {r['reason']}")
        print(f"    [bridge] guest boots so far: {bridge.boots} (every extra boot = power-cycle on the SAME disk)")

        say(5, "Result of the agent run")
        print(f"    {rep.final}   [outcome={rep.outcome}]")

        say(6, "/log.txt read back through the agent: the entry appears EXACTLY ONCE")
        print(agent.handle("read /log.txt").final)

    f = Image.load(img).with_log_replayed()
    key = int(agent.journal.ops["op-0001"]["key"], 16)
    say(7, "Independent check straight from the disk image (no kernel, no agent involved)")
    print(f"    /log.txt bytes     : {f.read_file('/log.txt')!r}")
    print(f"    table entry for key: {entries_by_key(f).get(key)}")
    print(f"    fs consistency     : {f.check_consistency() or 'OK'}")
    ok = f.read_file("/log.txt") == b"boot-entry-0\ndemo-entry" and len(f.table()) == 1
    print("    => exactly once: " + ("YES" if ok else "NO  <-- BUG"))

    say(8, "Prompt injection: summarize /inbox.txt with a deliberately gullible planner")
    with GuestBridge(img, log_dir=a.workdir) as b2:
        ag2 = Agent(b2, Journal(journal), InjectionTestPlanner())
        r2 = ag2.handle("summarize /inbox.txt")
        for t in ag2.trace:
            if t["kind"] in ("proposed", "refused"):
                print(f"    {t['kind']:9} {t.get('action')}  {t.get('code', '')}")
        print(f"    agent outcome: {r2.outcome}")
        ag2.planner = RulePlanner()
        print("    /important.txt still there ->", ag2.handle("read /important.txt").final.strip())
    print("    LABEL: tool-layer refusal (allowlist). NOT kernel taint enforcement (out of scope for this milestone).")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
