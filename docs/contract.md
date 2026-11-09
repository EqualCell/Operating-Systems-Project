# Effect protocol contract

The effect ABI uses fixed-width, 688/168/32-byte request and response structures
from [`kernel/effect.h`](../kernel/effect.h). Base effects are keyed by a 64-bit
client key; checked effects are keyed by `(grant_id, req_id)`. A matching retry
returns the recorded result without executing the file operation, while a hash
mismatch is rejected.

Controllers create and revoke grants. A grant transitions from active to either
consumed or revoked, and agents cannot acquire controller privileges or mutate
files through ordinary writes.
