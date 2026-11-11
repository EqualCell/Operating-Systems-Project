# Crash points

Reproduce one trial by hand:
```sh
. ./env.sh && make fs.img && cp fs.img /tmp/t.img
python3 - <<'PY'
from agent.qemu import VM
vm = VM('/tmp/t.img').boot()
print(vm.run('effectctl -s 2:1 append 0x77 /log.txt POST'))   # panics after the commit point
vm.kill()                                                    # power cut
vm = VM('/tmp/t.img').boot()                                 # SAME image: recovery runs at boot
print(vm.run('effectctl append 0x77 /log.txt POST'))         # -> outcome=REPLAYED
print(vm.run('cat /log.txt'))                                # POST appears once
PY
```

## Timeline of `commit()` and the hooks (`kernel/log.c`)
```
 effect: begin_op ... store_find ... do_append (log_write xK) ... store_put (log_write) ... end_op
                                   ^ crashat(n): panic at the n-th log_write  (always before commit)
 commit():
   write_log()          copy cache blocks -> log area
   ── hook stage 1 ──   CRASH_BEFORE_HEADER   : uncommitted
   write_head()         header with n>0 reaches the disk   === COMMIT POINT ===
   ── hook stage 2 ──   CRASH_AFTER_HEADER    : committed, nothing installed
   install_trans()      for each block: write home location
        └─ hook stage 3 after each block: CRASH_DURING_INSTALL (n-th hit)
   ── hook stage 4 ──   CRASH_AFTER_INSTALL   : installed, header not cleared
   write_head() (n=0)   clear the log
```
`log_write` is not the interesting half: the crashes after the commit point can only be reached from
inside `commit()`, which is why `crashhook` exists. A *DURING_INSTALL* point is the "move the crash
point inside `install_trans`" viva change: it is a one-line change in `install_trans()`.

## What each trial checks (`tests/cases/c_crash.py`)
1. **Atomicity on the dead disk**: after applying the log in memory, "file effect present" ⇔ "table entry present".
2. Expected classification: staging / stage 1 → uncommitted; stage 2,3,4 → committed.
3. Boot recovery installed exactly `log.n` blocks (`recovering tail ...` lines counted).
4. First replay is `EXECUTED` if uncommitted, `REPLAYED` if committed; second replay `REPLAYED`; same `rc`.
5. Final disk: payload exactly once, one table entry with the right result, filesystem consistent, log empty.
6. The image **file** is the same inode before the crash, after the crash and after replay.

Sweeps: `C1` append in a block, `C2` append across a block boundary (new data block + bitmap),
`C3` CREATE, `C4` `C1` on 3 CPUs, `C5` worst-case append across direct→indirect. The result tables
(one row per crash point) are in `docs/test-results.md` and `evidence/final/<case>/case.json`.
