#!/usr/bin/env python3
"""GDB inspection of the commit point while effect() runs.

Starts QEMU frozen (-S) with the gdb stub, attaches gdb-multiarch, sets
    break write_head if log.lh.n > 0
(i.e. the moment xv6 is about to make a transaction durable), then types one
`effectctl append` at the xv6 console. At the breakpoint gdb prints the call
chain and the block numbers in the transaction next to sb.effstart, which shows
the file blocks AND the effect-table block are committed together.

This is an INSPECTION session of the mechanism. It is not the "real bug found
and fixed" GDB log the course requires: that must come from a real bug you hit.

usage: python3 tests/gdb/inspect_commit.py [outfile]
"""
import os
import shutil
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from agent.qemu import REPO, qemu_path, setup_env  # noqa: E402

PORT = 26000 + os.getuid() % 4000 + 7
out_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "evidence", "gdb-commit-inspection.txt")
os.makedirs(os.path.dirname(out_path), exist_ok=True)
env = setup_env()
gdb = shutil.which("gdb-multiarch", path=env["PATH"]) or shutil.which("riscv64-unknown-elf-gdb", path=env["PATH"])
if not gdb:
    sys.exit("no gdb-multiarch / riscv64-unknown-elf-gdb found")

img = "/tmp/gdb-inspect.img"
shutil.copy(os.path.join(REPO, "fs.img"), img)
kernel = os.path.join(REPO, "kernel", "kernel")

q = subprocess.Popen([qemu_path(env), "-machine", "virt", "-bios", "none", "-kernel", kernel, "-m", "128M", "-smp", "1",
                      "-nographic", "-global", "virtio-mmio.force-legacy=false",
                      "-drive", f"file={img},if=none,format=raw,id=x0", "-device", "virtio-blk-device,drive=x0,bus=virtio-mmio-bus.0",
                      "-S", "-gdb", f"tcp::{PORT}"],
                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, bufsize=0)
console = []
threading.Thread(target=lambda: [console.append(c) for c in iter(lambda: q.stdout.read(1), b"")], daemon=True).start()

cmds = f"""
set pagination off
set confirm off
set print pretty off
file {kernel}
target remote :{PORT}
break sys_effect
continue
echo \\n===== stopped in sys_effect() (the effect syscall has just been entered) =====\\n
delete 1
break write_head if log.lh.n > 0
continue
echo \\n===== stopped at the COMMIT POINT: write_head() with a non-empty log =====\\n
bt 6
echo \\n--- number of blocks in this transaction:\\n
print log.lh.n
echo --- their home block numbers (log.lh.block[0..n-1]):\\n
print/d *log.lh.block@log.lh.n
echo --- first block of the effect table (sb.effstart) and its size (sb.effblocks):\\n
print sb.effstart
print sb.effblocks
echo --- does the transaction contain the table block?  (1 = yes)\\n
print log.lh.block[0] == sb.effstart || log.lh.block[1] == sb.effstart || log.lh.block[2] == sb.effstart || log.lh.block[3] == sb.effstart
echo --- we are inside sys_effect(): its frame\\n
frame 3
info frame
kill
quit
"""
cf = "/tmp/gdb-inspect.cmds"
open(cf, "w").write(cmds)
g = subprocess.Popen([gdb, "-batch", "-nx", "-x", cf, "--data-directory=" + os.path.join(os.path.expanduser("~/toolchain/root"), "usr/share/gdb")],
                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, text=True)

# wait for the shell prompt, then trigger one effect
t0 = time.time()
while b"$ " not in b"".join(console)[-4:] and time.time() - t0 < 60:
    time.sleep(0.1)
try:
    q.stdin.write(b"effectctl append 0x1234 /log.txt gdb-demo\n")
    q.stdin.flush()
except BrokenPipeError:
    g.kill()
    print("QEMU exited early. gdb said:\n" + g.communicate()[0] + "\nconsole:\n" + b"".join(console).decode("latin-1"))
    sys.exit(1)
gout, _ = g.communicate(timeout=90)
q.kill()
q.wait()
noise = ("Python Exception", "Could not load the Python gdb module", "Limited Python support", "Suggest passing --data-directory", "gdb-multiarch: warning:")
import re
gout = "\n".join(re.sub(r"Python Exception <class '\w+'>: [^\n]*", "", l) for l in gout.splitlines() if not l.startswith(noise) and l.strip() != "warning:")
gout = "\n".join(l for l in gout.splitlines() if l.strip() not in ("", ))
transcript = ("# GDB inspection of effect()'s commit point  (tests/gdb/inspect_commit.py)\n"
              "# (harmless 'Python Exception ... gdb._execute_unwinders' lines from the no-root gdb install were filtered out)\n"
              f"# gdb: {gdb}\n# kernel: {kernel}\n\n" + gout +
              "\n# ---- xv6 console as seen meanwhile ----\n" + b"".join(console).decode("latin-1").replace("\r", ""))
open(out_path, "w").write(transcript)
print(transcript)
