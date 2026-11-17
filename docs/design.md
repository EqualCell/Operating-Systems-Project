# Durable at-most-once effects and single-use approvals

## Boundary and authority

Stock xv6 has no users. This project adds a per-process controller bit. Only
boot's initial process receives it; fork inherits it, exec preserves it, exit
loses it. `controller_drop()` is irreversible and inherited by descendants.
The host console, init and administrative shell are trusted. The bridge's
agent entry point drops authority before handling input; the planner never
issues approvals. Executing a controller binary does not confer authority.
Untrusted processes cannot kill controller processes. Privileged host access,
modified kernels/images, physical disk tampering, and denial of service are
outside the boundary. This is one controller domain and one agent domain;
all agents may query retained results. There are no per-agent tenants.

Untrusted ordinary file mutations are refused globally, including writes
through descriptors opened before dropping authority. Pipe and console output
remain available. Controller code is deliberately small (grantctl); it does
not run a planner. Host approval dispatch is an explicit separate API.

## Identity and versions

Protected regular inodes are pinned permanently: link/unlink is refused even
for controllers. Thus device/inode identity cannot be reused, replaced or
aliased after protection. Existing hard links prevent first protection.
APPEND issuance pins a single-link regular inode and captures its persistent
version. Ordinary controller writes/truncations increment that version in
the same filesystem transaction. The inode lock serializes approval against
writes and excludes pre-opened-descriptor bypasses. Refuse version overflow.

CREATE supports canonical names directly in root (1..14 characters; no dot or
dot-dot). It binds the root inode/version and destination name/nonexistence,
not a fictional target inode. Root directory mutations advance its protected
version, so even unrelated namespace changes conservatively stale CREATE.
CREATE locks root through the nonexistence test and link insertion. A created
file is pinned before releasing its inode. No unpin or garbage collection.

## Requests, grants, replay and revoke

Grant IDs and request IDs are independent nonzero uint64 namespaces. A grant
ID is also its issuance idempotency key: identical reissuance returns the
retained approval, with its original expected version/state; changed binding
is a mismatch. Bindings store exact operation/path/length/payload bytes, not
FNV or a cryptographic hash. Requests are global within the one domain;
reusing a completed request ID with another grant is a mismatch.

Each retained grant can have at most one completion. A successful effect
atomically checks ACTIVE, identity/version and exact binding, changes file,
consumes grant, increments version and stores request ID/return value. A
matching completion is checked first and replays before ACTIVE/version tests,
even after revoke. Changed arguments cannot obtain the old result. Changing
request ID after consumption is denied. Negative failures do not consume a
grant; a recorded nonnegative short count consumes it. CREATE may create an
empty file on allocation exhaustion and records zero; APPEND zero progress
returns EIO without completion, with any unused indirect allocation undone.
There is no implicit transaction rollback in xv6.

A single sleep lock serializes issue/effect/revoke/status, before begin_op.
For effect versus revoke, the lock winner commits and synchronizes before
releasing the lock. Revoke on a consumed grant reports CONSUMED (cannot undo);
repeated revoke is idempotent. A completed request remains replayable. Clicking
revoke on the host does not itself cancel an in-flight effect.

Lock order: security sleep lock -> begin_op -> inode -> object-version buffer
or grant buffer. Ordinary FS paths never acquire the security lock. No spinlock
is held across sleeping I/O. Result classification is per-process, never
inferred from global counters. end_op plus sync waits for overlapping/group
transactions before any durable success is returned.

## Storage, budget, recovery

Format v1 extends the superblock with security-region start/count. A header
block holds magic/version/capacities, followed by 32 one-block grant records
and two blocks of uint64 object versions (256 inode slots).
The on-disk grant record is 320 bytes in its dedicated 1024-byte block;
request ABI is 296 bytes. Superblock remains little endian, inode size 64 bytes. Zero version means
unprotected; first protection sets one. Empty grants are all-zero. No eviction.
Invalid geometry/header/record/state fails closed (kernel panic at recovery or
read); unsupported images must be rebuilt explicitly. This is a format change,
not an in-place migration. mkfs reserves and bitmap-marks the entire region.

