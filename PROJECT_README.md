# Exactly-once syscalls across crashes (xv6-riscv)

CSL3030 Operating Systems Lab, IIT Jodhpur — Project 4, 3-student 60% scope.
Built on [mit-pdos/xv6-riscv](https://github.com/mit-pdos/xv6-riscv) (base commit `fa2ddcb`).
The original xv6 README is kept as `README`.

## What it does
`effect(key, op, path, buf, n)` is a system call that performs a file change (APPEND or CREATE)
**exactly once**, even if the machine crashes and the request is retried. The kernel keeps a
persistent `key -> result` table and writes the table entry and the file change in the **same xv6 log
transaction**, so after any crash the disk holds both or neither. A Python agent drives xv6 in QEMU
through a framed bridge and retries with the same key after a lost reply, crash or host restart.

## Layout
| path | what |
|---|---|
| `kernel/effect*.c/h` | syscall, persistent table, APPEND/CREATE |
| `kernel/log.c` | crash-injection hooks (`crashat`, `crashhook`) |
| `user/` | `effectctl`, `crashctl`, `effstat`, `effstress`, `effraw`, `diskfill`, `agentcall` |
| `agent/` | planner, tool validator, journal, bridge, QEMU driver |
| `tests/` | test framework, independent disk-image checker, 42 cases, mutants, GDB script |
| `docs/` | start at `docs/README.md` |
| `evidence/final/` | raw logs and results of the recorded run |

## Quick start
```sh
source env.sh            # only if the toolchain is unpacked in ~/toolchain/root (see docs/setup.md)
./run_tests.sh --slow    # build + all 42 cases, writes evidence/<run>/
python3 demo.py          # narrated crash -> reboot -> retry -> exactly-once demo
make qemu                # interactive xv6; try: effectctl append 1 /log.txt hi
```
Requirements: `gcc-riscv64-linux-gnu`, `qemu-system-riscv64`, Python 3.

## Status
42/42 cases pass (330 checks), including 78 crash/replay trials and 5 mutation tests.
Prompt-injection refusal is tool-layer only (not kernel taint enforcement); no LLM planner.
See `docs/limitations.md` and `docs/acceptance-checklist.md`.
