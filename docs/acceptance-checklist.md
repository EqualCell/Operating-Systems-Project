# Acceptance checklist — plan (3 students, 60 %) vs evidence

Legend: ✅ done and tested (test id / file) · 🟡 done, limited · ⬜ not done (stated honestly) · 👤 the team must supply

## Person 1 — kernel
| item (from the plan) | status | evidence |
|---|---|---|
| `make qemu` builds and boots | ✅ | `A1` (boot + `ls`), `./run_tests.sh` builds from scratch |
| user program calls the new syscall | ✅ | `A2`, `effectctl` |
| key above 32 bits is preserved | ✅ | `B4` (6 keys incl. same-low-32-bit pairs), mutant `truncate-key` caught |
| new key appends the expected bytes | ✅ | `B1` (independent file parse + table entry + independent signature) |
| repeating the same key does not append again | ✅ | `B2` (3 replays: 0 disk writes, 0 log writes) |
| table entry survives reboot | ✅ | `B6` |
| file update and table entry share one transaction | ✅ | `C1`–`C5` atomicity check at every crash point; GDB transcript `evidence/gdb-commit-inspection.txt`; mutant `split-transaction` caught |
| table-full detected before file mutation | ✅ | `B9` (also CREATE refused, no file left) |
| same-key concurrent calls serialised | ✅ | `B10a` (3 CPUs, 8 trials × 6 procs), `B10b` (1 CPU), `B11`, `B12` |
| representative pre- and post-commit crash/replay | ✅ | `C1`–`C5`: **every** `log_write` point + stages 1–4 (+ every install step) |
| `crashat(n)` | ✅ | `kernel/log.c`, `crashctl at N`, `C*` |
| `CREATE` implemented | ✅ | `B8`, `C3` |
| different payload under same key: policy | ✅ | `B5` (EMISMATCH, file untouched) |
| lock order, block budget, limitations documented | ✅ | `docs/kernel-design.md`, `E1` |
| production build has no crash injection | ✅ | `R2` |
| stock xv6 still works | ✅ | `R1` (`usertests -q`, 3 CPUs; run with `--slow`) |
| disk-full behaviour | 🟡 | `B13`: short write recorded, zero-progress `EIO`; no all-or-nothing claim |
| crash during recovery | ⬜ | cannot be armed from user space (limitations.md) |

## Person 2 — agent
| item | status | evidence |
|---|---|---|
| Python accepts a user goal; planner emits structured action | ✅ | `agent/planner.py`, unit tests |
| validator rejects unknown tools / malformed arguments / bad paths | ✅ | `U1` (23 unit tests, 26+ rejection cases) |
| `list_files`, `read_file` work against the real xv6 | ✅ | `D1`, `D2` (+ `summarize` host tool `D3`) |
| bridge detects timeout / malformed output; never invents success | ✅ | `D11` (frozen guest, panic, 6 malformed frames) |
| `append_file` reaches the real syscall | ✅ | `D4` (key on disk equals journaled key) |
| retry reuses the same key + arguments | ✅ | `D5` lost reply, `D6` crash pre/post commit, `D7` host restart |
| prompt-injection test repeatable, inside the disposable guest | ✅ | `D8`, `D10` (forged frame) |
| no model output executed as a host command | ✅ | fixed templates + hex payload; `U1` `test_payload_is_hex_no_metachars`; `D9` guest allowlist |
| LLM planner | ⬜ | deliberately not built (handout: only after tools work) |
| kernel (taint) enforcement of the injection policy | ⬜ | **tool-layer refusal only**; ask the instructor if Project 4 must include Project 3's taint demo |

## Person 3 — tests / evidence
| item | status | evidence |
|---|---|---|
| one command builds and runs the suite | ✅ | `./run_tests.sh` |
| same image across crash and replay | ✅ | every `C*` trial records `same_image_inode`; archived block-diffs |
| pre-commit and post-commit crash cases | ✅ | `C1`–`C5` |
| duplicate retry checked from final file contents (not from the agent's message) | ✅ | independent parser `tests/lib/fsimage.py` |
| same-key concurrency run | ✅ | `B10a/b`, `B11`, `B12` |
| logs and test inputs saved | ✅ | `evidence/final/<case>/*.qemu.log`, `case.json` |
| checker catches deliberately broken implementations | ✅ | `M-*` (5 mutants) |
| results distinguish implemented / deferred / failing | ✅ | `docs/limitations.md`, this file |
| one real GDB bug/fix session | 👤 | **not fabricated**. Tooling + an inspection transcript exist (`tests/gdb/inspect_commit.py`); the bug/fix log must come from a bug the team really finds |
| git design notes every two days | 👤 | `docs/design-journal.md` has real entries to start from; commits are the team's to make on their own dates |
| two-page handwritten report, per-student contribution, ZIP | 👤 | material in `docs/`; `tools/make_zip.sh Team_Name_4` builds the ZIP of added/modified files |
| live viva change | 👤 | `docs/viva-guide.md` lists likely changes and where to make them |
