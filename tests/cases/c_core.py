"""Core correctness cases (groups A = baseline, B = behaviour).

Convention: the kernel answers (effectctl output) are only the *claim*; the
verdict comes from tests/lib/fsimage.py reading the disk image directly.
"""
from tests.framework import case, effect, stats, cat, kv
from tests.lib.fsimage import Image, entries_by_key, fnv_sig

APPEND, CREATE = 1, 2
INIT_LOG = b"boot-entry-0\n"


def final(img_path):
    """Disk state as recovery would leave it (log replayed on a COPY, in memory)."""
    return Image.load(img_path).with_log_replayed()


# --------------------------------------------------------------------------- A
@case("A1", "Pristine image layout, reserved table blocks, clean boot", "baseline")
def a1(ctx):
    img = ctx.new_image()
    im = Image.load(img)
    ctx.param(effstart=im.effstart, effblocks=im.effblocks, bmapstart=im.bmapstart, inodestart=im.inodestart, logstart=im.logstart, fs_blocks=im.size)
    ctx.check("superblock magic", 0x10203040, im.magic)
    ctx.check("effect table has 1 reserved block", 1, im.effblocks)
    ctx.check("table sits right after the bitmap", im.bmapstart + 1, im.effstart)
    ctx.check("table starts empty", [], im.table())
    ctx.check("log starts empty", (0, []), im.log_header())
    ctx.check("pristine image is consistent (bitmap marks table; no block owned twice)", [], im.check_consistency())
    ctx.check("fixture /log.txt present", INIT_LOG, im.read_file("/log.txt"))
    vm = ctx.boot(img, "boot")
    out, st = ctx.sh(vm, "ls")
    ctx.check("shell works", "ok", st)
    for prog in ("effectctl", "agentcall", "crashctl", "effstat", "effstress", "effraw", "log.txt", "inbox.txt"):
        ctx.check(f"ls shows {prog}", True, prog in out)
    ctx.param(boot_seconds=vm.boot_seconds)


@case("A2", "effect() syscall is wired: user program -> kernel -> result", "baseline")
def a2(ctx):
    img = ctx.new_image()
    vm = ctx.boot(img, "boot")
    r = effect(ctx, vm, "append", "0x1", "/log.txt", "hello")
    ctx.param(key="0x1", op="APPEND", path="/log.txt", payload="hello")
    ctx.check("rc == bytes appended", 5, r["rc"])
    ctx.check("outcome EXECUTED", "EXECUTED", r.get("outcome"))
    s = stats(ctx, vm)
    ctx.check("kernel counter executed==1", 1, s["executed"])
    ctx.check("table_used==1", 1, s["table_used"])
    ctx.check("table_slots==64", 64, s["table_slots"])


# --------------------------------------------------------------------------- B
@case("B1", "New key appends the expected bytes; table entry is correct on disk", "behaviour",
      params=dict(key="0xDEADBEEF12345678", payload="HELLO-EXACTLY"))
def b1(ctx):
    img = ctx.new_image()
    vm = ctx.boot(img, "run")
    r = effect(ctx, vm, "append", "0xDEADBEEF12345678", "/log.txt", "HELLO-EXACTLY")
    vm.kill()
    f = final(img)
    ctx.check("rc", 13, r["rc"])
    ctx.check("file = old content + payload (independent parse)", INIT_LOG + b"HELLO-EXACTLY", f.read_file("/log.txt"))
    tab = entries_by_key(f)
    k = 0xDEADBEEF12345678
    ctx.check("64-bit key stored un-truncated in table", True, k in tab)
    ctx.check("stored result", 13, tab[k]["result"])
    ctx.check("stored signature equals independent FNV-1a", fnv_sig(APPEND, "/log.txt", b"HELLO-EXACTLY"), tab[k]["sig"])
    ctx.check("exactly one table entry", 1, len(tab))
    ctx.check("image consistent", [], f.check_consistency())


