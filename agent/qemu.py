"""agent/qemu.py -- run xv6 inside QEMU and talk to its serial console.

This is the lowest layer of the host->guest bridge. It knows how to
  * find qemu-system-riscv64 (also from a no-root toolchain in ~/toolchain/root),
  * boot xv6 on a disk image that WE are given (never recreated here),
  * type a line at the xv6 shell and collect the output,
  * detect a kernel panic or a hang, and
  * cut the power abruptly (SIGKILL), which is how crashes are simulated.

It contains no policy: allowlists and framing live in agent/bridge.py.
Raw serial output is always copied to a log file (evidence).
"""
import os
import re
import shutil
import subprocess
import threading
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def setup_env():
    """Return an environment dict in which qemu-system-riscv64 can be run."""
    env = dict(os.environ)
    tc = os.environ.get("XV6_TOOLCHAIN", os.path.expanduser("~/toolchain/root"))
    if os.path.isdir(os.path.join(tc, "usr", "bin")):
        env["PATH"] = os.path.join(tc, "usr", "bin") + os.pathsep + env.get("PATH", "")
        libs = [os.path.join(tc, "usr/lib/x86_64-linux-gnu"), os.path.join(tc, "lib/x86_64-linux-gnu")]
        env["LD_LIBRARY_PATH"] = os.pathsep.join(libs + [env.get("LD_LIBRARY_PATH", "")])
    return env


def qemu_path(env=None):
    env = env or setup_env()
    p = shutil.which("qemu-system-riscv64", path=env.get("PATH"))
    if not p:
        raise RuntimeError("qemu-system-riscv64 not found (see docs/setup.md)")
    return p


PROMPT = "\n$ "


class VMError(Exception):
    pass


class VM:
    def __init__(self, img, kernel=None, cpus=1, log_path=None, mem="128M", tag=""):
        self.img = os.path.abspath(img)
        self.kernel = kernel or os.path.join(REPO, "kernel", "kernel")
        self.cpus = cpus
        self.mem = mem
        self.log_path = log_path
        self.tag = tag
        self.proc = None
        self.buf = ""
        self.lock = threading.Lock()
        self.cmdline = None
        self.boot_seconds = None
        self.panicked = False
        self.last_rx = time.time()

    # ---- lifecycle -------------------------------------------------------
    def command_line(self):
        q = qemu_path()
        return [
            q, "-machine", "virt", "-bios", "none", "-kernel", self.kernel,
            "-m", self.mem, "-smp", str(self.cpus), "-nographic",
            "-global", "virtio-mmio.force-legacy=false",
            "-drive", f"file={self.img},if=none,format=raw,id=x0",
            "-device", "virtio-blk-device,drive=x0,bus=virtio-mmio-bus.0",
        ]

    def boot(self, timeout=60):
        self.cmdline = self.command_line()
        t0 = time.time()
        self.proc = subprocess.Popen(
            self.cmdline, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, env=setup_env(), bufsize=0)
        self._logf = open(self.log_path, "w") if self.log_path else None
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        if not self.wait_prompt(0, timeout):
            self.kill()
            raise VMError("xv6 did not reach the shell prompt:\n" + self.buf[-500:])
        self.boot_seconds = round(time.time() - t0, 3)
        return self

    def _read_loop(self):
        while True:
            b = self.proc.stdout.read(1)
            if not b:
                break
            s = b.decode("latin-1").replace("\r", "")
            with self.lock:
                self.buf += s
                self.last_rx = time.time()
                if "panic:" in self.buf and not self.panicked:
                    self.panicked = True
            if self._logf:
                self._logf.write(s)
                self._logf.flush()

    def kill(self):
        """Abrupt power cut."""
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait()
        if getattr(self, "_logf", None) and not self._logf.closed:
            time.sleep(0.05)
            self._logf.close()

    # ---- interaction -----------------------------------------------------
    def snapshot(self):
        with self.lock:
            return self.buf

    def wait_for(self, text, start, timeout):
        """Wait until `text` appears in buf[start:]; abort early on panic."""
        end = time.time() + timeout
        while time.time() < end:
            with self.lock:
                if text in self.buf[start:]:
                    return True
                if self.panicked:
                    return False
            if self.proc.poll() is not None:
                return False
            time.sleep(0.01)
        return False

    def wait_prompt(self, start, timeout):
        """The xv6 shell prompt is "$ ". Output that does not end in a newline
        puts the prompt mid-line, so we accept "$ " at the very end of the
        stream provided the guest has been quiet for 40 ms."""
        end = time.time() + timeout
        while time.time() < end:
            with self.lock:
                tail = self.buf[start:]
                quiet = time.time() - self.last_rx
                if tail.endswith("$ ") and quiet > 0.04:
                    return True
                if self.panicked:
                    return False
            if self.proc.poll() is not None:
                return False
            time.sleep(0.01)
        return False

    def run(self, cmd, timeout=30):
        """Type `cmd` at the shell. Returns (output, status)
        status: 'ok' (prompt came back), 'panic' (kernel panicked), 'timeout'."""
        with self.lock:
            start = len(self.buf)
        self.proc.stdin.write((cmd + "\n").encode())
        self.proc.stdin.flush()
        ok = self.wait_prompt(start + len(cmd) + 1, timeout)
        with self.lock:
            out = self.buf[start:]
        # strip the echoed command line and the trailing prompt
        out = out[len(cmd) + 1:] if out.startswith(cmd) else out
        if out.endswith("$ "):
            out = out[:-2]
        status = "ok" if ok else ("panic" if self.panicked else "timeout")
        return out, status

    def wait_panic(self, timeout=10):
        return self.wait_for("panic:", 0, timeout)

    # context manager ------------------------------------------------------
    def __enter__(self):
        return self.boot()

    def __exit__(self, *a):
        self.kill()


def parse_kv(line):
    """'EFFECT op=APPEND key=0x1 rc=5' -> {'op': 'APPEND', 'key': '0x1', 'rc': '5'}"""
    return dict(re.findall(r"(\w+)=(\S+)", line))


def find_line(output, prefix):
    for ln in output.splitlines():
        if ln.startswith(prefix):
            return ln
    return None
