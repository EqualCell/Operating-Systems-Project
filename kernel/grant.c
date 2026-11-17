// One retained grant block contains its exact approval and its one completion.
#include "types.h"
#include "riscv.h"
#include "defs.h"
#include "param.h"
#include "spinlock.h"
#include "sleeplock.h"
#include "proc.h"
#include "fs.h"
#include "file.h"
#include "stat.h"
#include "buf.h"
#include "effect.h"
#include "grant.h"

extern struct superblock sb;
extern uint64 sys_sync(void);
static struct sleeplock grants;

static int
valid(struct grant_request *r)
{
  int len = 0;
  if (!r->grant_id || (r->op != EFF_APPEND && r->op != EFF_CREATE) ||
      r->n < 0 || r->n > EFF_MAXPAYLOAD || (r->op == EFF_APPEND && !r->n))
    return 0;
  if (r->path[0] != '/')
    return 0;
  for (int i = 1; i < GR_PATH; i++) {
    char c = r->path[i];
    if (!c) { len = i; break; }
    if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
          (c >= '0' && c <= '9') || c == '.' || c == '_' || c == '-'))
      return 0;
  }
  return len >= 2 && len <= 15 && strncmp(r->path, "/.", GR_PATH) && strncmp(r->path, "/..", GR_PATH);
}

static void
getrecord(int slot, struct grant_record *r)
{
  struct buf *b = bread(ROOTDEV, sb.grstart + 1 + slot);
  memmove(r, b->data, sizeof(*r));
  brelse(b);
  if (r->binding.grant_id && (!valid(&r->binding) || !r->version ||
      r->inum < ROOTINO || r->inum >= sb.ninodes ||
      r->state < GR_ACTIVE || r->state > GR_CONSUMED ||
      (r->state == GR_CONSUMED && (!r->binding.request_id ||
       r->result < 0 || r->result > r->binding.n)) ||
      (r->state != GR_CONSUMED && r->binding.request_id)))
    panic("invalid grant record");
  if (!r->binding.grant_id) {
    char *p = (char *)r;
    for (uint i = 0; i < sizeof(*r); i++)
      if (p[i]) panic("invalid empty grant");
  }
}

static void
putrecord(int slot, struct grant_record *r)
{
  struct buf *b = bread(ROOTDEV, sb.grstart + 1 + slot);
  memmove(b->data, r, sizeof(*r));
  log_write(b);
  brelse(b);
}

// Caller holds inode lock, including protection and mutation of its version.
uint64
grant_version(struct inode *ip)
{
  if (ip->inum >= sb.ninodes || ip->inum >= GR_OBJECTS)
    panic("invalid protected inode");
  struct buf *b = bread(ROOTDEV, sb.grstart + 1 + GR_SLOTS + ip->inum / 128);
  uint64 v = ((uint64 *)b->data)[ip->inum % 128];
  brelse(b);
  return v;
}

static void
setversion(struct inode *ip, uint64 v)
{
  struct buf *b = bread(ROOTDEV, sb.grstart + 1 + GR_SLOTS + ip->inum / 128);
  ((uint64 *)b->data)[ip->inum % 128] = v;
  log_write(b);
  brelse(b);
}

void
grant_bump(struct inode *ip)
{
  uint64 v = grant_version(ip);
  if (v) {
    if (v == ~0ULL) panic("protected version overflow");
    setversion(ip, v + 1);
  }
}

