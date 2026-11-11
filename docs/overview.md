# Overview in plain words

## The problem
An AI agent asks the OS to do something ("append this line to the log"), the machine crashes or the
reply gets lost, and the agent asks again. A plain `write` then happens **twice**. Nothing is "buggy":
retrying a lost reply is the correct thing to do. What is missing is a way to say *"this is the same
request as before"* — an **idempotency key** — and an OS that remembers which keys it already finished.

## The solution in three sentences
1. The caller attaches a 64-bit **key** to the request: `effect(key, op, path, buf, n)`.
2. The kernel keeps a **table on disk** (`key → result`). Known key → return the old result, do nothing.
   New key → do the work **and** insert the key.
3. The work and the insert are blocks of **one xv6 log transaction**, so a crash leaves both or neither.
   Neither → the retry does the work (once). Both → the retry returns the stored result (once).

## The picture
```
HOST (Ubuntu)                                    GUEST (xv6 in QEMU)
 user: "append hi to /log.txt"
   │ planner (rules)                              agentcall  ──▶ effect(key,APPEND,"/log.txt","hi",2)
   ▼                                                                 │
 {"tool":"append_file",...}                                  ┌───────▼────────────────────────────┐
   │ validator (allowlist, schema)                           │ lock ─ begin_op                    │
   ▼                                                         │  table lookup (key known?)         │
 journal: save key+args  (fsync)  ◀─ before sending          │   yes → return saved result        │
   │ bridge: fixed command + framed reply                    │   no  → append bytes + table entry │
   ▼                                                         │ end_op (commit) ─ wait durable     │
 serial console ──────────────────────────────────────────▶  └────────────────────┬───────────────┘
   ▲ "@@BEGIN 101 ... @@END 101 rc=2"                                              ▼
   └─ UNKNOWN? reboot SAME disk, retry SAME key                                  fs.img
```

## Three rules the whole project rests on
1. **One transaction** covers the file change and the table entry. (`kernel/effect.c`)
2. **Same key + same arguments on every retry.** The key is made once and saved before the first send. (`agent/journal.py`)
3. **Never trust the reply, check the disk.** Tests judge by parsing `fs.img` independently. (`tests/lib/fsimage.py`)

## Who owns what (3 people)
| | role | files | demo in the viva |
|---|---|---|---|
| **Person 1 (heavy)** | kernel: syscall, table, transaction, crash hooks | `kernel/effect*.c/h`, `log.c`, `fs.h`, `mkfs`, `syscall*`, `Makefile`, `user/{effectctl,crashctl,effstat,effstress,effraw,diskfill}.c` | `effectctl` duplicate key; `crashctl stage 2` + reboot; GDB commit inspection |
| **Person 2 (light)** | host agent, tools, validator, bridge, journal, `agentcall` | `agent/`, `user/agentcall.c`, `fixtures/`, `docs/bridge.md` | `python3 demo.py --crash lost`; injection refusal |
| **Person 3 (light)** | tests, independent checker, evidence, mutants, docs | `tests/`, `evidence/`, `docs/test-results.md`, `run_tests.sh`, `tools/` | `./run_tests.sh --group crash`; a mutant failing |

Every member must still be able to explain the whole path (see `docs/viva-guide.md`).

## Reading order
`overview.md` → `contract.md` → `kernel-design.md` → `crash-points.md` → `bridge.md` → `test-results.md` → `limitations.md`.

## Repository map (what we added or changed)
```
kernel/effect.h            shared constants, table entry, stats struct
kernel/effect.c            sys_effect, sys_crashat, sys_crashhook, sys_effstat, the lock
kernel/effect_store.c      persistent table: find / put / count
kernel/effect_ops.c        APPEND, CREATE, request signature
kernel/log.c  bio.c        crash hooks, counters, log_nblocks   (small edits)
kernel/fs.h mkfs/mkfs.c    superblock fields + reserved table block
kernel/sysfile.c fs.c ...  create() made non-static; effectinit() call; syscall tables
user/*.c                   effectctl crashctl effstat effstress effraw diskfill agentcall
fixtures/*.txt             data files baked into fs.img
agent/                     tools.py planner.py agent.py journal.py bridge.py qemu.py __main__.py config.py
tests/                     framework.py run_all.py lib/ cases/ unit/ gdb/ mutants.py
demo.py run_tests.sh env.sh tools/make_zip.sh
docs/                      this folder
evidence/final/            raw logs, per-case json, results.md for the recorded run
```
