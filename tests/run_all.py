#!/usr/bin/env python3
"""Run the test suite and write evidence.

    python3 tests/run_all.py                    # everything (except --slow ones)
    python3 tests/run_all.py --only B1 B2       # selected cases
    python3 tests/run_all.py --group crash      # one group
    python3 tests/run_all.py --list

Output:  evidence/<run-id>/results.json, results.md, <case>/*.log|*.img.gz
Exit status 0 only if every selected case PASSED.
"""
import argparse
import importlib
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.qemu import REPO  # noqa: E402
from tests import framework  # noqa: E402

MODULES = ["tests.cases.c_core", "tests.cases.c_crash", "tests.cases.c_agent", "tests.cases.c_measure", "tests.cases.c_regress"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--group", nargs="*")
    ap.add_argument("--slow", action="store_true", help="include slow cases (usertests regression)")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--out", default=None, help="evidence directory (default evidence/<timestamp>)")
    ap.add_argument("--img", default=os.path.join(REPO, "fs.img"))
    ap.add_argument("--kernel", default=os.path.join(REPO, "kernel", "kernel"))
    a = ap.parse_args()

    for m in MODULES:
        try:
            importlib.import_module(m)
        except ModuleNotFoundError as e:
            if e.name != m:
                raise
    specs = framework.REGISTRY
    if a.only:
        specs = [s for s in specs if s["id"] in a.only]
    if a.group:
        specs = [s for s in specs if s["group"] in a.group]
    if not a.slow and not a.only:
        specs = [s for s in specs if not s["slow"]]
    if a.list:
        for s in specs:
            print(f"{s['id']:8} {s['group']:12} {s['title']}")
        return 0

    out = a.out or os.path.join(REPO, "evidence", time.strftime("run-%Y%m%d-%H%M%S"))
    run = framework.Run(out, a.img, a.kernel)
    env = framework.environment(a.img, a.kernel)
    print(f"evidence -> {out}\n{len(specs)} cases")
    t0 = time.time()
    for s in specs:
        run.execute(s)
    import gzip
    import shutil
    with open(a.img, "rb") as f, gzip.open(os.path.join(out, "pristine-fs.img.gz"), "wb") as g:
        shutil.copyfileobj(f, g)          # base for every *.blockdiff.gz (see tools/restore_image.py)
    summary = run.write_reports(env, dict(total_seconds=round(time.time() - t0, 1)))
    print(f"\nPASS {summary['PASS']}  FAIL {summary['FAIL']}  ERROR {summary['ERROR']}   ({round(time.time()-t0,1)} s)\nreport: {out}/results.md")
    return 0 if summary["FAIL"] == 0 and summary["ERROR"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
