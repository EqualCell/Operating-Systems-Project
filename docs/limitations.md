# Limitations and honest scope statement (60% milestone)

## Implemented and tested
APPEND and CREATE with persistent table, atomic transaction, replay, key-mismatch policy, table-full,
disk-full, `crashat`, commit-stage hooks, every crash point of five scenarios (incl. 3 CPUs), same-key
concurrency, hostile arguments, host agent + bridge + journal, lost reply / crash / host-restart retry,
tool-layer prompt-injection refusal, independent image checker, mutation tests, stock `usertests`.

## Deferred or not claimed
| item | status |
|---|---|
| Kernel enforcement of the prompt-injection policy (taint tracking, Project 3) | **not done**; D8 is a tool-layer (allowlist) refusal only |
| Grants, revocation, version-bound approvals, state preconditions (research extension) | not done (explicitly out of the 60% scope) |
| LLM planner | not done; deterministic planners only (the interface allows one later) |
| Per-key locking | one global sleeplock: effects never run in parallel |
| Table growth / eviction | 64 entries, **no retirement**: once full it stays full (by design: no silent eviction) |
| Crash **during recovery** | cannot be injected from user space (recovery runs at boot); partly covered because `install_trans` is idempotent and stage 3/4 crashes are recovered |
| Caching failures | errors are not recorded; the retry re-evaluates |
| 32-bit request signature | 2⁻³² collision chance for "same key, different request" |
| Multi-file / multi-directory effects | root-directory paths in tests; one file per request; payload ≤ 256 B |
| Agent payload | ≤ 32 printable ASCII chars (console line is 128 B and payload is hex) |
| Timing under real QEMU/KVM hardware | measured under TCG emulation, timings indicative only |
| GDB "real bug found and fixed" log | **not fabricated**: see `docs/design-journal.md`; the team must supply its own from a real bug. A GDB *inspection* transcript of the commit point is in `evidence/gdb-commit-inspection.txt` |
| Exhaustive proof | the crash sweeps are *finite* evidence over the listed points and scenarios, not a proof over all interleavings |

## Things that look like bugs but are not
* `effectctl` prints `outcome=REPLAYED` also when the effect had been committed by a *crashed earlier
  boot*: that is the point.
* xv6 maps address 0 in user space: a `NULL` buffer is a valid pointer there (test `B7` uses an address
  at/after the end of memory instead).
* A panic leaves QEMU spinning; the harness power-cuts it (`SIGKILL`) on purpose.
