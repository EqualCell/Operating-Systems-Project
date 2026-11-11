"""Tiny test framework that RECORDS EVERYTHING.

A test case is a function  fn(ctx)  registered with @case(...).  Through `ctx`
it boots VMs, runs guest commands and calls ctx.check(name, expected, observed).
The framework stores, for every case:
    parameters, every guest command + raw output, every check
    (expected / observed / pass), timing, raw QEMU serial logs, artifacts.
and writes   evidence/<run-id>/results.json   and   results.md.
"""
import gzip
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import traceback

from agent.qemu import REPO, VM, qemu_path, setup_env
from tests.lib.fsimage import Image

REGISTRY = []


def case(cid, title, group, params=None, slow=False):
    """Register a test case."""
    def deco(fn):
        REGISTRY.append(dict(id=cid, title=title, group=group, fn=fn,
                             params=params or {}, slow=slow))
        return fn
    return deco


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _sh(cmd, **kw):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30, env=setup_env(), **kw).stdout.strip()
    except Exception as e:  # noqa
        return f"unavailable ({e})"


def environment(pristine_img, kernel):
    files = ["kernel/effect.c", "kernel/effect_store.c", "kernel/effect_ops.c", "kernel/effect.h",
             "kernel/log.c", "kernel/fs.h", "mkfs/mkfs.c", "kernel/sysfile.c", "kernel/fs.c", "kernel/bio.c"]
    return dict(
        date=time.strftime("%Y-%m-%d %H:%M:%S"),
        host=platform.platform(), python=sys.version.split()[0],
        qemu=_sh([qemu_path(), "--version"]).splitlines()[0],
        riscv_gcc=_sh(["riscv64-linux-gnu-gcc", "--version"]).splitlines()[0],
        xv6_base_commit=_sh(["git", "-C", REPO, "rev-parse", "HEAD"]),
        git_dirty_files=len(_sh(["git", "-C", REPO, "status", "--porcelain"]).splitlines()),
        kernel_sha256=sha256(kernel), pristine_fs_img_sha256=sha256(pristine_img),
        source_sha256={f: sha256(os.path.join(REPO, f)) for f in files},
        qemu_machine="virt, -bios none, 128M, virtio-blk (legacy off)",
    )


class Ctx:
    def __init__(self, run, spec):
        self.run = run
        self.spec = spec
        self.id = spec["id"]
        self.dir = os.path.join(run.dir, self.id)
        os.makedirs(self.dir, exist_ok=True)
        self.params = dict(spec["params"])
        self.steps, self.checks, self.notes, self.boots = [], [], [], []
        self.tables = []
        self.vms = []
        self.kernel = run.kernel

    # ---- parameters / notes ----
    def param(self, **kw):
        self.params.update(kw)

    def note(self, text):
        self.notes.append(text)

    def table(self, name, rows):
        """Structured per-row evidence (e.g. one row per crash point)."""
        self.tables.append(dict(name=name, rows=rows))

    # ---- images & VMs ----
    def new_image(self, name="disk"):
        """A fresh copy of the pristine fs.img (clean fixture for a NEW independent trial)."""
        path = os.path.join(self.dir, f"{name}.img")
        shutil.copy(self.run.pristine, path)
        return path

    def boot(self, img, label, cpus=1, kernel=None):
        log = os.path.join(self.dir, f"{label}.qemu.log")
        vm = VM(img, kernel=kernel or self.kernel, cpus=cpus, log_path=log)
        vm.boot()
        self.vms.append(vm)
        self.boots.append(dict(label=label, cpus=cpus, boot_seconds=vm.boot_seconds,
                               image=os.path.basename(img), log=os.path.basename(log),
                               qemu_cmdline=" ".join(vm.cmdline)))
        return vm

    def sh(self, vm, cmd, timeout=30, label=None):
        out, status = vm.run(cmd, timeout=timeout)
        self.steps.append(dict(vm=label or os.path.basename(vm.img), cmd=cmd, status=status, output=out))
        return out, status

    def archive_diff(self, img, name):
        """Keep only the blocks that differ from the pristine image (small),
        and PROVE it is lossless by reconstructing the image from the diff."""
        from tests.lib.fsimage import make_diff, apply_diff
        dst = os.path.join(self.dir, name + ".blockdiff.gz")
        make_diff(self.run.pristine, img, dst)
        with open(img, "rb") as f:
            original = f.read()
        if apply_diff(self.run.pristine, dst) != original:
            raise RuntimeError("block-diff archive is not lossless")

    def archive(self, img, name):
        """Keep a gzip of an image as evidence (e.g. the post-crash disk)."""
        dst = os.path.join(self.dir, name + ".img.gz")
        with open(img, "rb") as f, gzip.open(dst, "wb") as g:
            shutil.copyfileobj(f, g)

    # ---- checks ----
    def check(self, name, expected, observed, ok=None):
        ok = (expected == observed) if ok is None else bool(ok)
        self.checks.append(dict(name=name, expected=repr(expected), observed=repr(observed), pass_=ok))
        return ok

    def compact_images(self):
        """Replace every working disk image by a lossless block-diff against the
        pristine image (a full image is 2 MB; the diff is a few KB)."""
        import glob
        for img in glob.glob(os.path.join(self.dir, "*.img")):
            name = os.path.basename(img)[:-4]
            try:
                self.archive_diff(img, name + ".final")
            finally:
                os.remove(img)

    def finish_vms(self):
        for vm in self.vms:
            vm.kill()


