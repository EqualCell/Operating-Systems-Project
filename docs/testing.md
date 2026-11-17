# Reproducible tests and evidence

```sh
./run_tests.sh                 # all normal cases, including crash and mutation tests
./run_tests.sh --slow          # also stock xv6 usertests -q, CPUS=3
./run_tests.sh --group security security-crash
./run_tests.sh --group agent
./run_tests.sh --group mutation comparison
python3 -m unittest discover -s tests/unit -v
make production
```

Generate a compact report with `python3 tools/summarize.py evidence/run-ID evidence/summary.md`.

The runner writes ignored `evidence/run-*/results.json`, a readable report,
serial logs, command/output traces, checks and lossless image block differences.
It records source revision, dirty count, source/kernel/image hashes, compiler,
QEMU, Python, CPU configuration and timings. Source `fs.img` is a fixture;
QEMU experiments use copies. Offline assertions run with QEMU stopped.
Results compare raw crash state, independent replay, and actual reboot state.
Tests never recreate an experiment image between crash and retry.

Core groups cover baseline ABI, 64-bit keys, bad user memory, exact bindings,
same/different-key concurrency, shared-grant races, effect/revoke races,
controller authority, fork/exec, descriptor and ordinary syscall bypasses,
stale versions, pinned identities, hard links, CREATE races, capacity,
disk-full/short-write paths, four crash stages for issue/effect/revoke,
controller/agent host restart, lost replies, journal corruption/torn-tail repair,
unsupported formats, production builds and upstream regression behavior.
The manual cat investigation runs BASE/pre/post crashes on CPUS=3 followed by
30 cat invocations and compares executable bytes and allocation metadata.

The mutation harness builds scratch copies and requires selected existing
tests to fail. Mutants omit authority/version/completion checks, truncate keys,
ignore replay/mismatch, split transactions or reverse commit ordering. A
mutation case passes only if its broken build is detected. Assertions are
never relaxed to make a mutant pass. `UNSAFE_COMPARISONS=1` is enabled only in
the isolated comparison tree; normal agentcall always drops authority.

Restore a generated image for independent inspection:

```sh
python3 tools/restore_image.py evidence/run-ID/pristine-fs.img.gz evidence/run-ID/CASE/disk.final.blockdiff.gz runs/restored.img
python3 -c "from tests.lib.fsimage import Image; f=Image.load('runs/restored.img'); print(f.grants()); print(f.versions()); print(f.check_consistency())"
```

Use actual generated paths (some cases use another image name). Do not open a
running VM's image as if it were a stable disk snapshot. `with_log_replayed()`
returns a separate in-memory view; it does not mutate raw evidence.

A source archive is `tools/make_zip.sh Project` -> `runs/Project.zip`. It includes
committed source/license/fixtures/tests and compact evidence, and excludes
.git and build outputs. Commit intended source before packaging. Debugger tools
are retained but this repair does not claim a new GDB debugging session.

Limits: finite tests do not prove every schedule; real host power loss/torn
sectors/reordered device writes and crashes during boot recovery are untested.
No unsupported hardware durability claim is made. Results apply to the source
revision and environment in the evidence summary; CI configuration itself is
not a claim that a remote CI run was performed.
