# Design journal (what actually happened, including what failed)

The course asks for a short note of "what failed and why". These entries are real events from the
build; the dates are the session date. **This is a starting point for the team's own git design
notes (one commit every two days): copy the entries you personally lived through into your commits,
do not backdate anything.**

## 2026-11-11 — environment
* No `qemu-system-riscv64`, no RISC-V cross compiler, no `sudo`; `archive.ubuntu.com` did not resolve
  (only a few hosts were reachable). `apt-get download` hung silently. **Fix:** fetched the `.deb`
  files from `mirrors.kernel.org/ubuntu` with `curl` and unpacked them with `dpkg -x` into
  `~/toolchain/root` (see `docs/setup.md`). Lesson: say which toolchain produced the evidence.
* `~/Downloads/xv6-public` is the *x86* xv6, not the RISC-V tree of the handout. Upstream xv6-riscv
  matches the handout (`printk`, split `sleep_prepare/sleep`, `LOGBLOCKS`, `copyin(pt, sz, ...)`).
  Lesson: check the real prototypes first.

## 2026-11-11 — kernel
* **Design choice:** table entry `{u64 key; int result; uint sig}`. The handout's 16-byte example had a
  `pad` field; we used it as a 32-bit request signature to implement the "same key, different payload" test.
* **Design choice:** results < 0 are never stored (so a failed attempt can be retried, key reusable).
* **Design choice:** single global sleeplock taken *before* `begin_op` (documented lock order).
* **Observation:** in this tree `end_op()` commits only when no other FS operation is in flight (group
  commit). So "end_op returned" ≠ "durable"; added `sys_sync()` after unlocking.
* First build failed: `%p` wants `void *` under `-Werror=format` (user printf has no width flags and
  no `%016llx`; `%p` prints all 16 hex digits of a 64-bit value). Fixed with a cast.
* Link failed: my first Makefile edit for the new objects missed the OBJS indentation (tab vs spaces),
  so `effect.o` etc. were never linked ("undefined reference to sys_effect"). Fixed.
* First boot: effect appended once; same key replayed; keys `0x100000001`/`0x200000001` (same low 32
  bits) both executed → no truncation. The measured cost of an in-block append: 3 logged blocks, 8 disk writes = 2·3+2.
* **Insight:** `crashat(n)` (panic in `log_write`) can only reach crashes *before* the commit point;
  the interesting ones need hooks inside `commit()` → added `crashhook(stage, n)` (handout says the same).

## 2026-11-11 — tests
* Harness bug: prompt detection assumed `"\n$ "`; `cat` of a file with no trailing newline prints the
  prompt mid-line → false timeout. Now: prompt = `"$ "` at end of stream + 40 ms quiet.
* Test bug (B7): I expected a `NULL` buffer to be rejected. **xv6 maps address 0** (text starts at 0), so
  the call legitimately appended 8 bytes of program text and the following checks failed. Replaced by
  pointers at/after the end of memory and one straddling the end.
* Test bug (B12): arithmetic (3 trials × 8 procs × 2 bytes = 48, not 24).
* Test bug (D8): the "benign control" reused the deliberately gullible planner, which only understands
  `summarize`; the control must use the normal planner.
* Test bug (D10): forged `@@END 101` targets attempt id 101, but the first call had id 100; the test now
  makes a `list` call first so the read really is attempt 101.
* Test bug (B13): assumed > 1500 free blocks; this image has ≈ 787. The check now compares with the
  bitmap's free-block count.
* **Mutation testing:** five deliberately broken kernels (`tests/mutants.py`). All were caught; the
  `split-transaction` mutant produced the exact bug the project prevents (`CRASH-PAYLOADCRASH-PAYLOAD`).
* Regression: stock `usertests -q` passes on 3 CPUs with our changes (R1).

## What is *not* in this journal
* A GDB "bug found and fixed" session. The bugs above were build errors and test mistakes, not kernel
  bugs found with a debugger, so we are **not** presenting any of them as that. The team must provide
  its own real session. A GDB transcript that *inspects the commit point* of `effect()` is in
  `evidence/gdb-commit-inspection.txt` (made by `tests/gdb/inspect_commit.py`); it shows the three blocks
  `{52, 33, 47}` of one transaction and that `47 == sb.effstart` (the table block). It is an
  inspection of the mechanism and is labelled as such.
