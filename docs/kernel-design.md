# Kernel design: how exactly-once works (Person 1's module)

Files: `kernel/effect.c` (syscalls + orchestration), `kernel/effect_store.c` (persistent table),
`kernel/effect_ops.c` (APPEND / CREATE), `kernel/log.c` (crash hooks, `log_nblocks`),
`kernel/bio.c` (disk-write counter), `kernel/fs.h`, `mkfs/mkfs.c` (layout), `kernel/sysfile.c`
(`create()` made non-static), `kernel/syscall.*`, `kernel/defs.h`, `user/*`, `Makefile`.

## 1. The core idea in one paragraph
xv6 already makes a *group of block writes* crash-atomic: `commit()` copies the blocks into the log,
writes the log header (`write_head()`, **the only atomic moment**), installs the blocks, clears the
header. If the machine dies before the header lands, recovery sees an empty log and installs nothing.
If it dies after, recovery installs every logged block. So if the **file change and the table entry
are blocks of the same transaction**, the disk after any crash contains either both or neither.
`effect()` is nothing more than "lookup → (do the work + insert the key) inside one transaction".

## 2. `sys_effect` step by step (`kernel/effect.c`)
```
1  argaddr(0,&key) ...                      64-bit key via argaddr (argint would truncate to 32 bits)
2  validate (key!=0, op, n, path, copyin)   before any lock or disk access; payload copied to kernel buffer
3  acquiresleep(&effect_lock)               one effect at a time (also serialises same-key racers)
4  begin_op()                               ONE transaction
5  store_find(key)                          reads the persistent table
     found, same sig  -> res = stored result            (replay)
     found, other sig -> EFF_EMISMATCH
     absent, no slot  -> EFF_EFULL                      (nothing modified yet)
     absent, slot s   -> res = do_append/do_create()    (file blocks logged)
                         if res >= 0: store_put(s,...)  (table block logged, SAME transaction)
6  end_op()                                 commit happens here if we are the last operation
7  releasesleep(&effect_lock)
8  sys_sync()                               wait until the commit containing our blocks is durable
9  return res
```

## 3. Why every crash point is safe (the argument the report needs)
Let T = the set of blocks of one effect (file inode/data/bitmap blocks + the table block).

| crash instant | disk state | recovery | replay of the same key |
|---|---|---|---|
| any `log_write` (staging) | nothing written to disk; log header `n = 0` | nothing | key absent → effect executes **once** |
| `BEFORE_HEADER` | T in log area, header `n = 0` | ignores log | key absent → executes once |
| `AFTER_HEADER` (commit point) | header lists T | installs all of T | key present → returns stored result, no change |
| `DURING_INSTALL` (h blocks done) | header lists T, some home blocks written | installs all of T again (idempotent copy) | key present → replay |
| `AFTER_INSTALL` | T installed, header still lists T | re-installs (same bytes) | key present → replay |
| after header cleared | T installed, `n = 0` | nothing | key present → replay |

A single block write is atomic on the virtual disk, so there is no third case. Table and file are
never split because both are in T. The tests check exactly this table (`C1`–`C5`), and the
mutants `split-transaction` and `commit-order` show the tests fail when it is violated.

## 4. Locking (outermost first)
```
effect_lock (sleeplock)  ->  log (begin_op/end_op)  ->  inode locks (ilock)  ->  buffer locks (bread)
```
* `effect_lock` is taken **before** `begin_op`: a process never waits for another effect while it
  occupies a transaction slot (no circular wait).
* inode locks are released (`iunlockput`) before `end_op`.
* no spinlock is held across disk I/O (`effect_lock` is a sleeplock, so waiting for the commit under it is legal).
* `effstat` takes the same locks in the same order.

A single global lock is the "first version" the plan allows. It means two effects never run in
parallel (throughput limit), but it makes the same-key race impossible by construction: the second
process sees the first one's table entry because the buffer cache is shared. Tests `B10a/B10b/B11/B12`.

## 5. Durability acknowledgement (group commit)
In this xv6 tree `end_op()` commits **only if no other FS operation is in flight**; otherwise the last
operation to finish commits for everybody. So `end_op()` returning does *not* mean "durable".
`sys_effect` therefore calls `sys_sync()` after releasing its locks: it waits for the commit that
contains our blocks (a no-op when our own `end_op` did the commit). Replays also wait, so a replay
can never report a result that is not yet durable.

## 6. Block budget
`begin_op()` reserves `MAXOPBLOCKS = 10` log blocks. Measured (test `E1`/`C*`, distinct logged blocks L):

| operation (test) | `log_write` calls K | distinct logged blocks L | disk writes (= 2L+2) | headroom vs MAXOPBLOCKS=10 |
|---|---|---|---|---|
| APPEND inside a block (`E1`,`C1`) | 3 | 3 (inode, data, **table**) | 8 | 7 |
| APPEND crossing a 1 KB boundary (`E1`,`C2`) | 6 | 5 (inode, 2 data, bitmap, **table**) | 12 | 5 |
| APPEND direct→indirect, worst case seen (`E1`,`C5`) | 9 | 6 | 14 | 4 |
| CREATE (`E1`,`C3`) | 9 | 6 | 14 | 4 |
| replay / any refusal (`B2`,`E1`) | 0 | 0 | 0 | – |

K counts `log_write()` *calls* (the same block can be logged several times: log absorption makes L ≤ K);
`crashat(n)` sweeps n = 1..K. Disk writes were measured with a counter in `bwrite()` and equal 2L+2 in
every executed case (L log copies + header + L installs + header clear).

The table block is exactly **one** of the L blocks: the exactly-once record costs +1 log block =
+2 disk writes per executed effect. The payload cap (256 B) is what keeps L ≤ 10. No transaction is
ever split to fit a bigger append.

## 7. Short writes and errors
xv6 logging does not undo a failed C function. Our rule: validation errors happen before any change;
`ENOENT/EINVAL/EEXIST` are decided before any block is modified; if the disk fills mid-append the
bytes that did get written are the recorded result (short write). Zero-progress → `EIO`, not recorded.
Test `B13` exercises all three on a completely full disk.

## 8. Not done (see `docs/limitations.md`)
No permission/grant model, no revocation, no per-key locks (one global lock), table has no
eviction (full is permanent), one signature of 32 bits, no crash injection *during recovery* (recovery
runs before user space exists, so it cannot be armed from a program).
