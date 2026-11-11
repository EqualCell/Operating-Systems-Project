# Experiments: how to reproduce and what is recorded

## One command
```sh
./run_tests.sh --slow          # build + 42 cases (≈ 3 min) -> evidence/<run>/ ; exit status 0 iff all pass
python3 tools/summarize.py evidence/<run> docs/test-results.md      # regenerate the readable report
```
`python3 tests/run_all.py --list` shows all cases; `--only ID...`, `--group baseline|behaviour|concurrency|crash|agent|measure|unit|regress|mutation`.
Per-case, per-trial results are in `docs/test-results.md` (generated, includes every crash point).

## Test catalogue
| group | ids | what |
|---|---|---|
| baseline | A1 A2 | layout, reserved block, boot, syscall wiring |
| behaviour | B1–B9, B13 | new key, replay, high-bit keys, mismatch, persistence, hostile args, CREATE, table full, disk full |
| concurrency | B10a B10b B11 B12 | same key ×6 procs (3 CPUs / 1 CPU), different payloads, distinct keys |
| crash | C1–C5 | every `log_write` point and every commit stage for 5 scenarios |
| agent | D1–D11 | list/read/summarize/append, lost reply, crash+retry, host restart, injection, guest allowlist, forged frame, honest failures |
| measure | E1 E2 | blocks and disk writes per effect, recovery cost |
| unit | U1 | 23 host-only tests |
| regress | R1 R2 | stock `usertests -q`; production build without crash hooks |
| mutation | M-* | five broken kernels must FAIL the suite |

## What is recorded for every case (`evidence/<run>/<case>/case.json`)
parameters (key, op, path, payload, CPUs, K, L, ...), every guest command with its raw output and
status, every check (name, expected, observed, pass), per-row tables, QEMU command line and boot time of
every boot, raw serial log of every boot (`*.qemu.log`), lossless block-diff archives of every disk
image (`*.blockdiff.gz`, base = `pristine-fs.img.gz`; rebuild with `tools/restore_image.py`), agent
trace + bridge history for agent cases, journal files, build logs of mutant/production kernels.
Run-level (`results.json → environment`): date, host, Python, QEMU, GCC, xv6 base commit, sha256 of
kernel, pristine image and the modified sources.

## The oracle (why a pass means something)
`tests/lib/fsimage.py` re-implements the xv6 on-disk format in Python (superblock, inodes, indirect
blocks, directory, log header, bitmap, effect table, FNV signature). Verdicts are computed from the
disk image, **never** from the agent's or kernel's own message. After a crash it applies the log in
memory on a copy, because "home" blocks right after a crash may still need recovery. The five mutants
(`tests/mutants.py`) prove it fails when the kernel is wrong.

## Same image across crash → replay
Each trial copies the pristine image once, then uses that single file for crash, reboot and replay; the
trial records `st_ino` of the file before the crash, between boots and after, and fails if it changed.
New independent trials start from a clean copy.

## Measured results (from the final run)
* **330 checks, 42 cases, 0 failures** (`evidence/final/results.json`).
* **78 crash/replay trials, 68 real crashes**, all exactly-once: 5 scenarios × (every `log_write` point +
  stages 1–4 + every install step + no-crash controls). Uncommitted crashes → replay `EXECUTED`; committed
  crashes (log header durable) → recovery installed the logged blocks at boot and replay was `REPLAYED`.
* Cost: in-block append 3 logged blocks / 8 disk writes (the table block is 1 of the 3); replay 0.
* Recovery cost: boot with 3 blocks to recover ≈ clean boot (0.26 s vs 0.28 s under TCG, noise level).
* Same-key concurrency on 3 CPUs: 8 trials × 6 processes → exactly 8 effects, 40 replays.
* Table full: 64 accepted, 6 refused with the file untouched; all 64 keys still replay.
* Disk full (692 free blocks → 689 written by `diskfill`): short write recorded (rc 4 of 10), zero-progress `EIO`.
* `usertests -q` (3 CPUs): ALL TESTS PASSED.

## GDB
`python3 tests/gdb/inspect_commit.py` → `evidence/gdb-commit-inspection.txt`: stops at the commit point
inside `effect()`, prints `bt` (`write_head ← commit ← end_op ← sys_effect`), the transaction's blocks
`{52, 33, 47}` and `sb.effstart = 47`. Interactive session: `make qemu-gdb` + `gdb-multiarch kernel/kernel`,
`target remote :<port>`. See `docs/limitations.md` for what this is and is not.
