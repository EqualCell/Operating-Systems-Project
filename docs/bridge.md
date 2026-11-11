# Host ↔ guest bridge (Person 2's module)

```
user goal ─▶ planner ─▶ {"tool","args"} ─▶ validate_action ─▶ agent ─▶ bridge.build_command
          "append hi to /log.txt"          allowlist+schema      │       "agentcall 101 append 6c3f.. /log.txt 6869"
                                                                 ▼
 QEMU serial console  ◀──────────────  xv6 shell runs agentcall ─▶ effect() system call ─▶ disk
          ▲        "@@BEGIN 101 / | EFFECT ... / @@END 101 rc=2 status=EXECUTED"
          └──── parse_reply ◀── only a complete frame with the SAME attempt id counts
```

## Method (one bridge, documented)
Serial-console interaction with **one fixed guest program**, `agentcall`. We type one line, wait for
the shell prompt `$ `, parse the framed output. (`agent/qemu.py` = console I/O, `agent/bridge.py` = framing.)

## Frame format
```
@@BEGIN <attempt-id>
| <body line>           every content line is prefixed with "| "
@@END <attempt-id> rc=<int> status=<OK | EXECUTED | REPLAYED | ERR:reason>
```
* `attempt-id` identifies one **send** (communication attempt). It is **not** the effect key. A retry
  gets a new attempt id but the **same key**.
* The `| ` prefix means file content can never look like a frame line (test `D10`).
* Console echo of our own command line is stripped; xv6 prints `\n` only, `\r` is removed.

## Guest commands (allowlist; anything else → `ERR:unknown-command`)
| command | does |
|---|---|
| `agentcall ID list` | names, type, size of root directory entries |
| `agentcall ID read /path` | first 1024 bytes of a file |
| `agentcall ID append KEYHEX /path HEX` | `effect(key, APPEND, ...)` |
| `agentcall ID create KEYHEX /path HEX` | `effect(key, CREATE, ...)` |

Guest-side checks (second defence, test `D9`): path = one leading `/` + `[A-Za-z0-9._-]`, ≤ 32 chars;
key = 1–16 hex digits, non-zero; payload = even-length hex, ≤ 32 bytes, printable ASCII. The payload
is hex so no shell metacharacter or quoting rule can matter (xv6 `sh` has no quoting).
Console line limit is 128 bytes; `build_command` refuses lines ≥ 120.

## Reply classification (`GuestReply.status`)
| status | meaning | agent action |
|---|---|---|
| `OK` | complete frame, `rc >= 0` | success |
| `ERR` | complete frame, `rc < 0` (guest or kernel refused) | **definitive** failure, journal `failed` |
| `UNKNOWN` | timeout, panic, no `@@END`, garbage, wrong id, injected loss | **outcome unknown**: retry with the same key |

`UNKNOWN` is never reported as success and never as failure. After a panic/timeout the bridge flags
`needs_restart`; `recover()` power-cycles QEMU **on the same disk image**, so xv6 recovery runs at boot.

## Retry identity (`agent/journal.py`)
1. `journal.begin()` generates the 64-bit key **once**, writes `{key, tool, args}` (JSON line + `fsync`).
2. Each send is logged as an `attempt` (separate id).
3. Final `result` = `done` / `failed`; an `unknown` result keeps the op *pending*.
4. After a host restart, `Agent.resume()` re-sends every pending op with the stored key and arguments
   (nothing is re-planned, no LLM involved). Tests `D5`, `D6`, `D7`; unit tests in `U1`.

## Safety properties
No `eval`, no host shell; commands are fixed templates over validated arguments; the QEMU guest is a
disposable VM on a disposable disk image; the agent has **no tool** for the crash hooks (the test
harness arms them from the console). `bridge._send_raw_for_tests` exists only to prove guest refusals.

## Tools (`agent/tools.py`)
| tool | args | side effect | where |
|---|---|---|---|
| `list_files` | – | no | guest |
| `read_file` | `path` | no | guest |
| `summarize` | `text` | no | host |
| `append_file` | `path` ∈ `WRITABLE_PATHS`, `text` 1..32 printable ASCII | **yes** (key + journal) | guest |
| `create_file` | `path` ∈ `WRITABLE_PATHS`, `text` | **yes** | guest |

Rejected: unknown tool, missing/extra arguments, wrong types, paths outside the flat allowed pattern
(`..`, relative, sub-directories, spaces, shell characters), appends outside the writable allowlist,
empty/oversize/non-ASCII payloads (unit tests: 23 cases).

## Prompt injection (what is and is not proven)
Test `D8`: `InjectionTestPlanner` (a deliberately gullible, deterministic stand-in for a tricked model)
reads `/inbox.txt`, then proposes `delete_file /important.txt`. The validator refuses it
(`unknown-tool`), it is never sent to the guest, `/important.txt` is byte-identical afterwards, and a
benign `read` still works. **This is tool-layer refusal, not kernel enforcement**: a program that calls
`unlink()` directly is not stopped. Kernel taint tracking (Project 3) is out of scope; ask the instructor
whether Project 4 teams must also deliver that demo.
