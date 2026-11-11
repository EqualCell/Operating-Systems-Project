// effect_store.c -- the PERSISTENT effect table (storage layer only).
//
// This file knows how entries are laid out on disk and how to find / insert
// them. It knows NOTHING about files, syscalls or policy (that is effect.c and
// effect_ops.c). Keeping it separate makes it easy to test and to explain:
//
//   "key -> result" map,  stored in the blocks mkfs reserved,
//   open addressing: hash the key, then probe linearly.
//
// RULES FOR CALLERS
//   * Every function here must be called INSIDE a begin_op()/end_op() pair,
//     because store_put() changes a block through log_write().
//     (store_find() only reads, but we call it inside the same transaction.)
//   * The caller must hold effect_lock (see effect.c) so two processes cannot
//     pick the same empty slot.
//   * Nothing here starts, ends or splits a transaction.
//
// LAYOUT (see kernel/effect.h):  slot s lives in block  sb.effstart + s/64,
// at index s%64 inside that block.  key==0 means "empty slot".

#include "types.h"
#include "riscv.h"
#include "defs.h"
#include "param.h"
#include "spinlock.h"
#include "sleeplock.h"
#include "fs.h"
#include "buf.h"
#include "effect.h"

extern struct superblock sb; // fs.c

// Total number of slots in the table.
int
store_slots(void)
{
  return sb.effblocks * EFF_EPB;
}

// Hash a 64-bit key to a starting slot (Fibonacci-style multiplicative hash).
static uint
store_hash(uint64 key)
{
  uint64 h = key * 0x9E3779B97F4A7C15ULL;
  return (uint)(h >> 32) % store_slots();
}

// Locate the slot for `key`.
//   returns  1 and fills *out : key is present at *slot
//   returns  0                : key is absent; *slot = first empty slot
//                               (where it should be inserted)
//   returns -1                : key is absent AND the table has no empty slot
//                               (table full)
// Deletion never happens, so an empty slot ends the probe sequence.
int
store_find(uint64 key, int *slot, struct effentry *out)
{
  int nslots = store_slots();
  int start = store_hash(key);

  for (int i = 0; i < nslots; i++) {
    int s = (start + i) % nslots;
    struct buf *bp = bread(ROOTDEV, sb.effstart + s / EFF_EPB);
    struct effentry e = ((struct effentry *)bp->data)[s % EFF_EPB];
    brelse(bp);

    if (e.key == key) {
      *slot = s;
      if (out)
        *out = e;
      return 1;
    }
    if (e.key == 0) {
      *slot = s;
      return 0;
    }
  }
  return -1;
}

// Write an entry into a slot previously returned by store_find().
// The change is staged with log_write(), so it becomes durable atomically
// with every other block of the same transaction (the file change!).
void
store_put(int slot, uint64 key, int result, uint sig)
{
  struct buf *bp = bread(ROOTDEV, sb.effstart + slot / EFF_EPB);
  struct effentry *e = &((struct effentry *)bp->data)[slot % EFF_EPB];
  e->key = key;
  e->result = result;
  e->sig = sig;
  log_write(bp);
  brelse(bp);
}

// Count occupied slots (for statistics / tests; read-only).
int
store_used(void)
{
  int used = 0;
  for (int b = 0; b < (int)sb.effblocks; b++) {
    struct buf *bp = bread(ROOTDEV, sb.effstart + b);
    for (int i = 0; i < (int)EFF_EPB; i++)
      if (((struct effentry *)bp->data)[i].key != 0)
        used++;
    brelse(bp);
  }
  return used;
}
