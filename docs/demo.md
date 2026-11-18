# Demonstration

All commands in this first block run in an **Ubuntu host terminal**:

```sh
make test-build
python3 demo.py --crash none
python3 demo.py --crash pre
python3 demo.py --crash post
python3 demo.py --crash lost
```

Each invocation makes a new `runs/demo-*` directory, containing one image,
separate controller/agent journals, and unique per-instance/boot serial logs.
An explicit `--workdir` must name a nonexistent directory: existing data is
never reset. The trusted controller issues an exact approval; the agent uses
it. Missing replies trigger same-ID retry. Expected results:

| Experiment | First reply | Recovery retry | Extra identical retry |
|---|---|---|---|
| none | EXECUTED | unnecessary | REPLAYED |
| pre | UNKNOWN | EXECUTED | REPLAYED |
| post | UNKNOWN | REPLAYED | REPLAYED |
| lost | UNKNOWN | REPLAYED | REPLAYED |

The offline check runs only after QEMU stops and requires
`b'boot-entry-0\nauthorized'` and exactly one consumed grant/completion.
Revoke after completion returns `-23`: it cannot undo committed work; the
completion remains queryable. Run all four experiments for the complete short
demo (authorized success, replay, before-commit crash, after-commit crash).

For a manual **xv6 shell** demo, boot a dedicated copy from Ubuntu:

```sh
mkdir -p runs/manual
cp -n fs.img runs/manual/disk.img
python3 -m agent --img runs/manual/disk.img "list"
```

For interactive QEMU use this host command (same image on every reboot):

```sh
qemu-system-riscv64 -machine virt -bios none -kernel kernel/kernel -m 128M -smp 3 -nographic -global virtio-mmio.force-legacy=false -drive file=runs/manual/disk.img,if=none,format=raw,id=x0 -device virtio-blk-device,drive=x0,bus=virtio-mmio-bus.0
```

Then type **inside xv6** (IDs in grantctl are hexadecimal):

```text
grantctl issue 1 0 append /log.txt hello
grantctl drop effect 1 9 append /log.txt hello
grantctl drop effect 1 9 append /log.txt hello
grantctl revoke 1
grantctl status 1 9
cat /log.txt
grantctl drop issue 2 0 append /log.txt BAD
```

Expect issue `rc=0`, effect `rc=5 outcome=EXECUTED`, retry `rc=5
outcome=REPLAYED`, revoke `rc=-23`, state `3` and one `hello` in the file.
The unprivileged issue attempt returns `-7`. Executing grantctl after dropping
authority does not grant privilege. Use Ctrl-A then X to exit QEMU.

For crash experimentation in xv6, issue a fresh grant, then:

```text
grantctl issue 2 0 append /log.txt post
grantctl -s 2 effect 2 a append /log.txt post
```

The kernel panics after the log commit header. Exit QEMU and reboot using the
same host command/image, then `grantctl drop effect 2 a append /log.txt post`:
expect saved-result `REPLAYED`. Substitute stage 1 for before-commit execution
on retry; stages 3/4 cover partial installation / before header clearing.
Never copy a fresh image over this experiment between crash and retry.

The host agent CLI takes a previously issued grant via `--grant 0xID` for a new
effect. `--resume` reloads pending grant/request/arguments from its journal.
Controller approval and revocation APIs live in `agent/controller.py`; the
planner and Agent cannot call them. `bridge.call('effect_status', {}, key=R,
grant_id=G)` performs the read-only recovery query.

For isolated comparisons, run `./run_tests.sh --group comparison`.
The test builds a scratch tree with `UNSAFE_COMPARISONS=1`: ordinary retries
produce `XX`, legacy dedup produces `X`, separated permission checking writes
`X` after revoke, and the integrated grant path produces `X` with one completion.
The normal `compare` binary reports disabled, and normal agent entry points
always drop controller authority.
