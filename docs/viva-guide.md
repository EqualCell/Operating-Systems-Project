# Viva guide

## 60-second answer
"`effect()` takes a 64-bit key. In **one** xv6 log transaction the kernel looks the key up in an
on-disk table; if it is absent it does the append/create and writes the key and result into the same
transaction; if present it returns the stored result. xv6's `commit()` has a single atomic moment —
`write_head()` — so after any crash both the file change and the key are on disk or neither is.
A retry therefore either does the work once or returns the old result. The Python agent saves the key
*before* sending, and retries with the same key after timeouts or restarts."

## Questions you should expect
| question | answer |
|---|---|
| Why `argaddr` for the key? | `argint` returns 32 bits; keys differing only above bit 31 would collide. Test `B4`; mutant `truncate-key` shows the failure. |
| Why one transaction? | Two transactions leave a window where the file changed but the key is missing → a replay appends twice. Mutant `split-transaction`: the suite reports `ATOMICITY VIOLATED` and a duplicated payload. |
| What is the commit point? | `write_head()` with `n > 0` in `commit()`. Before: recovery sees an empty log. After: it installs every logged block. |
| Why a lock *before* `begin_op`? | So nobody waits for another effect while holding a transaction slot; two same-key callers can't both miss the table. |
| Is `end_op()` returning = durable? | Not in this tree (group commit). `sys_sync()` after unlocking waits for the commit. |
| What happens on disk-full? | Short write is recorded; zero progress → EIO, unrecorded. We don't claim all-or-nothing. Test `B13`. |
| Same key, other payload? | `EFF_EMISMATCH` (signature differs). Test `B5`. |
| Table full? | Refused **before** the file is touched; replays of stored keys still work. Test `B9`. |
| What does a replay cost? | 0 log writes, 0 disk writes (`B2`, `E1`). An executed append costs 2L+2 writes, L=3 for an in-block append. |
| Why `crashhook` in addition to `crashat`? | `log_write` only runs while staging (before the commit point). |
| How do you know the tests can fail? | Five mutant kernels, each caught by its test (`M-*`). |
| Where is the injection defence? | Validator allowlist + guest allowlist; **not** kernel enforcement — say so. |
| What is UNKNOWN? | Timeout/panic/garbage: the effect may have happened. Retry with the same key. |
| Why hex payload? | xv6 `sh` has no quoting; hex removes every metacharacter problem. |
| Why journal before send? | If the host forgot the key it would invent a new one and the effect would happen twice. `D7`. |

## Likely live changes ("small change on the spot") and where to make them
| change | where |
|---|---|
| crash inside `install_trans` | already there: `crashctl stage 3 N`; or add `crash_stage_check(CRASH_DURING_INSTALL)` elsewhere in `log.c` |
| bigger/smaller table | `EFF_TABLE_BLOCKS` in `kernel/effect.h`, then `make clean && make` |
| change the payload limit | `EFF_MAXPAYLOAD` (watch the block budget: re-run `E1`/`C5`) |
| make mismatch replay instead of refuse | `sys_effect`: the `e.sig != sig` branch |
| record failures too | `sys_effect`: call `store_put` also when `res < 0` (and decide replay semantics) |
| per-key lock instead of a global one | replace `effect_lock` by a small table of key-hashed sleeplocks; keep the order `lock → begin_op` |
| new op (e.g. TRUNCATE) | new `effect_do_*` in `effect_ops.c`, a constant in `effect.h`, a branch in `sys_effect`, extend the signature |

## Demo script (5 minutes)
```sh
./run_tests.sh --only B2 B4        # duplicate key, high-bit keys
python3 demo.py --crash post       # crash after commit point, reboot same disk, retry, exactly once
python3 demo.py --crash lost       # lost reply
python3 tests/run_all.py --only M-split-transaction   # the checker catching a broken kernel
cat evidence/final/results.md | head -60
```
