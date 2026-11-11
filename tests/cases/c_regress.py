"""Regression and meta-tests (groups "regress" and "mutation")."""
import os
import shutil
import subprocess
import sys

from agent.qemu import REPO, setup_env
from tests import framework
from tests.framework import case, effect, stats, kv
from tests.lib.fsimage import Image
from tests.mutants import MUTANTS

IGNORE = shutil.ignore_patterns(".git", "evidence", "*.o", "*.d", "*.asm", "*.sym", "fs.img", "kernel/kernel",
                                "__pycache__", "mkfs/mkfs", "user/usys.S", "*.pyc", "runs", "_*")


def build_tree(ctx, name, extra_make="", edit=None):
    """Copy the source tree to a scratch dir, optionally edit it, build it."""
    dst = os.path.join("/tmp", f"xv6-{name}-{os.getpid()}")
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(REPO, dst, ignore=IGNORE)
    if edit:
        edit(dst)
    env = setup_env()
    env["TOOLPREFIX"] = "riscv64-linux-gnu-"
    p = subprocess.run(f"make -j8 {extra_make} kernel/kernel fs.img", shell=True, cwd=dst, env=env,
                       capture_output=True, text=True)
    with open(os.path.join(ctx.dir, f"build-{name}.log"), "w") as f:
        f.write(p.stdout + p.stderr)
    return dst, p.returncode


@case("U1", "Host-only unit tests (validator, parser, journal, planners)", "unit")
def u1(ctx):
    p = subprocess.run([sys.executable, "-m", "unittest", "tests.unit.test_agent_units", "-v"], cwd=REPO,
                       capture_output=True, text=True)
    out = p.stdout + p.stderr
    with open(os.path.join(ctx.dir, "unittest.log"), "w") as f:
        f.write(out)
    ran = [l for l in out.splitlines() if l.startswith("Ran ")]
    ctx.param(unittest_summary=ran[0] if ran else "?")
    ctx.check("unittest exit status", 0, p.returncode)
    ctx.check("at least 20 unit tests ran", True, bool(ran) and int(ran[0].split()[1]) >= 20)


@case("R1", "Regression: stock xv6 `usertests -q` still passes with our kernel changes (3 CPUs)", "regress", slow=True,
      params=dict(cpus=3))
def r1(ctx):
    img = ctx.new_image()
    vm = ctx.boot(img, "usertests", cpus=3)
    out, st = ctx.sh(vm, "usertests -q", timeout=1500)
    ctx.check("usertests finished", "ok", st)
    ctx.check("ALL TESTS PASSED", True, "ALL TESTS PASSED" in out)
    ctx.note(out.strip().splitlines()[-1] if out.strip() else "(no output)")
    vm.kill()
    ctx.check("image consistent afterwards", [], Image.load(img).with_log_replayed().check_consistency())


@case("R2", "Production build (TESTHOOKS=0): crash hooks compiled out and refused; effect() still works", "regress")
def r2(ctx):
    tree, rc = build_tree(ctx, "prod", "TESTHOOKS=0")
    ctx.check("production build succeeds", 0, rc)
    kern, img0 = os.path.join(tree, "kernel/kernel"), os.path.join(tree, "fs.img")
    data = open(kern, "rb").read()
    ctx.check("no crash-injection strings in the production kernel binary", False, b"injected crash" in data)
    img = os.path.join(ctx.dir, "prod.img")
    shutil.copy(img0, img)
    vm = ctx.boot(img, "prod", kernel=kern)
    out, _ = ctx.sh(vm, "crashctl at 1")
    ctx.check("crashat refused with EFF_EPERM (-7)", "CRASHCTL rc=-7", out.strip())
    out, _ = ctx.sh(vm, "crashctl stage 2 1")
    ctx.check("crashhook refused with EFF_EPERM (-7)", "CRASHCTL rc=-7", out.strip())
    r = effect(ctx, vm, "append", "0x1", "/log.txt", "prod")
    r2_ = effect(ctx, vm, "append", "0x1", "/log.txt", "prod")
    ctx.check("effect() works in the production kernel (EXECUTED then REPLAYED)", ("EXECUTED", "REPLAYED"), (r["outcome"], r2_["outcome"]))
    vm.kill()
    ctx.check("file has the text once", b"boot-entry-0\nprod", Image.load(img).with_log_replayed().read_file("/log.txt"))
    shutil.rmtree(tree, ignore_errors=True)


def _make_mutant_case(mname):
    desc, fname, edits, must_fail = MUTANTS[mname]

    @case(f"M-{mname}", f"MUTANT '{mname}': {desc} -> the suite must FAIL", "mutation",
          params=dict(mutated_file=fname, caught_by=",".join(must_fail)))
    def _m(ctx):
        def edit(dst):
            p = os.path.join(dst, fname)
            s = open(p).read()
            for old, new in edits:
                assert old in s, f"mutant edit target not found: {old[:50]!r}"
                s = s.replace(old, new, 1)
            open(p, "w").write(s)
        tree, rc = build_tree(ctx, mname, "", edit)
        ctx.check("mutant kernel builds", 0, rc)
        sub = framework.Run(os.path.join(ctx.dir, "inner"), os.path.join(tree, "fs.img"), os.path.join(tree, "kernel/kernel"))
        rows = []
        for spec in list(framework.REGISTRY):
            if spec["id"] in must_fail:
                res = sub.execute(spec, verbose=False)
                bad = [c["name"] for c in res["checks"] if not c["pass_"]]
                rows.append(dict(test=spec["id"], result=res["result"], failed_checks=len(bad), first_failed=(bad[0] if bad else "")))
                ctx.check(f"test {spec['id']} detects the bug (result != PASS)", True, res["result"] != "PASS")
        ctx.table("the same test run against the BROKEN kernel", rows)
        shutil.rmtree(tree, ignore_errors=True)
    return _m


for _name in MUTANTS:
    _make_mutant_case(_name)
