# Fresh verification summary

Source revision: `b252d07ba0566d6929583e72bae57eed524140c3`; dirty entries: 0.
Results: **80 PASS, 0 FAIL, 0 ERROR**; 658 checks; 310.0 seconds.

Command: `./run_tests.sh --slow` (all cases, including independent crash checks, mutants and stock usertests).
Run date: 2026-11-17. Raw outputs for this run are retained locally in `evidence/run-20261117-184354/` (ignored).

## Environment

- date: `2026-11-17T18:43:54.287410+05:30`
- host: `Linux-7.0.0-38-generic-x86_64-with-glibc2.43`
- python: `3.14.4`
- qemu: `QEMU emulator version 10.2.1 (Debian 1:10.2.1+ds-1ubuntu3.3)`
- riscv_gcc: `riscv64-linux-gnu-gcc (Ubuntu 15.2.0-16ubuntu1) 15.2.0`
- source_revision: `b252d07ba0566d6929583e72bae57eed524140c3`
- git_dirty_files: `0`
- kernel_sha256: `c40dba2546da1851049313c248616c1f6e88589fc1c44290276da2e3f2fd9af0`
- pristine_fs_img_sha256: `eaf41a88aa1091bc717891a1f73782c6944450ef0dc9253adb91737549256f29`
- qemu_machine: `virt, -bios none, 128M, virtio-blk (legacy off)`

## Cases

| Case | Group | Result | Checks | Seconds |
|---|---|---|---|---|
| S-auth | security | PASS | 5/5 | 0.52 |
| S-invalid | security | PASS | 4/4 | 0.47 |
| S-stale | security | PASS | 4/4 | 1.02 |
| S-same | security | PASS | 6/6 | 0.52 |
| S-different | security | PASS | 6/6 | 0.54 |
| S-revoke | security | PASS | 5/5 | 0.5 |
| S-capacity | security | PASS | 8/8 | 1.5 |
| S-create-race | security | PASS | 4/4 | 1.26 |
| S-legacy-create-race | security | PASS | 4/4 | 0.93 |
| S-distinct | security | PASS | 4/4 | 1.59 |
| S-keys | security | PASS | 8/8 | 1.0 |
| S-crash-issue-1 | security-crash | PASS | 5/5 | 0.82 |
| S-crash-issue-2 | security-crash | PASS | 5/5 | 0.73 |
| S-crash-issue-3 | security-crash | PASS | 5/5 | 0.72 |
| S-crash-issue-4 | security-crash | PASS | 5/5 | 0.76 |
| S-crash-effect-1 | security-crash | PASS | 10/10 | 0.98 |
| S-crash-effect-2 | security-crash | PASS | 10/10 | 0.94 |
| S-crash-effect-3 | security-crash | PASS | 10/10 | 0.85 |
| S-crash-effect-4 | security-crash | PASS | 10/10 | 0.96 |
| S-crash-revoke-1 | security-crash | PASS | 7/7 | 0.84 |
| S-crash-revoke-2 | security-crash | PASS | 7/7 | 0.87 |
| S-crash-revoke-3 | security-crash | PASS | 7/7 | 0.83 |
| S-crash-revoke-4 | security-crash | PASS | 7/7 | 0.96 |
| S-create | security | PASS | 8/8 | 0.94 |
| S-manual | security | PASS | 37/37 | 3.16 |
| S-format | security | PASS | 1/1 | 0.17 |
| S-diskfull | security | PASS | 17/17 | 16.93 |
| S-budget | security | PASS | 7/7 | 0.58 |
| S-comparison | comparison | PASS | 7/7 | 1.7 |
| S-create-budget | security | PASS | 7/7 | 0.98 |
| S-controller-recovery | security | PASS | 16/16 | 2.89 |
| S-create-crash-1 | security-crash | PASS | 6/6 | 0.98 |
| S-create-crash-3 | security-crash | PASS | 6/6 | 1.03 |
| S-create-crash-4 | security-crash | PASS | 6/6 | 0.99 |
| S-overlap | security | PASS | 56/56 | 21.22 |
| A1 | baseline | PASS | 16/16 | 0.48 |
| A2 | baseline | PASS | 5/5 | 0.46 |
| B1 | behaviour | PASS | 7/7 | 0.4 |
| B2 | behaviour | PASS | 9/9 | 0.76 |
| B3 | behaviour | PASS | 3/3 | 0.5 |
| B4 | behaviour | PASS | 4/4 | 0.99 |
| B5 | behaviour | PASS | 8/8 | 0.69 |
| B6 | behaviour | PASS | 4/4 | 0.8 |
| B7 | behaviour | PASS | 22/22 | 1.52 |
| B8 | behaviour | PASS | 10/10 | 0.68 |
| B9 | behaviour | PASS | 10/10 | 2.21 |
| B10a | concurrency | PASS | 6/6 | 1.16 |
| B10b | concurrency | PASS | 2/2 | 0.79 |
| B11 | concurrency | PASS | 3/3 | 0.81 |
| B12 | concurrency | PASS | 8/8 | 1.15 |
| B13 | behaviour | PASS | 12/12 | 14.51 |
| C1 | crash | PASS | 13/13 | 10.12 |
| C2 | crash | PASS | 18/18 | 14.53 |
| C3 | crash | PASS | 22/22 | 18.29 |
| C4 | crash | PASS | 13/13 | 10.68 |
| C5 | crash | PASS | 22/22 | 18.14 |
| D1 | agent | PASS | 8/8 | 0.45 |
| D2 | agent | PASS | 3/3 | 0.45 |
| D3 | agent | PASS | 2/2 | 0.36 |
| D4 | agent | PASS | 4/4 | 0.55 |
| D5 | agent | PASS | 7/7 | 0.65 |
| D6 | agent | PASS | 14/14 | 1.8 |
| D7 | agent | PASS | 9/9 | 1.13 |
| D8 | agent | PASS | 7/7 | 0.42 |
| D9 | agent | PASS | 10/10 | 0.98 |
| D10 | agent | PASS | 3/3 | 0.55 |
| D11 | agent | PASS | 11/11 | 3.8 |
| E1 | measure | PASS | 12/12 | 2.17 |
| E2 | measure | PASS | 2/2 | 4.59 |
| U1 | unit | PASS | 2/2 | 0.04 |
| R1 | regress | PASS | 3/3 | 88.01 |
| R2 | regress | PASS | 8/8 | 1.81 |
| M-truncate-key | mutation | PASS | 2/2 | 1.67 |
| M-split-transaction | mutation | PASS | 2/2 | 9.96 |
| M-no-replay-lookup | mutation | PASS | 2/2 | 1.59 |
| M-ignore-mismatch | mutation | PASS | 2/2 | 1.43 |
| M-commit-order | mutation | PASS | 2/2 | 10.91 |
| M-grant-no-authority | mutation | PASS | 2/2 | 1.24 |
| M-grant-no-version | mutation | PASS | 2/2 | 2.14 |
| M-grant-no-completion | mutation | PASS | 2/2 | 1.7 |

