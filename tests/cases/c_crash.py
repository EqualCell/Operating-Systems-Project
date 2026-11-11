"""Crash / reboot / replay cases (group "crash").

ONE TRIAL (all on the SAME disk image; the image is never recreated between
the crash and the replay -- only each new trial starts from a clean fixture):

   1. fresh image  ->  boot  ->  arm a crash  ->  effect(key,...)  -> PANIC
   2. power cut (SIGKILL).  Parse the dead disk with the independent checker:
        - which log state did the crash leave?  (header n == 0: uncommitted)
        - apply the log in memory = what recovery will produce
        - ATOMICITY: file effect present  <=>  table entry present
   3. reboot the SAME image  (xv6 recovery runs in initlog at boot)
   4. replay the SAME key + arguments  (twice)
   5. final disk: effect appears EXACTLY ONCE (never 0, never 2), table has the
      key once, filesystem consistent, log empty.

Crash points
   crashat(n)         n = 1 .. K     K = number of log_write() calls of one effect
                                     (all BEFORE the commit point)
   crashhook stage 1  log blocks written, header not yet           (uncommitted)
   crashhook stage 2  header durable = the commit point            (committed)
   crashhook stage 3  after the h-th home-block write, h = 1 .. L  (committed)
   crashhook stage 4  all blocks installed, log header not cleared (committed)
   control            first n beyond the last point: no crash happens
"""
import os

from tests.framework import case, effect, stats, kv
from tests.lib.fsimage import Image, entries_by_key

INIT_LOG = b"boot-entry-0\n"
INIT_EDGE = (b"E" * 19 + b"\n") * 51

SCEN = {
    "append-inblock":    dict(op="append", path="/log.txt",  text="CRASH-PAYLOAD", initial=INIT_LOG),
    "append-crossblock": dict(op="append", path="/edge.txt", text="0123456789",    initial=INIT_EDGE),
    "create":            dict(op="create", path="/made.txt", text="fresh-file",    initial=None),
    # file of 12280 B (11.99 blocks): a 40-byte append crosses from the last DIRECT
    # block into the INDIRECT area -> allocates indirect block + data block + bitmap
    "append-indirect":   dict(op="append", path="/big.txt",  text="0123456789012345678901234567890123456789", initial=(b"B" * 19 + b"\n") * 614),
}
KEY = "0xC0FFEE0000000001"


def expected_final(sc):
    return sc["text"].encode() if sc["initial"] is None else sc["initial"] + sc["text"].encode()


def effect_present(img, sc):
    data = img.read_file(sc["path"])
    if sc["initial"] is None:
        return data == sc["text"].encode()
    return data == expected_final(sc)


def measure(ctx, sc, cpus):
    """Run the effect once with no crash to learn K (log_write calls) and L (blocks)."""
    img = ctx.new_image("measure")
    vm = ctx.boot(img, "measure", cpus=cpus)
    r = effect(ctx, vm, sc["op"], KEY, sc["path"], sc["text"])
    s = stats(ctx, vm)
    vm.kill()
    assert r["outcome"] == "EXECUTED", r
    return s["last_logwrites"], s["last_logged"], s["last_diskwrites"]


