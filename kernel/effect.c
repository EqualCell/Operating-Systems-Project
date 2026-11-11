// effect.c -- system calls for exactly-once effects across crashes.
//
//   effect(key, op, path, buf, n)   the assigned syscall
//   crashat(n)                      test hook: panic at the n-th log_write
//   crashhook(stage, n)             test hook: panic at a point inside commit()
//   effstat(&st)                    read statistics (for tests)
//
// THE WHOLE IDEA, in 12 lines (see sys_effect below):
//
//     lock(effect_lock)                  // one effect at a time (first version)
//     begin_op()                         // ONE transaction ...
//       look key up in the persistent table
//       key found?  -> return the saved result, change nothing
//       key absent? -> do the file effect  +  write the table entry
//     end_op()                           // ... both reach the disk together
//     unlock(effect_lock)
//     wait until the commit is durable   // only then answer the caller
//
// WHY THIS IS EXACTLY-ONCE
//   xv6's log commits all blocks of a transaction at ONE atomic moment
//   (write_head() in log.c).  The file blocks and the table block are in the
//   same transaction, so after any crash the disk holds either BOTH or NEITHER:
//     NEITHER -> retry sees no key  -> performs the effect          (once)
//     BOTH    -> retry sees the key -> returns the saved result     (once)
//
// LOCK ORDER (outermost first; never acquire in the opposite direction)
//     effect_lock  ->  log (begin_op/end_op)  ->  inode locks  ->  buffer locks
//   * effect_lock is taken BEFORE begin_op, so a process never sits inside a
//     transaction while waiting for another effect (no circular wait).
//   * inode locks are always released before end_op().
//   * we never hold a spinlock across disk I/O (effect_lock is a sleeplock).

#include "types.h"
#include "riscv.h"
#include "defs.h"
#include "param.h"
#include "spinlock.h"
#include "sleeplock.h"
#include "fs.h"
#include "proc.h"
#include "effect.h"

// ---- provided by the other effect modules / log.c / bio.c ----
int  store_find(uint64 key, int *slot, struct effentry *out);
void store_put(int slot, uint64 key, int result, uint sig);
int  store_slots(void);
int  store_used(void);
uint effect_sig(int op, const char *path, const char *buf, int n);
int  effect_do_append(char *path, char *kbuf, int n);
int  effect_do_create(char *path, char *kbuf, int n);
int  log_nblocks(void);
extern uint64 sys_sync(void);
extern int crash_logwrite_n, crash_logwrite_count;
extern int crash_stage, crash_stage_n, crash_stage_count;
extern uint64 stat_logwrites, stat_diskwrites;

static struct sleeplock effect_lock;
static struct effstats st; // protected by effect_lock (except effstat's read)

void
effectinit(void)
{
  initsleeplock(&effect_lock, "effect");
}