## Measured transaction budgets

- S-budget: 7 distinct blocks; reservation 10.
- S-create-budget: 7 distinct blocks; reservation 10.

## Interpretation and limits

Mutation-case PASS means the deliberately broken kernel was detected, not that it behaved correctly.
The CPUS=3 BASE/pre/post investigation did not reproduce exec-cat failures in 30 repeated cat commands; executable bytes and allocation metadata were checked.
Tests demonstrate bounded retained-request at-most-once effects and one-time grant consumption under the documented xv6/QEMU redo-log assumptions. They are not an exhaustive interleaving proof or a physical power-loss test.
Protected inodes are pinned permanently; 32 grant/completion slots, no GC, one controller/agent domain, root-only names and 256-byte kernel payloads. Host planner payloads are limited to 32 printable bytes.
Local Ubuntu 26.04.1 toolchain was exercised; Ubuntu 24.04 CI configuration was prepared but no remote CI run or fresh package installation is claimed.

## Source hashes

- `kernel/grant.c`: `762c300de4e9223b82590b66ff7a99910df422fd87ac0079dcec54036a4e57d8`
- `kernel/grant.h`: `88ba570eb23dbfd7db724ef9ba1e34eeaf98ef8cee09af2510038886481731a3`
- `kernel/file.c`: `32e225a0fff381279fcb3608635db351f4b22593fd5af4e3568a98cd256430ba`
- `kernel/proc.c`: `9b2607441af2385da5fbc51ad61e2999b78893f57ee22785c8a8b7dad87bca0f`
- `agent/journal.py`: `1002cf5d292bd68db244c270ad43a4f8e329f4a7a6d436c386426af899fba25a`
- `agent/bridge.py`: `873ad8dceeb26a056ea354ef446b7327ac38d3564ed165154a7dd7c4bb5024bf`
- `agent/agent.py`: `03de7249f6ebe8d3f9032c005dfd09742d52c97768ac156b5dbfc250a81c76ee`
- `agent/controller.py`: `00c447f56fc752478fbc19cfd760d1b4cae60d89594ecdb0ac25f02bf030ae39`
- `user/grtest.c`: `0ec71a5f6c54634cae90282aea9fadb6d9c470bfd7968311ee1df764fe556abd`
- `kernel/effect.c`: `8abaa66ad4b969fd56a020b1f105a928d7b435bb3a95ab2ab30e3989b4e89b0b`
- `kernel/effect_store.c`: `429f062a5ace364209b778a0acf46b8dab9c9c7965b2d219b59a40c44664e62b`
- `kernel/effect_ops.c`: `6e4d0d5753fdb6dffd8adfdcbf5b6eb843da6e8a6dc91189c6ef4c8e443963f4`
- `kernel/effect.h`: `39cd2078bd3af5bdc74c9ef96c69e9f72ff794ac6182392a387d23fb167352d1`
- `kernel/log.c`: `3286c9fa3ae8f70c7498b1736ed90c0d7ee1bdc00a55be6af331cb82d39e8e9d`
- `kernel/fs.h`: `c6d6b5fc3ca428c0c5992e1f67ec3b4c302961c195de051b592b3f61c2445abb`
- `mkfs/mkfs.c`: `7b6d0c5ce25c3121857c3b37c412b1a8ca116999ee40df0b831ccba3a4cdb50e`
- `kernel/sysfile.c`: `be3e855a7f5a09edf66fc21a5a79c927975a5e646d5ae155b1ae4fb3455482b6`
- `kernel/fs.c`: `9a4b913984450638a67f320f1ea76f2e0e8550a1cf576d010518584a215b8172`
- `kernel/bio.c`: `386776864eec7c3e816f491c14f72166a91645460a395c1b900721f5841e6760`

