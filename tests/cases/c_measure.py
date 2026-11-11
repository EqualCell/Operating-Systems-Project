"""Measurements (group "measure"): cost of an effect in log blocks / disk writes."""
import time

from tests.framework import case, effect, stats
from tests.lib.fsimage import Image

INIT_LOG = b"boot-entry-0\n"
MAXOPBLOCKS = 10
LOGBLOCKS = 30


def final(img):
    return Image.load(img).with_log_replayed()


def one(ctx, vm, label, op, key, path, text, expect_outcome):
    s0 = stats(ctx, vm)
    r = effect(ctx, vm, op, key, path, text)
    s1 = stats(ctx, vm)
    row = dict(case=label, outcome=r.get("outcome"), rc=r["rc"],
               log_write_calls=s1["logwrites"] - s0["logwrites"],
               disk_writes=s1["diskwrites"] - s0["diskwrites"],
               logged_blocks=s1["last_logged"] if r.get("outcome") == "EXECUTED" else 0)
    return r, row


@case("E1", "Cost per effect: log blocks and disk writes (append, cross-block, indirect, create, replay, refusals)", "measure")
def e1(ctx):
    img = ctx.new_image()
    vm = ctx.boot(img, "run")
    rows = []
    r, row = one(ctx, vm, "APPEND within a block", "append", "0xE1", "/log.txt", "hello", "EXECUTED"); rows.append(row)
    ctx.check("append-in-block executed", "EXECUTED", r["outcome"])
    r, row = one(ctx, vm, "REPLAY of that key", "append", "0xE1", "/log.txt", "hello", "REPLAYED"); rows.append(row)
    ctx.check("replay costs 0 disk writes and 0 log_writes", (0, 0), (row["disk_writes"], row["log_write_calls"]))
    r, row = one(ctx, vm, "APPEND crossing 1 KB boundary (edge.txt)", "append", "0xE2", "/edge.txt", "0123456789", "EXECUTED"); rows.append(row)
    r, row = one(ctx, vm, "APPEND direct->indirect (big.txt)", "append", "0xE3", "/big.txt", "0123456789012345678901234567890123456789", "EXECUTED"); rows.append(row)
    r, row = one(ctx, vm, "CREATE new file", "create", "0xE4", "/m.txt", "body", "EXECUTED"); rows.append(row)
    r, row = one(ctx, vm, "MISMATCH refusal", "append", "0xE1", "/log.txt", "other", ""); rows.append(row)
    ctx.check("mismatch refusal costs 0 disk writes", 0, row["disk_writes"])
    r, row = one(ctx, vm, "ENOENT refusal", "append", "0xE5", "/none.txt", "x", ""); rows.append(row)
    ctx.check("ENOENT refusal costs 0 disk writes (nothing logged)", 0, row["disk_writes"])
    vm.kill()
    for row in rows:
        if row["outcome"] == "EXECUTED":
            L = row["logged_blocks"]
            ctx.check(f"{row['case']}: disk writes == 2*L+2 (L={L}: log copy + header + install + header clear)", 2 * L + 2, row["disk_writes"])
            ctx.check(f"{row['case']}: L <= MAXOPBLOCKS({MAXOPBLOCKS})", True, L <= MAXOPBLOCKS)
    ctx.table("per-effect cost (xv6 log: 2L+2 disk writes for L logged blocks)", rows)
    ctx.note("The table block is exactly ONE of the L logged blocks, i.e. the exactly-once record costs +1 log block = +2 disk writes per executed effect; a replay costs nothing.")
    ctx.param(MAXOPBLOCKS=MAXOPBLOCKS, LOGBLOCKS=LOGBLOCKS)


@case("E2", "Recovery cost: boot time with a committed-but-uninstalled log vs a clean boot", "measure")
def e2(ctx):
    clean, rec = [], []
    for i in range(5):
        img = ctx.new_image(f"clean{i}")
        vm = ctx.boot(img, f"clean{i}")
        clean.append(vm.boot_seconds)
        vm.kill()
    for i in range(5):
        img = ctx.new_image(f"rec{i}")
        vm = ctx.boot(img, f"crash{i}")
        out, st = ctx.sh(vm, "effectctl -s 2:1 append 0x1 /log.txt rec", timeout=15)
        vm.kill()
        vm2 = ctx.boot(img, f"recover{i}")
        n = len([l for l in vm2.snapshot().splitlines() if l.startswith("recovering tail")])
        rec.append((vm2.boot_seconds, n))
        vm2.kill()
    ctx.table("boot wall-clock seconds (QEMU start -> shell prompt)", [
        dict(kind="clean boot", samples=clean, mean=round(sum(clean) / 5, 3)),
        dict(kind="boot with recovery of 3 logged blocks", samples=[r[0] for r in rec], mean=round(sum(r[0] for r in rec) / 5, 3)),
    ])
    ctx.check("recovery installed 3 blocks every time", [3] * 5, [r[1] for r in rec])
    ctx.check("recovery boots complete (< 10 s each)", True, all(r[0] < 10 for r in rec))
    ctx.note("Wall-clock on an emulated machine; indicative only. Recovery work is 3 block copies, negligible.")
