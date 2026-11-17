# Fresh verification summary

Source revision: `9812b9591fe923ab84bb9fafcf8199f3eda49a6b`; dirty entries: 0.
Results: **80 PASS, 0 FAIL, 0 ERROR**; 658 checks; 310.3 seconds.

Command: `./run_tests.sh --slow` (all cases, including independent crash checks, mutants and stock usertests).
Run date: 2026-11-17. Raw outputs are regenerated under ignored `evidence/run-*/` directories.

## Environment

- date: `2026-11-17T18:19:46.164182+05:30`
- host: `Linux-7.0.0-38-generic-x86_64-with-glibc2.43`
- python: `3.14.4`
- qemu: `QEMU emulator version 10.2.1 (Debian 1:10.2.1+ds-1ubuntu3.3)`
- riscv_gcc: `riscv64-linux-gnu-gcc (Ubuntu 15.2.0-16ubuntu1) 15.2.0`
- source_revision: `9812b9591fe923ab84bb9fafcf8199f3eda49a6b`
- git_dirty_files: `0`
- kernel_sha256: `c40dba2546da1851049313c248616c1f6e88589fc1c44290276da2e3f2fd9af0`
- pristine_fs_img_sha256: `eaf41a88aa1091bc717891a1f73782c6944450ef0dc9253adb91737549256f29`
- qemu_machine: `virt, -bios none, 128M, virtio-blk (legacy off)`

## Cases

