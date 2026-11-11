// effect_ops.c -- the actual FILE EFFECTS (APPEND / CREATE), nothing else.
//
// These helpers are called by sys_effect() in effect.c, which already holds
// effect_lock and has already called begin_op().  They therefore:
//   * never call begin_op()/end_op() themselves (no nested/split transaction);
//   * only touch blocks through the normal fs.c routines, which stage every
//     change with log_write().
//
// They return  >= 0  : number of bytes that now belong to the file (success)
//              <  0  : an EFF_E* error code; NOTHING durable was changed
//                      (we only report an error before any block is modified,
//                       except the documented short-write case for APPEND).
//
// Concurrency note: other (non-effect) processes may run ordinary FS system
// calls at the same time. They use ilock() on inodes, and we take the same
// inode lock, so file bytes are never interleaved.

#include "types.h"
#include "riscv.h"
#include "defs.h"
#include "param.h"
#include "stat.h"
#include "spinlock.h"
#include "sleeplock.h"
#include "fs.h"
#include "file.h"
#include "effect.h"

// 32-bit FNV-1a over (op, path, payload).  Stored in the table next to the
// key.  If the same key comes back with a different request the signature
// differs and we refuse (EFF_EMISMATCH) instead of replaying a stranger's
// result.  (A 32-bit signature can collide with probability 2^-32; this is a
// documented limitation, not a security boundary.)
uint
effect_sig(int op, const char *path, const char *buf, int n)
{
  uint h = 2166136261u;
#define MIX(b) do { h ^= (uchar)(b); h *= 16777619u; } while (0)
  MIX(op);
  for (const char *p = path; *p; p++)
    MIX(*p);
  MIX(0); // path terminator, so ("/a","bc") != ("/ab","c")
  for (int i = 0; i < n; i++)
    MIX(buf[i]);
#undef MIX
  return h;
}

// APPEND n bytes (kernel buffer) to the existing regular file `path`.
// Short-write semantics: if the disk fills up half-way, the bytes that DID get
// written are the result and are recorded together with the key, so replay
// reports the same short count. Nothing is ever written without a record.
int
effect_do_append(char *path, char *kbuf, int n)
{
  struct inode *ip;
  int r;

  if ((ip = namei(path)) == 0)
    return EFF_ENOENT;
  ilock(ip);
  if (ip->type != T_FILE) { // never append to directories / devices
    iunlockput(ip);
    return EFF_EINVAL;
  }
  r = writei(ip, 0, (uint64)kbuf, ip->size, n); // 0 => kernel source address
  iunlockput(ip);
  if (r < 0)
    return EFF_EINVAL; // e.g. would exceed the maximum file size
  if (r == 0 && n > 0)
    return EFF_EIO; // disk full before the first byte: nothing happened
  return r;
}

// CREATE a new regular file `path` containing the n bytes of kbuf.
int
effect_do_create(char *path, char *kbuf, int n)
{
  struct inode *ip;
  int r = 0;

  if ((ip = namei(path)) != 0) { // already exists: a CREATE must not clobber it
    iput(ip);
    return EFF_EEXIST;
  }
  if ((ip = create(path, T_FILE, 0, 0)) == 0) // returns ip LOCKED
    return EFF_EINVAL; // missing parent directory, out of inodes, ...
  if (n > 0) {
    r = writei(ip, 0, (uint64)kbuf, 0, n);
    if (r < 0)
      r = 0;
  }
  iunlockput(ip);
  return r; // the file exists even if r < n (short write is recorded)
}
