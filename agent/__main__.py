"""Command line:   python3 -m agent --img work.img "list"
                  python3 -m agent --img work.img "append hello to /log.txt"
                  python3 -m agent --img work.img --resume
The image is used IN PLACE (copy fs.img first if you want a disposable disk)."""
import argparse
import json
import os
import sys

from .agent import Agent
from .bridge import GuestBridge
from .journal import Journal
from .planner import InjectionTestPlanner, RulePlanner


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m agent")
    ap.add_argument("--img", required=True, help="xv6 disk image (used in place)")
    ap.add_argument("--kernel", default=None)
    ap.add_argument("--journal", default="agent-journal.jsonl")
    ap.add_argument("--cpus", type=int, default=1)
    ap.add_argument("--planner", choices=["rule", "injection"], default="rule",
                    help="'injection' = deliberately gullible test planner")
    ap.add_argument("--trace-out", default=None, help="write the full audit trace (JSON)")
    ap.add_argument("--log-dir", default=None, help="keep raw QEMU console logs here")
    ap.add_argument("--resume", action="store_true", help="retry pending journaled requests")
    ap.add_argument("goal", nargs="*", help='e.g. "list", "read /report.txt", "append hi to /log.txt"')
    a = ap.parse_args(argv)

    planner = InjectionTestPlanner() if a.planner == "injection" else RulePlanner()
    with GuestBridge(a.img, kernel=a.kernel, cpus=a.cpus, log_dir=a.log_dir) as bridge:
        agent = Agent(bridge, Journal(a.journal), planner)
        code = 0
        if a.resume:
            for op, obs in agent.resume():
                print(f"resume {op}: {obs.text}")
        if a.goal:
            rep = agent.handle(" ".join(a.goal))
            print(rep.final)
            print(f"[outcome={rep.outcome} refusals={rep.refusals} effects={rep.effects}]")
            code = 0 if rep.outcome == "OK" else 1
        if a.trace_out:
            with open(a.trace_out, "w") as f:
                json.dump(agent.trace, f, indent=1)
    return code


if __name__ == "__main__":
    sys.exit(main())