One grant record contains both issuance binding and completion: no separate
completion slot is allocated during effect. A transaction touches at most 10
blocks on the supported 2000-block filesystem (one bitmap): two data blocks,
indirect, bitmap, target inode, parent directory data/inode for CREATE, up to
two version blocks, and grant. APPEND needs at most seven. The 256-byte bound
excludes large writes. Creation cleanup uses the same reservation. Ordinary
writes reserve a version block in their chunk budget. Larger disk geometry is
unsupported without revisiting bitmap/log bounds. No nested transactions.

Assume QEMU synchronous sector writes are ordered and survive a simulated
process crash. The xv6 redo-log header is the commit point: before header,
neither effect nor consumption; after header, recovery installs both. Hardware
power loss, write-cache reordering, torn sectors and malicious disk corruption
are outside these assumptions. Same-image reboot is required. Crash hooks
exist only in explicit test builds and require controller authority.

Worst-case reservation for the fixed FSSIZE=2000 image: APPEND touches at most
2 data + indirect + bitmap + inode + object-version + grant = 7 distinct blocks.
CREATE touches file data + file inode + directory data + directory inode +
indirect + bitmap + up to 2 version-table blocks + grant = at most 9. The
10-block per-operation reservation covers these; the 30-block log/cache admits
three reservations. Ordinary controller mutations add at most one version
block to stock write budgets. Capacity is checked before file mutation.
Geometry is deliberately fixed/bounded; increasing FSSIZE or inode capacity
requires revisiting bitmap and reservation bounds.

## Host recovery and scope

The host fsyncs complete logical request/grant/arguments before dispatch.
Attempt IDs are separate from request IDs. Missing replies mean UNKNOWN;
restart queries status or retries exactly the same request, never generates
another identity for pending work. A JSONL journal truncates and fsyncs only
an unterminated final record, rejects complete/middle corruption and bad
references, and locks each reload/append. Unique instance/boot logs persist.
Resets use explicit experiment copies. Deterministic planning is sufficient;
allowlisting assists transport but kernel checks enforce authorization.

The old effect ABI is controller-only in secure builds, retained as a clearly
identified deduplication comparison. Ordinary append retries and a deliberately
separate permission check are experimental only, never an agent path. Scope
excludes unrestricted exactly-once execution, distributed consensus, arbitrary
file sizes/paths, unbounded retention and safe garbage collection. Eventual
completion needs retained identities, intact storage, available capacity,
a valid unconsumed grant, and retries after recovery.


## ABI and results

Syscalls 28..32 are controller_drop(), grant_issue(&request),
grant_effect(&request), grant_revoke(uint64) and grant_status(grant, request,
&status). The caller supplies a fixed 296-byte request with no user pointers;
copyin validates the complete structure before use. The per-process
`effect_result()` syscall returns 1 for execution, 2 for replay, 0 for error.
Status is read-only and reports retained request, state, saved result, expected
and current versions; request zero queries the grant alone. An ACTIVE grant
with no completion is pending, not a promise of cancellation or success.

| Result | Meaning |
|---|---|
| >=0 | Saved byte count (effect); 0 success for issue/revoke/status |
| -1 | Invalid argument/pointer/operation/path |
| -2 | APPEND target absent |
| -3 | Retention capacity exhausted |
| -4 | Changed binding or completed request ID used with another grant |
| -5 | Zero-progress APPEND or unavailable allocation |
| -6 | CREATE destination exists |
| -7 | Caller lacks controller authority, or production crash hook |
| -20 | Grant not found |
| -21 | Grant revoked |
| -22 | Object/version stale |
| -23 | Grant consumed; new request cannot execute, revoke cannot undo |
| -24 | Status result placeholder: no completion yet |

Unsupported geometry/format or invalid recovered records cause a diagnostic
boot panic rather than enabling an empty authorization table. No arbitrary
malicious bit-flip detection is claimed; storage tampering is outside scope.