@case("B2", "Same key repeated: effect happens once, replays change nothing", "behaviour",
      params=dict(key="0x42", replays=3))
def b2(ctx):
    img = ctx.new_image()
    vm = ctx.boot(img, "run")
    first = effect(ctx, vm, "append", "0x42", "/log.txt", "ONCE")
    s0 = stats(ctx, vm)
    replays = [effect(ctx, vm, "append", "0x42", "/log.txt", "ONCE") for _ in range(3)]
    s1 = stats(ctx, vm)
    vm.kill()
    ctx.check("first call EXECUTED", "EXECUTED", first["outcome"])
    ctx.check("replays all REPLAYED", ["REPLAYED"] * 3, [r["outcome"] for r in replays])
    ctx.check("replays return the stored result", [4, 4, 4], [r["rc"] for r in replays])
    ctx.check("kernel executed counter unchanged by replays", s0["executed"], s1["executed"])
    ctx.check("kernel replayed counter +3", s0["replayed"] + 3, s1["replayed"])
    ctx.check("replays caused 0 disk writes", 0, s1["diskwrites"] - s0["diskwrites"])
    ctx.check("replays caused 0 log_write calls", 0, s1["logwrites"] - s0["logwrites"])
    f = final(img)
    ctx.check("file contains payload exactly once", INIT_LOG + b"ONCE", f.read_file("/log.txt"))
    ctx.check("one table entry", 1, len(f.table()))


@case("B3", "Different key = a second logical operation", "behaviour")
def b3(ctx):
    img = ctx.new_image()
    vm = ctx.boot(img, "run")
    a = effect(ctx, vm, "append", "0x10", "/log.txt", "AAA")
    b = effect(ctx, vm, "append", "0x11", "/log.txt", "AAA")   # same text, different key
    vm.kill()
    ctx.check("both EXECUTED", ["EXECUTED", "EXECUTED"], [a["outcome"], b["outcome"]])
    f = final(img)
    ctx.check("file has AAA twice", INIT_LOG + b"AAAAAA", f.read_file("/log.txt"))
    ctx.check("two table entries", {0x10, 0x11}, set(entries_by_key(f)))


@case("B4", "Keys that differ only in the HIGH 32 bits never collide (no truncation)", "behaviour")
def b4(ctx):
    keys = [0x1, 0x100000001, 0x200000001, 0xFFFFFFFF00000001, 0xFFFFFFFFFFFFFFFF, 0x8000000000000000]
    ctx.param(keys=[hex(k) for k in keys])
    img = ctx.new_image()
    vm = ctx.boot(img, "run")
    outs = []
    for i, k in enumerate(keys):
        outs.append(effect(ctx, vm, "append", hex(k), "/log.txt", chr(ord("a") + i)))
    # retry one of them: must be a replay, not a new append
    again = effect(ctx, vm, "append", hex(keys[2]), "/log.txt", "c")
    vm.kill()
    ctx.check("all 6 distinct keys EXECUTED", ["EXECUTED"] * 6, [o["outcome"] for o in outs])
    ctx.check("retry of 0x200000001 is REPLAYED", "REPLAYED", again["outcome"])
    f = final(img)
    ctx.check("file has each letter exactly once", INIT_LOG + b"abcdef", f.read_file("/log.txt"))
    ctx.check("table holds all six full 64-bit keys", set(keys), set(entries_by_key(f)))
    ctx.note("0x1, 0x100000001, 0x200000001 have identical low 32 bits: a 32-bit argint() key would have collided.")