## Publication verification

This fresh full run includes the controller recovery fix. Previous evidence is
preserved byte-for-byte in [initial-validation.md](history/initial-validation.md);
its original revision and narrower validation remain unchanged.

The ensuing commit changes evidence only. The exact tested code revision above
is the branch HEAD immediately before that evidence commit; no code changed
while testing or afterward.

Exact host commands (installed Ubuntu 26.04.1 toolchain):

```sh
PYTHONUNBUFFERED=1 ./run_tests.sh --slow
make test-build
python3 demo.py --crash none
python3 demo.py --crash pre
python3 demo.py --crash post
python3 demo.py --crash lost
make production
```

### Four fresh demos

| Mode | Final outcome | Attempts | Exit |
|---|---|---|---|
| none | EXECUTED | 1 | 0 |
| pre | EXECUTED | 2 | 0 |
| post | REPLAYED | 2 | 0 |
| lost | REPLAYED | 2 | 0 |

Each demo used a new dedicated image, verified exactly one effect offline,
and replayed the extra identical request. Crash/lost-reply cases recorded
UNKNOWN before retrying.

### Production

Configuration: `TESTHOOKS=0 UNSAFE_COMPARISONS=0`. Build succeeded; injection strings
are absent from the binary. Runtime checks on CPUS=3:

- `crashctl at 1` → `CRASHCTL rc=-7`.
- `crashctl stage 2 1` → `CRASHCTL rc=-7`.
- `compare` → `unsafe comparisons disabled`.

Production kernel SHA-256: `4c7013d82b5a23c3d4d16240c8ec4570e6261610eecf7a47e8ab955597c2f117`.

### Repository audit

README quick-start commands were executed successfully and local links resolve.
The tracked-file audit found no ELF binaries, build products, disk images, or
common credential patterns. This heuristic scan does not prove the absence of
every possible secret. MIT license and upstream acknowledgments are unchanged.
Generated outputs remain ignored; nothing was pushed.

### Remaining limits

32 retained grants with no garbage collection; permanently pinned protected
inodes; one shared authority domain; root-only CREATE names; 256-byte kernel
payloads. Physical power loss, arbitrary disk corruption and exhaustive
interleavings are outside the validated scope. Ubuntu 24.04 installation and
remote CI were not exercised.
