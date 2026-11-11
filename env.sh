# env.sh -- source this once per shell:  source env.sh
# Points PATH at the RISC-V cross compiler + QEMU if they were unpacked into
# ~/toolchain/root (no-root install used on the dev machine). On a normal
# machine with `apt install gcc-riscv64-linux-gnu qemu-system-misc/riscv` this
# file is unnecessary.
TC="${XV6_TOOLCHAIN:-$HOME/toolchain/root}"
if [ -d "$TC/usr/bin" ]; then
  export PATH="$TC/usr/bin:$PATH"
  export LD_LIBRARY_PATH="$TC/usr/lib/x86_64-linux-gnu:$TC/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}"
fi
export TOOLPREFIX=riscv64-linux-gnu-
