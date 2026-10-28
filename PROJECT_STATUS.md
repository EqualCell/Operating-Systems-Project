# OS Project 4: exactly-once file effects in xv6

## Progress checkpoint

- Chosen base: MIT xv6-riscv, pinned to commit `e93dabeb98431235c6e1a101cb96c73c923fdbc4` on its `riscv` branch.
- Goal: add `effect(key, op, path, buf, n)` for APPEND and CREATE. Save the file change and completed key/result in one xv6 file-system log transaction.
- Planned tests: replay after each injected crash point using the same `fs.img`; simultaneous requests with one key; mismatched retry; full key table.
- Current state: repository bootstrap and baseline build; Project 4 implementation is pending.

## Local setup (Ubuntu/Debian)

```sh
sudo apt update
sudo apt install -y git make gcc-riscv64-unknown-elf binutils-riscv64-unknown-elf qemu-system-misc bc
git clone https://github.com/EqualCell/Operating-Systems-Project.git
cd Operating-Systems-Project
make qemu
```

In the xv6 shell, try `ls` and `echo hello`. Exit QEMU with Ctrl-A then X. The source runs **inside** QEMU as a RISC-V guest; QEMU is a host program and is not committed to Git.

## Relevant code map

- `kernel/syscall.c`, `kernel/syscall.h`: syscall dispatch and numbers.
- `user/usys.pl`, `user/user.h`: user-facing syscall stub and declaration.
- `kernel/sysfile.c`, `kernel/fs.c`: file operations and disk blocks.
- `kernel/log.c`: crash-recoverable log transactions.
- `kernel/fs.h`, `mkfs/mkfs.c`: on-disk layout and file-system image creation.

The existing `make clean` removes `fs.img`. Do **not** run it between crash and retry when testing persistence. Do not commit `fs.img`, build outputs, or the course PDF.
