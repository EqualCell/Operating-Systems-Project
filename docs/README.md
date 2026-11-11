# Documentation index

| read this | when |
|---|---|
| [overview.md](overview.md) | first: the problem, the idea, the picture, who owns what |
| [contract.md](contract.md) | the frozen interface (syscalls, results, table, protocol) |
| [kernel-design.md](kernel-design.md) | how `effect()` works, lock order, durability, block budget (Person 1) |
| [crash-points.md](crash-points.md) | `commit()` timeline, hooks, what each trial checks, hand-run example |
| [disk-format.md](disk-format.md) | layout, superblock fields, table entry |
| [bridge.md](bridge.md) | agent, tools, validator, framing, journal, injection demo (Person 2) |
| [experiments.md](experiments.md) | how to run, catalogue, what is recorded, measured results (Person 3) |
| [test-results.md](test-results.md) | generated report: every case, every crash point, costs, mutants |
| [acceptance-checklist.md](acceptance-checklist.md) | the plan's checklists vs evidence; what is not done |
| [limitations.md](limitations.md) | honest scope statement |
| [viva-guide.md](viva-guide.md) | questions, live-change cookbook, 5-minute demo |
| [design-journal.md](design-journal.md) | what really failed during the build |
| [setup.md](setup.md) | toolchain (incl. the no-root method), commands |

Quick start: `./run_tests.sh --slow` · `python3 demo.py` · `python3 tests/run_all.py --list`