void
grantinit(void)
{
  initsleeplock(&grants, "grants");
  if (sb.grstart != sb.effstart + sb.effblocks || sb.grblocks != GR_BLOCKS ||
      sb.ninodes > GR_OBJECTS || sb.grstart + sb.grblocks >= sb.size)
    panic("unsupported grant geometry");
  struct buf *b = bread(ROOTDEV, sb.grstart);
  struct grant_header h;
  memmove(&h, b->data, sizeof(h));
  brelse(b);
  if (h.magic != GR_MAGIC || h.format != GR_FORMAT ||
      h.slots != GR_SLOTS || h.objects != GR_OBJECTS)
    panic("unsupported grant format");
  struct grant_record r;
  for (int i = 0; i < GR_SLOTS; i++) getrecord(i, &r);
  // Invalid protection metadata must not let boot reclaim/reuse a pinned inode.
  begin_op();
  for (uint i = ROOTINO; i < sb.ninodes; i++) {
    struct inode *ip = iget_public(ROOTDEV, i);
    // Inspect the version without ilock first: free inodes cannot be ilocked.
    uint64 v = grant_version(ip);
    if (v) {
      ilock(ip);
      if (!((ip->type == T_FILE && ip->nlink == 1) ||
            (i == ROOTINO && ip->type == T_DIR)))
        panic("invalid protected object");
      iunlock(ip);
    }
    iput(ip);
  }
  for (int i = 0; i < GR_SLOTS; i++) {
    getrecord(i, &r);
    if (!r.binding.grant_id) continue;
    struct inode *ip = iget_public(ROOTDEV, r.inum);
    ilock(ip);
    if (grant_version(ip) < r.version ||
        (r.binding.op == EFF_APPEND && (ip->type != T_FILE || ip->nlink != 1)) ||
        (r.binding.op == EFF_CREATE && r.inum != ROOTINO))
      panic("invalid grant object");
    iunlockput(ip);
    for (int j = 0; j < i; j++) {
      struct grant_record prev;
      getrecord(j, &prev);
      if (prev.binding.grant_id == r.binding.grant_id ||
          (r.binding.request_id && prev.binding.request_id == r.binding.request_id))
        panic("duplicate grant identity");
    }
  }
  end_op();
}

uint64
sys_controller_drop(void)
{
  myproc()->controller = 0;
  return 0;
}

static int
same(struct grant_request *a, struct grant_request *b)
{
  return a->op == b->op && a->n == b->n && !strncmp(a->path, b->path, GR_PATH) &&
         !memcmp(a->payload, b->payload, a->n);
}

static int
copyrequest(struct grant_request *r)
{
  uint64 addr;
  argaddr(0, &addr);
  return copyin(myproc()->pagetable, myproc()->sz, (char *)r, addr, sizeof(*r)) == 0 && valid(r);
}

static int
find(uint64 id, struct grant_record *r, int *empty)
{
  *empty = -1;
  for (int i = 0; i < GR_SLOTS; i++) {
    getrecord(i, r);
    if (r->binding.grant_id == id) return i;
    if (!r->binding.grant_id && *empty < 0) *empty = i;
  }
  return -1;
}

static void
done(void)
{
  end_op();
  // Keep serialization until group commit has become durable.
  sys_sync();
  releasesleep(&grants);
}

uint64
sys_grant_issue(void)
{
  struct grant_request q;
  struct grant_record r;
  if (!myproc()->controller) return EFF_EPERM;
  if (!copyrequest(&q) || q.request_id) return EFF_EINVAL;
  acquiresleep(&grants);
  begin_op();
  int empty, slot = find(q.grant_id, &r, &empty), res = 0;
  if (slot >= 0) {
    res = same(&q, &r.binding) ? 0 : EFF_EMISMATCH;
  } else if (empty < 0) {
    res = EFF_EFULL;
  } else {
    struct inode *ip = namei(q.op == EFF_CREATE ? "/" : q.path);
    if (!ip) res = EFF_ENOENT;
    else {
      ilock(ip);
      if ((q.op == EFF_APPEND && (ip->type != T_FILE || ip->nlink != 1)) ||
          (q.op == EFF_CREATE && ip->inum != ROOTINO)) res = EFF_EINVAL;
      else if (grant_version(ip) == ~0ULL) res = GR_STALE;
      else {
        struct inode *exists = q.op == EFF_CREATE ? dirlookup(ip, q.path + 1, 0) : 0;
        if (exists) { iput(exists); res = EFF_EEXIST; }
        else {
          uint64 v = grant_version(ip);
          if (!v) { v = 1; setversion(ip, v); }
          memset(&r, 0, sizeof(r));
          r.binding = q;
          r.inum = ip->inum;
          r.version = v;
          r.state = GR_ACTIVE;
          putrecord(empty, &r);
        }
      }
      iunlockput(ip);
    }
  }
  done();
  return res;
}

