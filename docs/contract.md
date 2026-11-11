# Shared contract (frozen interface)

Source of truth in code: `kernel/effect.h`. This page is the prose version.
Nobody changes an item below without telling the other two members.

## 1. System calls

| # | call | purpose | test-only? |
|---|---|---|---|
| 23 | `int effect(uint64 key, int op, const char *path, const void *buf, int n)` | the assigned exactly-once syscall | no |
| 24 | `int crashat(int n)` | panic at the n-th `log_write()` after arming (0 = disarm) | **yes** |
| 25 | `int crashhook(int stage, int n)` | panic at a named point inside `commit()` (stage 0 = disarm) | **yes** |
| 26 | `int effstat(struct effstats *st)` | read counters (executed, replayed, table_used, disk writes ...) | no (read-only) |

"Test-only" means: compiled only with `-DEFFECT_TESTHOOKS` (Makefile `TESTHOOKS=1`, the default
for our test builds). A production build `make clean && make TESTHOOKS=0 qemu` removes the hook
code and the two calls return `EFF_EPERM` (-7). Test R2 proves this.

## 2. `effect(key, op, path, buf, n)`

* `key` – full **64-bit** idempotency key, read with `argaddr()` (never `argint()`). `0` is
  reserved (marks an empty table slot) and is rejected.
* `op` – `EFF_APPEND = 1` (append to an **existing regular** file) or `EFF_CREATE = 2` (create a
  **new** regular file containing the bytes).
* `path` – absolute path (`/name`, root directory in all our tests; the kernel itself accepts any
  absolute path whose parent exists).
* `buf`, `n` – payload (copied with `copyin`, never dereferenced). `0 <= n <= 256`; APPEND needs `n >= 1`.

### Return value

| value | name | meaning | recorded in table? |
|---|---|---|---|
| `>= 0` | result | bytes written (APPEND) / bytes of initial content (CREATE). Same value on replay. | **yes** |
| -1 | `EFF_EINVAL` | bad key/op/length/path pointer, not a regular file, parent missing, would exceed max file size | no |
| -2 | `EFF_ENOENT` | APPEND target does not exist | no |
| -3 | `EFF_EFULL` | table full (checked **before** the file is touched) | no |
| -4 | `EFF_EMISMATCH` | key already completed with a **different** (op, path, payload) | no |
| -5 | `EFF_EIO` | disk full before the first byte could be written | no |
| -6 | `EFF_EEXIST` | CREATE target already exists | no |
| -7 | `EFF_EPERM` | crash hooks requested in a production build | – |

Rule: **errors are never stored**, so a retry after an error is always safe. A key whose only
attempts failed has never "completed" and may be reused.

### Semantics

1. Key unknown → perform the effect, record `{key, result, signature}` **in the same transaction**.
2. Key known, same request → return the stored result, change nothing (cost: 0 disk writes).
3. Key known, different request → `EFF_EMISMATCH`, change nothing.
4. The call returns only after its transaction is durable (waits for the commit; see kernel-design §5).
5. Short writes (disk full part-way): the bytes actually written are the result and are recorded
   together with the key (replay returns the same short count). No all-or-nothing claim.

### Signature
`sig = FNV-1a-32( op byte, path bytes, 0x00, payload bytes )`, stored next to the key. Detects key
reuse with a different request. (2^-32 collision chance: a documented limitation, not a security boundary.)

## 3. On-disk table (see `docs/disk-format.md`)
16-byte entries `{uint64 key; int32 result; uint32 sig}`, 64 per 1 KB block, `EFF_TABLE_BLOCKS = 1`
block reserved by `mkfs`, location in the superblock (`effstart`, `effblocks`). Little-endian.

## 4. Crash stages for `crashhook(stage, n)`

| stage | constant | where in `commit()` | durable state at that instant |
|---|---|---|---|
| 1 | `CRASH_BEFORE_HEADER` | log blocks written, header not yet | uncommitted → recovery installs nothing |
| 2 | `CRASH_AFTER_HEADER` | header written = **commit point** | committed, nothing installed |
| 3 | `CRASH_DURING_INSTALL` | after the n-th home-block write | committed, partly installed |
| 4 | `CRASH_AFTER_INSTALL` | all installed, header not cleared | committed, fully installed |

`crashat(n)` panics at the n-th `log_write()`; all those points are before the commit point.

## 5. Guest protocol (`agentcall`, see `docs/bridge.md`)
```
agentcall ID list
agentcall ID read   /path
agentcall ID append KEYHEX /path HEXPAYLOAD
agentcall ID create KEYHEX /path HEXPAYLOAD
-> @@BEGIN ID / "| " prefixed body lines / @@END ID rc=N status=S
```

## 6. Utilities in the guest
`effectctl` (human front end, prints `EFFECT op=.. key=.. rc=.. outcome=EXECUTED|REPLAYED|ERROR`),
`crashctl`, `effstat`, `effstress` (concurrency / table fill), `effraw` (hostile arguments),
`diskfill`, `agentcall`.

## 7. Limits
`EFF_MAXPAYLOAD = 256` B (kernel); agent payload ≤ 32 chars; table 64 entries; `MAXOPBLOCKS = 10`,
`LOGBLOCKS = 30` (xv6 constants).
