// effect.h -- the ONE shared contract for the exactly-once "effect" feature.
//
// Included by the kernel (effect*.c, log.c, mkfs) AND by user programs
// (user/effectctl.c ...), so it may only use types from kernel/types.h.
//
// Read docs/contract.md for the prose version of this file.

#ifndef EFFECT_H
#define EFFECT_H

// ---------------------------------------------------------------------------
// 1. Operations   effect(key, op, path, buf, n)
// ---------------------------------------------------------------------------
#define EFF_APPEND 1 // append n bytes of buf to an EXISTING regular file
#define EFF_CREATE 2 // create a NEW regular file holding n bytes of buf

// ---------------------------------------------------------------------------
// 2. Result codes.
//    A non-negative return value is a SUCCESS result (bytes written).
//    A negative return value is an ERROR and is NEVER stored in the table:
//    nothing durable happened, so a retry is always safe.
// ---------------------------------------------------------------------------
#define EFF_EINVAL    (-1) // bad op / key==0 / bad length / bad path / not a file
#define EFF_ENOENT    (-2) // APPEND target does not exist
#define EFF_EFULL     (-3) // effect table is full (checked BEFORE touching file)
#define EFF_EMISMATCH (-4) // key already used for a DIFFERENT request
#define EFF_EIO       (-5) // could not write anything (e.g. disk full)
#define EFF_EEXIST    (-6) // CREATE target already exists
#define EFF_EPERM     (-7) // crash hooks requested but kernel built without them

// ---------------------------------------------------------------------------
// 3. Limits
// ---------------------------------------------------------------------------
// Payload bound. Chosen so one effect stays far inside MAXOPBLOCKS (10):
//   APPEND of <=256 B touches: inode blk + <=2 data blks + bitmap blk
//                              + indirect blk + table blk  = <=6 blocks.
//   CREATE touches: inode blk + dir data blk + dir bitmap/inode + file data blk
//                   + bitmap blk + table blk               = <=7 blocks.
#define EFF_MAXPAYLOAD 256

// ---------------------------------------------------------------------------
// 4. On-disk table entry: exactly 16 bytes, so 64 fit in one 1 KB block.
//    key == 0 means "slot empty" (so key 0 is not a legal idempotency key).
// ---------------------------------------------------------------------------
struct effentry {
  uint64 key;    // full 64-bit idempotency key (NEVER truncated)
  int    result; // saved result (>= 0): what we return again on replay
  uint   sig;    // 32-bit FNV-1a of (op, path, payload): detects key reuse
};

#define EFF_EPB (1024 / sizeof(struct effentry)) // entries per block (=64)

// Number of 1 KB blocks mkfs reserves for the table (location is recorded
// in the superblock: sb.effstart / sb.effblocks).  1 block = 64 entries,
// small on purpose so the "table full" test is cheap to run.
#define EFF_TABLE_BLOCKS 1

// ---------------------------------------------------------------------------
// 5. Crash-injection stages for crashhook(stage, n)   (TEST BUILDS ONLY)
//    They sit inside commit() in log.c, see docs/crash-points.md.
// ---------------------------------------------------------------------------
#define CRASH_BEFORE_HEADER  1 // log blocks written, header NOT yet -> uncommitted
#define CRASH_AFTER_HEADER   2 // header durable (commit point), nothing installed
#define CRASH_DURING_INSTALL 3 // after the n-th home-block write of install_trans
#define CRASH_AFTER_INSTALL  4 // all blocks installed, log header not yet cleared

// ---------------------------------------------------------------------------
// 6. Statistics returned by effstat(&st). Everything is a plain 64-bit
//    counter so tests can record every parameter.
// ---------------------------------------------------------------------------
struct effstats {
  uint64 executed;      // new keys: effect performed + recorded
  uint64 replayed;      // known key + same request: stored result returned
  uint64 mismatched;    // known key + different request: refused
  uint64 table_full;    // refused because table was full
  uint64 errors;        // other refused requests (EINVAL/ENOENT/EEXIST/...)
  uint64 table_used;    // occupied slots right now
  uint64 table_slots;   // total slots
  uint64 logwrites;     // total log_write() calls since boot
  uint64 diskwrites;    // total bwrite() calls since boot (real disk writes)
  uint64 last_logged;   // distinct log blocks of the most recent executed effect
  uint64 last_diskwrites; // disk writes caused by the most recent executed effect
  uint64 last_logwrites;  // log_write() calls made by the most recent executed effect
};

#endif // EFFECT_H
