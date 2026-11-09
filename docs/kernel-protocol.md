# Kernel protocol implementation

Effect requests reserve a filesystem transaction, acquire `effect_gate_lock`,
perform inode work, release the gate, and finish with
`log_end_op_and_wait()`. This is the lock hierarchy:

`log.lock` (through `begin_op`) -> `effect_gate_lock` -> inode locks.

The xv6 log has 30 blocks. Effect payloads are bounded to 512 bytes, so the
operation remains within the existing `MAXOPBLOCKS` reservation together with
inode, bitmap, indirect, and metadata blocks. Commit crash hooks cover log
registration, the commit header, installation, and grant consumption.
