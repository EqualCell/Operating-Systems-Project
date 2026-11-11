# Setup

## Normal machine
```sh
sudo apt install gcc-riscv64-linux-gnu qemu-system-misc qemu-system-riscv python3 make   # or the riscv64-unknown-elf toolchain
git clone <this repo> && cd xv6-riscv
./run_tests.sh            # builds, runs the whole suite, writes evidence/<time>/
python3 demo.py           # narrated end-to-end demo
make qemu                 # interactive xv6 (try: effectctl append 1 /log.txt hi)
```
## Without root (how the evidence in this repo was produced)
`apt` needs root, so the `.deb` packages were downloaded and unpacked into `~/toolchain/root` (no install):
`gcc-riscv64-linux-gnu`, `binutils-riscv64-linux-gnu`, `libc6-dev-riscv64-cross`, `qemu-system-riscv`,
`qemu-system-misc` and their dependencies, plus `gdb-multiarch` for the GDB script. `env.sh` puts that
directory on `PATH`/`LD_LIBRARY_PATH` and sets `TOOLPREFIX=riscv64-linux-gnu-`; `agent/qemu.py` does the
same for QEMU automatically. Set `XV6_TOOLCHAIN=/other/prefix` to move it.

## Versions used for the recorded run
Recorded automatically in `evidence/final/results.json → environment` (QEMU 10.2.1, riscv64 GCC 15.2.0,
Python 3.14, xv6-riscv base commit, sha256 of kernel/fs.img/sources).

## Useful commands
| | |
|---|---|
| full suite | `./run_tests.sh` (add `--slow` for `usertests -q`) |
| selected cases | `./run_tests.sh --only B2 C1` / `--group crash` / `--list` |
| one-case crash walkthrough | `docs/crash-points.md` |
| production kernel | `make clean && make TESTHOOKS=0 qemu` |
| 3 CPUs / 1 CPU | `make CPUS=3 qemu` / `make CPUS=1 qemu` |
| GDB (inspection transcript) | `python3 tests/gdb/inspect_commit.py` |
| interactive GDB | `make qemu-gdb`, then `gdb-multiarch kernel/kernel` → `target remote :26000` (port printed by make) |
| submission zip | `tools/make_zip.sh Team_Name_4` |