uint64
sys_grant_revoke(void)
{
  uint64 id;
  argaddr(0, &id);
  if (!myproc()->controller) return EFF_EPERM;
  if (!id) return EFF_EINVAL;
  acquiresleep(&grants);
  begin_op();
  struct grant_record r;
  int empty, slot = find(id, &r, &empty), res = 0;
  if (slot < 0) res = GR_ENOENT;
  else if (r.state == GR_CONSUMED) res = GR_CONSUMED_ERR;
  else if (r.state == GR_ACTIVE) { r.state = GR_REVOKED; putrecord(slot, &r); }
  done();
  return res;
}

uint64
sys_grant_effect(void)
{
  struct proc *p = myproc();
  p->effect_outcome = 0;
  struct grant_request q;
  struct grant_record r;
  if (!copyrequest(&q) || !q.request_id) return EFF_EINVAL;
  acquiresleep(&grants);
  begin_op();
  int empty, slot = find(q.grant_id, &r, &empty), res;
  if (slot < 0) res = GR_ENOENT;
  else if (!same(&q, &r.binding)) res = EFF_EMISMATCH;
  else if (r.state == GR_CONSUMED && r.binding.request_id == q.request_id) {
    res = r.result;
    p->effect_outcome = 2;
  } else if (r.state == GR_CONSUMED) res = GR_CONSUMED_ERR;
  else if (r.state == GR_REVOKED) res = GR_REVOKED_ERR;
  else {
    // Request IDs are global in this single authorization domain.
    struct grant_record other;
    res = 0;
    for (int i = 0; i < GR_SLOTS; i++) {
      getrecord(i, &other);
      if (other.binding.request_id == q.request_id) { res = EFF_EMISMATCH; break; }
    }
    if (!res) {
      struct inode *ip = namei(q.op == EFF_CREATE ? "/" : q.path);
      if (!ip) res = GR_STALE;
      else {
        ilock(ip);
        if (ip->inum != r.inum || grant_version(ip) != r.version || r.version == ~0ULL)
          res = GR_STALE;
        else if (q.op == EFF_APPEND) {
          res = writei(ip, 0, (uint64)q.payload, ip->size, q.n);
          if (res == 0) res = EFF_EIO;
          if (res < 0 && res != EFF_EIO) res = EFF_EINVAL;
        } else {
          // Parent stays locked through exclusive lookup and insertion.
          res = grant_create(ip, q.path + 1, q.payload, q.n);
        }
        if (res >= 0) {
          r.binding.request_id = q.request_id;
          r.result = res;
          r.state = GR_CONSUMED;
          putrecord(slot, &r);
          p->effect_outcome = 1;
        }
        iunlockput(ip);
      }
    }
  }
  done();
  return res;
}

// Read-only status: request 0 queries grant; nonzero must match completion.
uint64
sys_grant_status(void)
{
  uint64 id, req, addr;
  argaddr(0, &id); argaddr(1, &req); argaddr(2, &addr);
  if (!id) return EFF_EINVAL;
  acquiresleep(&grants);
  begin_op();
  struct grant_record r;
  struct grant_status out;
  int empty, slot = find(id, &r, &empty), res = 0;
  if (slot < 0) res = GR_ENOENT;
  else if (req && r.state == GR_CONSUMED && req != r.binding.request_id) res = EFF_EMISMATCH;
  else {
    out.request_id = r.binding.request_id;
    out.expected_version = r.version;
    struct inode *ip = iget_public(ROOTDEV, r.inum);
    ilock(ip);
    out.current_version = grant_version(ip);
    iunlockput(ip);
    out.state = r.state;
    out.result = r.state == GR_CONSUMED ? r.result : GR_PENDING;
  }
  done();
  if (!res && copyout(myproc()->pagetable, myproc()->sz, addr, (char *)&out, sizeof(out)) < 0)
    res = EFF_EINVAL;
  return res;
}

void
grant_protect(struct inode *ip)
{
  if (!grant_version(ip)) setversion(ip, 1);
}