@case("B5", "Same key, DIFFERENT request is refused (EMISMATCH), file untouched", "behaviour")
def b5(ctx):
    img = ctx.new_image()
    vm = ctx.boot(img, "run")
    ok = effect(ctx, vm, "append", "0x77", "/log.txt", "AAA")
    m1 = effect(ctx, vm, "append", "0x77", "/log.txt", "BBB")        # other payload
    m2 = effect(ctx, vm, "append", "0x77", "/report.txt", "AAA")     # other path
    m3 = effect(ctx, vm, "create", "0x77", "/log.txt", "AAA")        # other op
    s = stats(ctx, vm)
    vm.kill()
    ctx.check("original EXECUTED", "EXECUTED", ok["outcome"])
    ctx.check("different payload -> -4", -4, m1["rc"])
    ctx.check("different path -> -4", -4, m2["rc"])
    ctx.check("different op -> -4", -4, m3["rc"])
    ctx.check("mismatched counter == 3", 3, s["mismatched"])
    f = final(img)
    ctx.check("log.txt has only the original AAA", INIT_LOG + b"AAA", f.read_file("/log.txt"))
    ctx.check("report.txt untouched", b"The server handled 100 requests.\nFive requests failed.\nAverage response time was 20 ms.\n", f.read_file("/report.txt"))
    ctx.check("still one table entry", 1, len(f.table()))


@case("B6", "Table entry survives power-off and reboot (persistence)", "behaviour")
def b6(ctx):
    img = ctx.new_image()
    vm = ctx.boot(img, "boot1")
    first = effect(ctx, vm, "append", "0xBEEF", "/log.txt", "PERSIST")
    vm.kill()
    mid = Image.load(img)
    ctx.check("entry is on disk after power-off", True, 0xBEEF in entries_by_key(mid.with_log_replayed()))
    vm2 = ctx.boot(img, "boot2")                    # SAME image
    s = stats(ctx, vm2)
    ctx.check("fresh boot sees the entry (table_used==1) with executed counter reset", (1, 0), (s["table_used"], s["executed"]))
    again = effect(ctx, vm2, "append", "0xBEEF", "/log.txt", "PERSIST")
    vm2.kill()
    ctx.check("retry after reboot REPLAYED", "REPLAYED", again["outcome"])
    ctx.check("file has PERSIST once", INIT_LOG + b"PERSIST", final(img).read_file("/log.txt"))


@case("B7", "Validation and hostile arguments: refused cleanly, kernel survives", "behaviour")
def b7(ctx):
    img = ctx.new_image()
    vm = ctx.boot(img, "run")

    def raw(mode, key, op, path="/log.txt", n=None):
        cmd = f"effraw {mode} {key} {op} {path}" + (f" {n}" if n is not None else "")
        out, st = ctx.sh(vm, cmd)
        line = next((l for l in out.splitlines() if l.startswith("RAW")), "")
        return int(kv(line).get("rc", 999)), st

    table = [
        ("key 0 is reserved", ("plain", "0x0", 1), -1),
        ("unknown op 9", ("plain", "0x5", 9), -1),
        ("op 0", ("plain", "0x5", 0), -1),
        ("APPEND of 0 bytes", ("len", "0x5", 1, "/log.txt", 0), -1),
        ("payload 257 > limit", ("len", "0x5", 1, "/log.txt", 257), -1),
        ("negative length", ("negn", "0x5", 1), -1),
        ("buffer pointer one past end of memory", ("endptr", "0x5", 1), -1),
        ("buffer straddling end of memory", ("straddle", "0x5", 1), -1),
        ("unmapped buffer pointer", ("badptr", "0x5", 1), -1),
        ("unmapped path pointer", ("badpath", "0x5", 1), -1),
        ("relative path", ("plain", "0x5", 1, "log.txt"), -1),
        ("path '/' only", ("plain", "0x5", 1, "/"), -1),
        ("APPEND to missing file", ("plain", "0x6", 1, "/nosuch.txt"), -2),
        ("APPEND to a directory", ("plain", "0x7", 1, "/."), -1),
        ("APPEND to a device", ("plain", "0x8", 1, "/console"), -1),
    ]
    got = []
    for name, args, expect in table:
        rc, st = raw(*args)
        got.append((name, rc))
        ctx.check(f"{name}: rc", expect, rc)
    # exact upper bound is accepted: 256 bytes
    rc256, _ = raw("len", "0x9", 1, "/log.txt", 256)
    ctx.check("payload of exactly 256 bytes accepted (rc=256)", 256, rc256)
    s = stats(ctx, vm)
    ctx.check("kernel still alive and answering", True, "executed" in s)
    ctx.check("only the 256-byte call executed", 1, s["executed"])
    ctx.check("table_used==1 (errors are never recorded)", 1, s["table_used"])
    ctx.check("kernel 'errors' counter == 3 (ENOENT, dir, device reach the op layer)", 3, s["errors"])
    vm.kill()
    f = final(img)
    ctx.check("only change to disk: 256 'x' appended", INIT_LOG + b"x" * 256, f.read_file("/log.txt"))
    ctx.check("image consistent", [], f.check_consistency())


