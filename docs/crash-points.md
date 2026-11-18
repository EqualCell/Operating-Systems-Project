# Crash points

Use `make test-build`. Default/production builds compile out injection and
return -7 from crashat/crashhook. Only controllers can arm test hooks.

| Stage | Location in kernel/log.c | After reboot |
|---|---|---|
| 1 | log data written, before header | uncommitted changes discarded |
| 2 | commit header durable | entire transaction replayed |
| 3 | after the nth home-block installation | remaining installation replayed |
| 4 | installation finished, header not cleared | idempotent installation replayed |

`crashat(n)` panics during the nth log_write staging call. `crashhook(3,n)`
selects the nth installation block; `crashctl stage 3 n` exposes it. Hooks are
not active during boot recovery. The harness SIGKILLs panicked QEMU and reboots
the SAME experiment image. Independent trials get separate copies. Offline
verification distinguishes raw home/log blocks from a copy with replay applied.
See [testing](testing.md) and [demo](demo.md).