// effect(key, op, path, buf, n)
//   returns >= 0 : result (bytes written), either freshly executed or replayed
//   returns <  0 : EFF_E* error; nothing durable was changed by THIS call
uint64
sys_effect(void)
{
  uint64 key, ubuf;
  int op, n;
  char path[MAXPATH];
  char kbuf[EFF_MAXPAYLOAD];
  struct proc *p = myproc();

  // The key is a 64-bit value: read it with argaddr(), NEVER argint(), which
  // would truncate it to 32 bits and make keys differing only in the high
  // half collide silently.
  argaddr(0, &key);
  argint(1, &op);
  argaddr(3, &ubuf);
  argint(4, &n);
  if (argstr(2, path, MAXPATH) < 0)
    return EFF_EINVAL;

  // ---- validate everything BEFORE locking or touching the disk ----
  if (key == 0)
    return EFF_EINVAL; // 0 marks an empty table slot
  if (op != EFF_APPEND && op != EFF_CREATE)
    return EFF_EINVAL;
  if (n < 0 || n > EFF_MAXPAYLOAD)
    return EFF_EINVAL;
  if (op == EFF_APPEND && n == 0)
    return EFF_EINVAL;
  if (path[0] != '/' || path[1] == 0)
    return EFF_EINVAL;
  // Never dereference a user pointer: copy the payload into kernel memory.
  if (n > 0 && copyin(p->pagetable, p->sz, kbuf, ubuf, n) != 0)
    return EFF_EINVAL;

  uint sig = effect_sig(op, path, kbuf, n);
  int res, slot = -1;
  struct effentry e;
  int executed = 0;
  uint64 lw0 = stat_logwrites, dw0 = stat_diskwrites;
  uint64 logged = 0;

  acquiresleep(&effect_lock); // serialise effects (also same-key racers)
  begin_op();                 // ONE transaction covers lookup + effect + record

  int found = store_find(key, &slot, &e);
  if (found == 1) {
    if (e.sig != sig) {
      res = EFF_EMISMATCH; // same key, different request: refuse
      st.mismatched++;
    } else {
      res = e.result; // already done: return the saved result, change nothing
      st.replayed++;
    }
  } else if (found < 0) {
    res = EFF_EFULL; // checked BEFORE the file is modified
    st.table_full++;
  } else {
    // New key: perform the effect, then record it IN THE SAME TRANSACTION.
    if (op == EFF_APPEND)
      res = effect_do_append(path, kbuf, n);
    else
      res = effect_do_create(path, kbuf, n);

    if (res >= 0) {
      store_put(slot, key, res, sig);
      logged = log_nblocks(); // distinct blocks this transaction logged
      executed = 1;
    } else {
      st.errors++; // nothing was modified, nothing is recorded
    }
  }

  end_op(); // commit point is reached inside here (if we were the last op)
  if (executed) {
    st.executed++;
    st.last_logged = logged;
  }
  releasesleep(&effect_lock);

  // end_op() only commits when no other FS operation is in flight (group
  // commit).  Do not answer before OUR changes are durable: wait until the
  // commit that contains them has finished.  (This is a no-op in the common
  // case where our own end_op() performed the commit.)
  sys_sync();

  if (executed) {
    st.last_logwrites = stat_logwrites - lw0;
    st.last_diskwrites = stat_diskwrites - dw0;
  }
  return res;
}

// effstat(struct effstats *st): copy the counters to user space.
uint64
sys_effstat(void)
{
  uint64 uaddr;
  struct effstats out;
  struct proc *p = myproc();

  argaddr(0, &uaddr);
  acquiresleep(&effect_lock);
  out = st;
  out.table_slots = store_slots();
  out.logwrites = stat_logwrites;
  out.diskwrites = stat_diskwrites;
  begin_op(); // store_used() reads via the buffer cache
  out.table_used = store_used();
  end_op();
  releasesleep(&effect_lock);
  if (copyout(p->pagetable, p->sz, uaddr, (char *)&out, sizeof(out)) < 0)
    return -1;
  return 0;
}

// crashat(n): panic at the n-th log_write() from now (n = 0 disarms).
// Only available in builds compiled with -DEFFECT_TESTHOOKS.
uint64
sys_crashat(void)
{
#ifdef EFFECT_TESTHOOKS
  int n;
  argint(0, &n);
  if (n < 0)
    return EFF_EINVAL;
  crash_logwrite_count = 0;
  crash_logwrite_n = n;
  return 0;
#else
  return EFF_EPERM;
#endif
}

// crashhook(stage, n): panic at the n-th time commit() reaches `stage`
// (stage = 0 disarms). Only available in test builds.
uint64
sys_crashhook(void)
{
#ifdef EFFECT_TESTHOOKS
  int stage, n;
  argint(0, &stage);
  argint(1, &n);
  if (stage == 0) { // disarm
    crash_stage = 0;
    return 0;
  }
  if (stage < 0 || stage > CRASH_AFTER_INSTALL || n < 1)
    return EFF_EINVAL;
  crash_stage_count = 0;
  crash_stage_n = n;
  crash_stage = stage;
  return 0;
#else
  return EFF_EPERM;
#endif
}
