# Crash-safe authorized file effects in xv6

An xv6 RISC-V kernel experiment with durable at-most-once file effects per
retained request identity and single-use, revocable grants. A Python/QEMU
bridge journals requests before dispatch and retries the same grant, request
ID and exact arguments after a lost reply or crash. The planner is deterministic;
no external LLM is required or integrated.

The kernel atomically validates approval and file version, appends or creates,
consumes the grant and saves its result in one redo-log transaction. Completed
identical requests replay their saved result even after a revoke attempt.
Changing arguments is rejected. This is bounded retained-request deduplication,
not unrestricted exactly-once execution.

```text
Trusted host controller -> grant_issue / revoke
Untrusted planner -> validator -> fsynced journal -> QEMU agentcall
                                                    | drops authority
                                                    v
                      kernel grant_effect -> file + version + completion
                                           one xv6 log transaction
```

Features include exact byte bindings (256-byte kernel payloads), 64-bit IDs,
persistent versions, permanent inode pinning, protection against ordinary
syscall/descriptor bypasses, status queries, crash injection in explicit test
builds, and an independent disk-image verifier. CREATE supports names directly
in root; there are 32 retained grants/completions and no eviction.

On an installed toolchain:

```sh
make test-build
./run_tests.sh --slow
python3 demo.py --crash pre
python3 demo.py --crash post
make production
```

See [setup](docs/setup.md) for Ubuntu packages and executable verification,
[demo](docs/demo.md) for exact host/guest commands, [design](docs/design.md) for
the authority/locking/storage contract, and [results](evidence/summary.md) for
fresh validation and measured limits. Default builds disable crash hooks;
configuration changes rebuild affected objects. Tests copy images into dedicated
experiment directories and reboot the same copy after a crash.

The administrative console, init, controller descendants and privileged host
access are trusted. `controller_drop()` is irreversible; fork/exec cannot regain
authority. All agents share one result domain. Untrusted ordinary file mutations
are denied globally; legitimate controller writes advance protected versions.
Protected files cannot be linked/unlinked even by controllers. No garbage
collection, physical-power-loss guarantee, disk-tampering resistance or
exhaustive concurrency proof is claimed. See [design limitations](docs/design.md).

MIT xv6 licensing and contributor acknowledgments are preserved in [LICENSE](LICENSE)
and the original upstream [README](README). Existing contributor history is retained.