| Case | Group | Result | Checks | Seconds |
|---|---|---|---|---|
| S-auth | security | PASS | 5/5 | 0.53 |
| S-invalid | security | PASS | 4/4 | 0.48 |
| S-stale | security | PASS | 4/4 | 0.83 |
| S-same | security | PASS | 6/6 | 0.52 |
| S-different | security | PASS | 6/6 | 0.53 |
| S-revoke | security | PASS | 5/5 | 0.5 |
| S-capacity | security | PASS | 8/8 | 1.86 |
| S-create-race | security | PASS | 4/4 | 1.03 |
| S-legacy-create-race | security | PASS | 4/4 | 0.89 |
| S-distinct | security | PASS | 4/4 | 1.56 |
| S-keys | security | PASS | 8/8 | 1.0 |
| S-crash-issue-1 | security-crash | PASS | 5/5 | 0.86 |
| S-crash-issue-2 | security-crash | PASS | 5/5 | 0.7 |
| S-crash-issue-3 | security-crash | PASS | 5/5 | 0.77 |
| S-crash-issue-4 | security-crash | PASS | 5/5 | 0.77 |
| S-crash-effect-1 | security-crash | PASS | 10/10 | 0.89 |
| S-crash-effect-2 | security-crash | PASS | 10/10 | 0.87 |
| S-crash-effect-3 | security-crash | PASS | 10/10 | 0.91 |
| S-crash-effect-4 | security-crash | PASS | 10/10 | 0.91 |
| S-crash-revoke-1 | security-crash | PASS | 7/7 | 0.93 |
| S-crash-revoke-2 | security-crash | PASS | 7/7 | 0.88 |
| S-crash-revoke-3 | security-crash | PASS | 7/7 | 0.94 |
| S-crash-revoke-4 | security-crash | PASS | 7/7 | 0.98 |
| S-create | security | PASS | 8/8 | 0.9 |
| S-manual | security | PASS | 37/37 | 3.3 |
| S-format | security | PASS | 1/1 | 0.19 |
| S-diskfull | security | PASS | 17/17 | 17.17 |
| S-budget | security | PASS | 7/7 | 0.53 |
| S-comparison | comparison | PASS | 7/7 | 1.64 |
| S-create-budget | security | PASS | 7/7 | 0.86 |
| S-controller-recovery | security | PASS | 16/16 | 2.98 |
| S-create-crash-1 | security-crash | PASS | 6/6 | 1.01 |
| S-create-crash-3 | security-crash | PASS | 6/6 | 0.95 |
| S-create-crash-4 | security-crash | PASS | 6/6 | 1.0 |
| S-overlap | security | PASS | 56/56 | 16.38 |
| A1 | baseline | PASS | 16/16 | 0.45 |
| A2 | baseline | PASS | 5/5 | 0.46 |
| B1 | behaviour | PASS | 7/7 | 0.4 |
| B2 | behaviour | PASS | 9/9 | 0.77 |
| B3 | behaviour | PASS | 3/3 | 0.5 |
| B4 | behaviour | PASS | 4/4 | 0.93 |
| B5 | behaviour | PASS | 8/8 | 0.61 |
| B6 | behaviour | PASS | 4/4 | 0.82 |
| B7 | behaviour | PASS | 22/22 | 1.48 |
| B8 | behaviour | PASS | 10/10 | 0.74 |
| B9 | behaviour | PASS | 10/10 | 2.35 |
| B10a | concurrency | PASS | 6/6 | 1.14 |
| B10b | concurrency | PASS | 2/2 | 0.76 |
| B11 | concurrency | PASS | 3/3 | 0.87 |
| B12 | concurrency | PASS | 8/8 | 1.14 |
| B13 | behaviour | PASS | 12/12 | 15.64 |
| C1 | crash | PASS | 13/13 | 9.81 |
| C2 | crash | PASS | 18/18 | 14.17 |
| C3 | crash | PASS | 22/22 | 17.62 |
| C4 | crash | PASS | 13/13 | 10.05 |
| C5 | crash | PASS | 22/22 | 17.76 |
| D1 | agent | PASS | 8/8 | 0.45 |
| D2 | agent | PASS | 3/3 | 0.42 |
| D3 | agent | PASS | 2/2 | 0.37 |
| D4 | agent | PASS | 4/4 | 0.56 |
| D5 | agent | PASS | 7/7 | 0.72 |
| D6 | agent | PASS | 14/14 | 1.83 |
| D7 | agent | PASS | 9/9 | 1.17 |
| D8 | agent | PASS | 7/7 | 0.47 |
| D9 | agent | PASS | 10/10 | 0.97 |
| D10 | agent | PASS | 3/3 | 0.55 |
| D11 | agent | PASS | 11/11 | 3.76 |
| E1 | measure | PASS | 12/12 | 2.17 |
| E2 | measure | PASS | 2/2 | 4.61 |
| U1 | unit | PASS | 2/2 | 0.05 |
| R1 | regress | PASS | 3/3 | 94.07 |
| R2 | regress | PASS | 8/8 | 1.87 |
| M-truncate-key | mutation | PASS | 2/2 | 1.67 |
| M-split-transaction | mutation | PASS | 2/2 | 10.06 |
| M-no-replay-lookup | mutation | PASS | 2/2 | 1.68 |
| M-ignore-mismatch | mutation | PASS | 2/2 | 1.47 |
| M-commit-order | mutation | PASS | 2/2 | 10.68 |
| M-grant-no-authority | mutation | PASS | 2/2 | 1.28 |
| M-grant-no-version | mutation | PASS | 2/2 | 1.98 |
| M-grant-no-completion | mutation | PASS | 2/2 | 1.68 |

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
- `agent/controller.py`: `9f736d9756c3acb5453bdac4835339fe4fb01c9ac7ca659bdbe0aefec5ac0cb6`
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

## Final follow-up validation

After the full run, a small controller recovery fix was committed at
`4a2b7a3`: panic/timeout now marks the bridge for restart. The focused
S-controller-recovery regression passed at that clean revision (1 case,
16 checks, 3.5 seconds), without manually setting the restart flag.
All hashed kernel sources are identical to the full-run revision.

The full suite was not repeated after this isolated host fix; its targeted
regression and all 30 host unit tests passed. The final demo additionally
refuses to present a production build as a crash experiment.

`make production` succeeded and its binary contained no injection strings.
Production kernel SHA-256: `4c7013d82b5a23c3d4d16240c8ec4570e6261610eecf7a47e8ab955597c2f117`.
Remote CI and fresh package installation were not performed.

All four demo modes (none/pre/post/lost) passed with a fresh dedicated image
each. Source packaging was verified as a valid ZIP with licenses and fixtures.