@case("B8", "CREATE: new file + record in one transaction; replay; error cases", "behaviour")
def b8(ctx):
    img = ctx.new_image()
    vm = ctx.boot(img, "run")
    c1 = effect(ctx, vm, "create", "0xC1", "/new.txt", "created-body")
    c1r = effect(ctx, vm, "create", "0xC1", "/new.txt", "created-body")     # replay
    c2 = effect(ctx, vm, "create", "0xC2", "/new.txt", "other")               # new key, path exists
    c3 = effect(ctx, vm, "create", "0xC3", "/nodir/x.txt", "zzz")             # missing parent
    s = stats(ctx, vm)
    vm.kill()
    ctx.check("CREATE EXECUTED rc=bytes", ("EXECUTED", 12), (c1["outcome"], c1["rc"]))
    ctx.check("CREATE replay REPLAYED same rc", ("REPLAYED", 12), (c1r["outcome"], c1r["rc"]))
    ctx.check("CREATE of existing path -> EEXIST(-6)", -6, c2["rc"])
    ctx.check("CREATE with missing parent -> EINVAL(-1)", -1, c3["rc"])
    f = final(img)
    ctx.check("new.txt exists with exact body", b"created-body", f.read_file("/new.txt"))
    ctx.check("only the successful CREATE recorded", {0xC1}, set(entries_by_key(f)))
    ctx.check("failed CREATEs left no file", None, f.read_file("/x.txt"))
    ctx.check("exactly one directory entry named new.txt", 1, list(f.root_entries()).count("new.txt"))
    ctx.check("image consistent", [], f.check_consistency())
    ctx.check("kernel counters executed=1 replayed=1 errors=2", (1, 1, 2), (s["executed"], s["replayed"], s["errors"]))
    ctx.param(last_logged_blocks_create=s["last_logged"], last_diskwrites_create=s["last_diskwrites"])


@case("B9", "Table full: refused BEFORE touching the file; replays still work", "behaviour",
      params=dict(slots=64, calls=70))
