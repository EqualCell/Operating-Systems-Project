# Ubuntu setup

Run these in an **Ubuntu host terminal**, not the xv6 shell.

```sh
sudo apt-get update
sudo apt-get install -y build-essential gcc-riscv64-linux-gnu binutils-riscv64-linux-gnu python3 bc
```

On Ubuntu 24.04, install `qemu-system-misc`; on Ubuntu 26.04, install
`qemu-system-riscv`. Package contents differ by release:
[Ubuntu 24.04 package](https://packages.ubuntu.com/noble/qemu-system-misc),
[Ubuntu 26.04 package](https://packages.ubuntu.com/resolute/qemu-system-riscv).

```sh
# Ubuntu 26.04:
sudo apt-get install -y qemu-system-riscv
# Ubuntu 24.04: use sudo apt-get install -y qemu-system-misc instead.
command -v qemu-system-riscv64
qemu-system-riscv64 --version
command -v riscv64-linux-gnu-gcc
riscv64-linux-gnu-gcc --version
make test-build
./run_tests.sh --slow
```

Fresh local validation used Ubuntu 26.04.1, `/usr/bin/qemu-system-riscv64`
owned by `qemu-system-riscv` (verified with dpkg-query), QEMU 10.2.1, RISC-V GCC
15.2.0 and Python 3.14.4. QEMU must be at least 7.2. The Ubuntu 24.04 package
selection is checked against Ubuntu's catalogue; installation on a new 24.04
machine was not performed here. CI is configured for that release.

`env.sh` and the Python QEMU launcher also recognize an existing unpacked
`$XV6_TOOLCHAIN/usr/bin` (default `~/toolchain/root`). No network, LLM API,
third-party Python packages or root privilege is needed to run the tests once
the toolchain is installed.

`make production` builds without hooks; `make test-build` enables them.
`make clean` removes the source `fs.img`; never clean/rebuild an experiment
image between crash and retry. Format v1 is new: old images are refused;
rebuild a pristine image explicitly and preserve old experiment artifacts.