def trial(ctx, name, sc, arm, expect_commit, cpus=1):
    """Run one crash trial; return a result row (dict) and add nothing to checks."""
    img = ctx.new_image(name)
    ino0 = os.stat(img).st_ino
    problems = []
    row = dict(trial=name, arm=arm or "(control: no crash)")

    vm1 = ctx.boot(img, f"{name}.run1", cpus=cpus)
    r1 = effect(ctx, vm1, sc["op"], KEY, sc["path"], sc["text"], arm=arm or "", timeout=20, label=f"{name}.run1")
    crashed = r1["status"] == "panic"
    row["crashed"] = crashed
    vm1.kill()

    # ---- the dead disk, before any recovery ----
    raw = Image.load(img)
    ctx.archive_diff(img, f"{name}.postcrash")
    log_n, log_blocks = raw.log_header()
    view = raw.with_log_replayed()                # in-memory emulation of recovery
    v_effect, v_key = effect_present(view, sc), (int(KEY, 16) in entries_by_key(view))
    row.update(log_n=log_n, view_effect=v_effect, view_key=v_key)
    if v_effect != v_key:
        problems.append(f"ATOMICITY VIOLATED (effect={v_effect} key={v_key})")
    committed_view = v_effect and v_key
    if expect_commit is not None and committed_view != expect_commit:
        problems.append(f"expected committed={expect_commit} got {committed_view}")
    if not crashed and r1["outcome"] != "EXECUTED":
        problems.append(f"control run outcome {r1['outcome']}")

    # ---- reboot the SAME image, replay the SAME key twice ----
    ino_mid = os.stat(img).st_ino
    vm2 = ctx.boot(img, f"{name}.run2", cpus=cpus)
    rec = [l for l in vm2.snapshot().splitlines() if l.startswith("recovering tail")]
    row["recovered_blocks"] = len(rec)
    if len(rec) != log_n:
        problems.append(f"recovery installed {len(rec)} blocks but log header said {log_n}")
    rp1 = effect(ctx, vm2, sc["op"], KEY, sc["path"], sc["text"], label=f"{name}.run2")
    rp2 = effect(ctx, vm2, sc["op"], KEY, sc["path"], sc["text"], label=f"{name}.run2")
    s2 = stats(ctx, vm2, label=f"{name}.run2")
    vm2.kill()
    row["replay1"] = rp1.get("outcome")
    row["replay2"] = rp2.get("outcome")
    want = "REPLAYED" if committed_view else "EXECUTED"
    if rp1.get("outcome") != want:
        problems.append(f"first replay {rp1.get('outcome')} != {want}")
    if rp2.get("outcome") != "REPLAYED":
        problems.append(f"second replay {rp2.get('outcome')} != REPLAYED")
    if rp1.get("rc") != len(sc["text"]) or rp2.get("rc") != len(sc["text"]):
        problems.append(f"replay rc {rp1.get('rc')}/{rp2.get('rc')}")
    if s2["executed"] != (0 if committed_view else 1):
        problems.append(f"post-reboot executed counter {s2['executed']}")

    # ---- final verdict from the disk ----
    fin = Image.load(img)
    row["final_log_n"] = fin.log_header()[0]
    f = fin.with_log_replayed()
    data = f.read_file(sc["path"])
    once = data == expected_final(sc)
    tab = entries_by_key(f)
    row["final_file_ok_once"] = once
    row["table_entries"] = len(tab)
    if not once:
        problems.append(f"file content wrong: {data!r}")
    if len(tab) != 1 or int(KEY, 16) not in tab or tab[int(KEY, 16)]["result"] != len(sc["text"]):
        problems.append(f"table wrong: {tab}")
    cons = f.check_consistency()
    if cons:
        problems.append(f"fs inconsistent: {cons}")
    if row["final_log_n"] != 0:
        problems.append("log not empty after recovery")
    if not (ino0 == ino_mid == os.stat(img).st_ino):
        problems.append("image file was replaced between crash and replay!")
    row["same_image_inode"] = ino0 == ino_mid == os.stat(img).st_ino
    row["verdict"] = "PASS" if not problems else "FAIL: " + "; ".join(problems)
    return row, problems


def sweep(ctx, scen_name, cpus=1, stages=True, crashat=True):
    sc = SCEN[scen_name]
    K, L, writes = measure(ctx, sc, cpus)
    ctx.param(scenario=scen_name, op=sc["op"], path=sc["path"], payload=sc["text"], key=KEY, cpus=cpus,
              log_write_calls_K=K, logged_blocks_L=L, disk_writes_per_effect=writes)
    rows = []
    plan = []
    if crashat:
        plan += [(f"crashat{n}", f"-c {n}", False) for n in range(1, K + 1)]
        plan += [(f"crashat{K+1}-control", f"-c {K+1}", None)]
    if stages:
        plan += [("stage1-before-header", "-s 1:1", False),
                 ("stage2-after-header", "-s 2:1", True)]
        plan += [(f"stage3-install-{h}", f"-s 3:{h}", True) for h in range(1, L + 1)]
        plan += [("stage4-after-install", "-s 4:1", True),
                 (f"stage3-install-{L+1}-control", f"-s 3:{L+1}", None)]
    for name, arm, exp in plan:
        row, problems = trial(ctx, f"{scen_name}.{name}", sc, arm, exp, cpus)
        rows.append(row)
        ctx.check(f"{name}: crash->recover->replay = exactly once", "PASS", row["verdict"])
    ctx.table(f"crash points for {scen_name} (K={K} log_write calls, L={L} blocks, {writes} disk writes)", rows)
    crashes = [r for r in rows if r["crashed"]]
    ctx.check("at least K+L+3 real crashes were exercised", True, len(crashes) >= K + L + 3 if (crashat and stages) else len(crashes) >= 1)
    ctx.check("uncommitted crashes (replay EXECUTED) and committed crashes (replay REPLAYED) both occurred",
              True, any(r["replay1"] == "EXECUTED" and r["crashed"] for r in rows) and any(r["replay1"] == "REPLAYED" and r["crashed"] for r in rows))


@case("C1", "Crash sweep: APPEND inside one block (every log_write point + every commit stage)", "crash")
def c1(ctx):
    sweep(ctx, "append-inblock")


@case("C2", "Crash sweep: APPEND crossing a block boundary (allocates a new block + bitmap)", "crash")
def c2(ctx):
    sweep(ctx, "append-crossblock")


@case("C3", "Crash sweep: CREATE (inode + directory entry + data + table in one transaction)", "crash")
def c3(ctx):
    sweep(ctx, "create")


@case("C4", "Crash sweep on 3 CPUs: APPEND inside one block", "crash", params=dict(cpus=3))
def c4(ctx):
    sweep(ctx, "append-inblock", cpus=3)


@case("C5", "Crash sweep: WORST-CASE block budget (APPEND crossing direct->indirect: new indirect + data + bitmap)", "crash")
def c5(ctx):
    sweep(ctx, "append-indirect")