class Run:
    def __init__(self, outdir, pristine, kernel):
        self.dir = outdir
        os.makedirs(outdir, exist_ok=True)
        self.pristine = pristine
        self.kernel = kernel
        self.results = []

    def execute(self, spec, verbose=True):
        ctx = Ctx(self, spec)
        t0 = time.time()
        status, err = "PASS", None
        try:
            spec["fn"](ctx)
            if not ctx.checks:
                status, err = "ERROR", "case made no checks"
            elif not all(c["pass_"] for c in ctx.checks):
                status = "FAIL"
        except Exception:
            status, err = "ERROR", traceback.format_exc()
        finally:
            ctx.finish_vms()
            try:
                ctx.compact_images()
            except Exception:  # never let evidence compaction hide a test verdict
                err = (err or "") + "\n(image compaction failed)\n" + traceback.format_exc()
        res = dict(id=ctx.id, title=spec["title"], group=spec["group"], result=status,
                   seconds=round(time.time() - t0, 2), params=ctx.params, boots=ctx.boots,
                   steps=ctx.steps, checks=ctx.checks, notes=ctx.notes, tables=ctx.tables, error=err)
        self.results.append(res)
        if verbose:
            bad = [c["name"] for c in ctx.checks if not c["pass_"]]
            print(f"  [{status:5}] {ctx.id:<8} {spec['title']}  ({res['seconds']}s)" + (f"  FAILED CHECKS: {bad}" if bad else ""))
            if err:
                print(err)
        with open(os.path.join(ctx.dir, "case.json"), "w") as f:
            json.dump(res, f, indent=1)
        return res

    def write_reports(self, env, extra=None):
        summary = {s: sum(r["result"] == s for r in self.results) for s in ("PASS", "FAIL", "ERROR")}
        doc = dict(environment=env, summary=summary, results=self.results, **(extra or {}))
        with open(os.path.join(self.dir, "results.json"), "w") as f:
            json.dump(doc, f, indent=1)
        md = ["# Test results", "", f"Run: `{os.path.basename(self.dir)}`  ", f"**PASS {summary['PASS']} / FAIL {summary['FAIL']} / ERROR {summary['ERROR']}**  (total {len(self.results)})", "",
              "## Environment", ""]
        for k, v in env.items():
            if k != "source_sha256":
                md.append(f"- **{k}**: `{v}`")
        md += ["", "## Cases", "", "| ID | Group | Title | Params | Result | Checks (pass/total) | s |", "|---|---|---|---|---|---|---|"]
        for r in self.results:
            p = ", ".join(f"{k}={v}" for k, v in r["params"].items())
            ok = sum(c["pass_"] for c in r["checks"])
            md.append(f"| {r['id']} | {r['group']} | {r['title']} | {p} | **{r['result']}** | {ok}/{len(r['checks'])} | {r['seconds']} |")
        md += ["", "## Check detail (expected vs observed)", ""]
        for r in self.results:
            md += [f"### {r['id']} — {r['title']}  [{r['result']}]", ""]
            for n in r["notes"]:
                md.append(f"> {n}")
            md += ["", "| check | expected | observed | ok |", "|---|---|---|---|"]
            for c in r["checks"]:
                md.append(f"| {c['name']} | `{c['expected'][:80]}` | `{c['observed'][:80]}` | {'✔' if c['pass_'] else '✘'} |")
            md.append("")
            for t in r.get("tables", []):
                if not t["rows"]:
                    continue
                cols = list(t["rows"][0].keys())
                md += [f"**{t['name']}**", "", "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
                for row in t["rows"]:
                    md.append("| " + " | ".join(str(row.get(c, "")) for c in cols) + " |")
                md.append("")
        with open(os.path.join(self.dir, "results.md"), "w") as f:
            f.write("\n".join(md))
        return summary


# ---------------------------------------------------------------------------
# helpers shared by the case files
# ---------------------------------------------------------------------------
def kv(line):
    import re
    return dict(re.findall(r"(\w+)=(\S+)", line or ""))


def effect(ctx, vm, op, key, path, text, arm="", timeout=30, label=None):
    """Run `effectctl` and return the parsed EFFECT line (dict) + status."""
    cmd = f"effectctl {arm} {op} {key} {path} {text}".replace("  ", " ")
    out, status = ctx.sh(vm, cmd, timeout=timeout, label=label)
    line = next((l for l in out.splitlines() if l.startswith("EFFECT")), None)
    d = kv(line)
    d["status"] = status
    d["raw"] = out
    d["rc"] = int(d["rc"]) if "rc" in d else None
    return d


def stats(ctx, vm, label=None):
    out, status = ctx.sh(vm, "effstat", label=label)
    line = next((l for l in out.splitlines() if l.startswith("EFFSTAT")), "")
    return {k: int(v) for k, v in kv(line).items()}


def cat(ctx, vm, path):
    out, _ = ctx.sh(vm, f"cat {path}")
    return out


def count(hay, needle):
    return hay.count(needle)