def b9(ctx):
    img = ctx.new_image()
    vm = ctx.boot(img, "run")
    out, st = ctx.sh(vm, "effstress fill 70 0x1000 /log.txt z", timeout=120)
    line = next((l for l in out.splitlines() if l.startswith("STRESS-SUMMARY")), "")
    d = kv(line)
    ctx.check("64 effects fit, 6 refused with EFULL", ("64", "6"), (d.get("ok"), d.get("EFULL")))
    s = stats(ctx, vm)
    ctx.check("table_used == table_slots == 64", (64, 64), (s["table_used"], s["table_slots"]))
    # replay everything again: existing keys still answer, new keys still EFULL
    out2, _ = ctx.sh(vm, "effstress fill 70 0x1000 /log.txt z", timeout=120)
    d2 = kv(next((l for l in out2.splitlines() if l.startswith("STRESS-SUMMARY")), ""))
    ctx.check("full table: all 64 stored keys still replay (linear probing finds every one)", ("64", "6"), (d2.get("ok"), d2.get("EFULL")))
    s2 = stats(ctx, vm)
    ctx.check("replays did not execute anything", s["executed"], s2["executed"])
    mm = effect(ctx, vm, "append", "0x1000", "/log.txt", "DIFFERENT")
    ctx.check("mismatch detected even when full", -4, mm["rc"])
    cr = effect(ctx, vm, "create", "0x9999", "/tfull.txt", "never")
    ctx.check("CREATE with full table -> EFULL(-3)", -3, cr["rc"])
    vm.kill()
    f = final(img)
    ctx.check("file grew by exactly 64 bytes (none for refused calls)", INIT_LOG + b"z" * 64, f.read_file("/log.txt"))
    ctx.check("refused CREATE left no file", None, f.read_file("/tfull.txt"))
    ctx.check("64 distinct keys on disk", 64, len(f.table()))
    ctx.check("image consistent", [], f.check_consistency())


def _stress(ctx, cpus, mode, n, trials):
    img = ctx.new_image()
    vm = ctx.boot(img, "run", cpus=cpus)
    summaries = []
    for t in range(trials):
        key = f"0x{0x5000 + t * 0x100:x}"
        text = f"T{t}"
        out, st = ctx.sh(vm, f"effstress {mode} {n} {key} /log.txt {text}", timeout=60)
        summaries.append(kv(next((l for l in out.splitlines() if l.startswith("STRESS-SUMMARY")), "")))
    s = stats(ctx, vm)
    vm.kill()
    return img, summaries, s


@case("B10a", "Concurrency: 6 processes, SAME key, SAME payload, 3 CPUs, 8 trials", "concurrency",
      params=dict(cpus=3, procs=6, trials=8))
def b10a(ctx):
    img, sums, s = _stress(ctx, 3, "same", 6, 8)
    f = final(img)
    expect = INIT_LOG + b"".join(f"T{t}".encode() for t in range(8))
    ctx.check("every caller got a success result", ["6"] * 8, [d.get("ok") for d in sums])
    ctx.check("file has each trial's payload EXACTLY once", expect, f.read_file("/log.txt"))
    ctx.check("kernel: executed == trials (8)", 8, s["executed"])
    ctx.check("kernel: replayed == 8*(6-1) = 40", 40, s["replayed"])
    ctx.check("8 table entries", 8, len(f.table()))
    ctx.check("image consistent", [], f.check_consistency())


@case("B10b", "Concurrency: same key SAME payload, 1 CPU (debug configuration)", "concurrency",
      params=dict(cpus=1, procs=6, trials=4))
def b10b(ctx):
    img, sums, s = _stress(ctx, 1, "same", 6, 4)
    f = final(img)
    expect = INIT_LOG + b"".join(f"T{t}".encode() for t in range(4))
    ctx.check("file has each payload exactly once", expect, f.read_file("/log.txt"))
    ctx.check("executed == 4, replayed == 20", (4, 20), (s["executed"], s["replayed"]))


@case("B11", "Concurrency: same key, DIFFERENT payloads: one wins, rest EMISMATCH", "concurrency",
      params=dict(cpus=3, procs=6, trials=4))
def b11(ctx):
    img, sums, s = _stress(ctx, 3, "diff", 6, 4)
    f = final(img)
    data = f.read_file("/log.txt")[len(INIT_LOG):]
    ctx.check("per trial: exactly 1 success and 5 EMISMATCH", [("1", "5")] * 4, [(d.get("ok"), d.get("EMISMATCH")) for d in sums])
    ctx.check("file grew by exactly one payload per trial (4 x 3 bytes)", 12, len(data))
    ctx.check("kernel executed == 4, mismatched == 20", (4, 20), (s["executed"], s["mismatched"]))


@case("B12", "Concurrency: 8 processes, DISTINCT keys, 3 CPUs: no lost / duplicate append", "concurrency",
      params=dict(cpus=3, procs=8, trials=3))
def b12(ctx):
    img, sums, s = _stress(ctx, 3, "many", 8, 3)
    f = final(img)
    data = f.read_file("/log.txt")[len(INIT_LOG):]
    ctx.check("all calls succeeded", ["8"] * 3, [d.get("ok") for d in sums])
    ctx.check("48 bytes appended (3 trials x 8 procs x 2-byte payload)", 48, len(data))
    for t in range(3):
        ctx.check(f"trial {t}: payload 'T{t}' present exactly 8 times", 8, data.count(f"T{t}".encode()))
    ctx.check("24 distinct keys recorded", 24, len(f.table()))
    ctx.check("executed==24 replayed==0", (24, 0), (s["executed"], s["replayed"]))
    ctx.check("image consistent", [], f.check_consistency())


@case("B13", "Disk FULL: short write is recorded atomically; zero-progress is EIO and not recorded", "behaviour")
def b13(ctx):
    img = ctx.new_image()
    free0 = Image.load(img).free_blocks()
    vm = ctx.boot(img, "run")
    out, st = ctx.sh(vm, "diskfill", timeout=300)
    ctx.check("diskfill ran to completion", "ok", st)
    filled = int(kv(next((l for l in out.splitlines() if l.startswith("DISKFILL")), "")).get("blocks", 0))
    ctx.param(free_blocks_before=free0, diskfill_blocks_written=filled)
    ctx.check("diskfill wrote (almost) every free block", True, free0 - 12 <= filled <= free0)

    # (a) file whose last block has 4 free bytes: 10-byte append -> only 4 fit -> SHORT WRITE
    a = effect(ctx, vm, "append", "0xD1", "/edge.txt", "0123456789")
    a2 = effect(ctx, vm, "append", "0xD1", "/edge.txt", "0123456789")
    ctx.check("(a) short write: rc = 4 bytes actually appended (not 10)", 4, a["rc"])
    ctx.check("(a) the short result is recorded: replay returns the same 4", ("REPLAYED", 4), (a2["outcome"], a2["rc"]))
    # (b) file ending exactly on a block boundary: nothing fits -> EIO, NOT recorded
    b = effect(ctx, vm, "append", "0xD2", "/full.txt", "xyz")
    ctx.check("(b) no progress possible -> EIO (-5)", -5, b["rc"])
    # (c) CREATE: inode available but no data block -> file exists, empty, result 0 recorded
    c = effect(ctx, vm, "create", "0xD3", "/new.txt", "hello")
    s = stats(ctx, vm)
    vm.kill()
    f = final(img)
    ctx.check("(a) file grew by exactly 4 bytes, once", Image.load(img).with_log_replayed().read_file("/edge.txt")[-14:], (b"E" * 19 + b"\n")[-10:] + b"0123")
    ctx.check("(b) /full.txt unchanged (1024 bytes)", 1024, len(f.read_file("/full.txt")))
    tab = entries_by_key(f)
    ctx.check("(a) recorded with result 4; (b) NOT recorded", (4, False), (tab[0xD1]["result"], 0xD2 in tab))
    ctx.check("(c) CREATE under full disk: no data block available -> recorded result is the bytes actually written",
              (c["rc"], tab.get(0xD3, {}).get("result")), (0, 0))
    ctx.check("(c) the created file is empty", b"", f.read_file("/new.txt"))
    ctx.check("bitmap says the disk is completely full (0 free blocks)", 0, f.free_blocks())
    ctx.check("image consistent after disk-full operations", [], f.check_consistency())
    ctx.note("xv6 logging makes recorded block updates crash-atomic; it does not undo a failed function. Our rule: whatever bytes were written are recorded in the same transaction (short-write semantics), and zero-progress failures are not recorded. We do NOT claim all-or-nothing append on disk-full.")
