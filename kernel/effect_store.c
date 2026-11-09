#include "types.h"
#include "param.h"
#include "stat.h"
#include "fs.h"
#include "spinlock.h"
#include "sleeplock.h"
#include "proc.h"
#include "defs.h"
#include "effect_store.h"

#define EFFECT_STORE_SLOTS 64

#ifndef EFFECT_USE_MEM_DOUBLE
#define EFFECT_USE_MEM_DOUBLE 1
#endif

static struct spinlock store_lock;
static struct effect_record effects[EFFECT_STORE_SLOTS];
static struct grant_record grants[EFFECT_STORE_SLOTS];
static uint64 versions[EFFECT_STORE_SLOTS];
static uint32 generations[EFFECT_STORE_SLOTS];
static uint32 version_inums[EFFECT_STORE_SLOTS];
static uint32 version_devs[EFFECT_STORE_SLOTS];
static uint32 version_used[EFFECT_STORE_SLOTS];

static int
version_slot(uint dev, uint inum, int allocate)
{
  int i, free_slot = -1;
  for (i = 0; i < EFFECT_STORE_SLOTS; i++) {
    if (version_used[i] && version_devs[i] == dev &&
        version_inums[i] == inum)
      return i;
    if (!version_used[i] && free_slot < 0)
      free_slot = i;
  }
  if (!allocate || free_slot < 0)
    return -1;
  version_used[free_slot] = 1;
  version_devs[free_slot] = dev;
  version_inums[free_slot] = inum;
  generations[free_slot] = 1;
  return free_slot;
}

void
effect_store_init(void)
{
  initlock(&store_lock, "effect_store");
  memset(effects, 0, sizeof(effects));
  memset(grants, 0, sizeof(grants));
  memset(version_used, 0, sizeof(version_used));
}

int
effect_store_lookup_base(uint64 key, struct effect_record *out)
{
  int i;
  acquire(&store_lock);
  for (i = 0; i < EFFECT_STORE_SLOTS; i++)
    if (effects[i].valid && !effects[i].is_extended &&
        effects[i].key_or_req_id == key) {
      *out = effects[i];
      release(&store_lock);
      return 1;
    }
  release(&store_lock);
  return 0;
}

int
effect_store_lookup_ext(uint64 grant_id, uint64 req_id,
                        struct effect_record *out)
{
  int i;
  acquire(&store_lock);
  for (i = 0; i < EFFECT_STORE_SLOTS; i++)
    if (effects[i].valid && effects[i].is_extended &&
        effects[i].grant_id == grant_id &&
        effects[i].key_or_req_id == req_id) {
      *out = effects[i];
      release(&store_lock);
      return 1;
    }
  release(&store_lock);
  return 0;
}

int
effect_store_has_free_slot(void)
{
  int i, free_slot = 0;
  acquire(&store_lock);
  for (i = 0; i < EFFECT_STORE_SLOTS; i++)
    if (!effects[i].valid) {
      free_slot = 1;
      break;
    }
  release(&store_lock);
  return free_slot;
}

int
effect_store_insert(const struct effect_record *record)
{
  int i;
  acquire(&store_lock);
  for (i = 0; i < EFFECT_STORE_SLOTS; i++)
    if (!effects[i].valid) {
      effects[i] = *record;
      effects[i].valid = 1;
      release(&store_lock);
      return 0;
    }
  release(&store_lock);
  return -1;
}

int
effect_store_grant_lookup(uint64 grant_id, struct grant_record *out)
{
  int i;
  acquire(&store_lock);
  for (i = 0; i < EFFECT_STORE_SLOTS; i++)
    if (grants[i].valid && grants[i].grant_id == grant_id) {
      *out = grants[i];
      release(&store_lock);
      return 1;
    }
  release(&store_lock);
  return 0;
}

int
effect_store_grant_has_slot(void)
{
  int i, found = 0;
  acquire(&store_lock);
  for (i = 0; i < EFFECT_STORE_SLOTS; i++)
    if (!grants[i].valid) {
      found = 1;
      break;
    }
  release(&store_lock);
  return found;
}

int
effect_store_grant_alloc(const struct grant_record *record)
{
  int i;
  acquire(&store_lock);
  for (i = 0; i < EFFECT_STORE_SLOTS; i++)
    if (!grants[i].valid) {
      grants[i] = *record;
      grants[i].valid = 1;
      release(&store_lock);
      return 0;
    }
  release(&store_lock);
  return -1;
}

int
effect_store_grant_update(const struct grant_record *record)
{
  int i;
  acquire(&store_lock);
  for (i = 0; i < EFFECT_STORE_SLOTS; i++)
    if (grants[i].valid && grants[i].grant_id == record->grant_id) {
      grants[i] = *record;
      release(&store_lock);
      return 0;
    }
  release(&store_lock);
  return -1;
}

static void
snapshot_locked(struct inode *ip, struct file_id_snapshot *snapshot)
{
  int slot = version_slot(ip->dev, ip->inum, 1);
  snapshot->dev = ip->dev;
  snapshot->inum = ip->inum;
  snapshot->gen = generations[slot];
  snapshot->exists = 1;
  snapshot->version = versions[slot];
  snapshot->size = ip->size;
}

int
effect_fs_snapshot_path(char *path, struct file_id_snapshot *snapshot)
{
  struct inode *ip = namei(path);
  if (ip == 0)
    return EFFECT_ERR_NOENT;
  ilock(ip);
  snapshot_locked(ip, snapshot);
  iunlockput(ip);
  return EFFECT_OK_COMMITTED;
}

static int
execute_append(struct inode *ip, uint8 *payload, uint32 n,
               struct file_id_snapshot *after, int *bytes)
{
  int slot;
  int written = writei(ip, 0, (uint64)payload, ip->size, n);
  if (written != (int)n)
    return EFFECT_ERR_NOSPC;
  slot = version_slot(ip->dev, ip->inum, 1);
  versions[slot]++;
  snapshot_locked(ip, after);
  *bytes = written;
  return EFFECT_OK_COMMITTED;
}

int
effect_fs_execute_base(uint32 op, char *path, uint8 *payload, uint32 n,
                       struct file_id_snapshot *after, int *bytes)
{
  struct inode *ip;
  int result;

  if (op == EFFECT_OP_CREATE) {
    ip = namei(path);
    if (ip != 0) {
      iput(ip);
      return EFFECT_ERR_EXIST;
    }
    ip = effect_create_file(path);
    if (ip == 0)
      return EFFECT_ERR_NOSPC;
    snapshot_locked(ip, after);
    iunlockput(ip);
    *bytes = 0;
    return EFFECT_OK_COMMITTED;
  }
  if (op != EFFECT_OP_APPEND)
    return EFFECT_ERR_INVALID;
  ip = namei(path);
  if (ip == 0)
    return EFFECT_ERR_NOENT;
  ilock(ip);
  if (ip->type != T_FILE) {
    iunlockput(ip);
    return EFFECT_ERR_INVALID;
  }
  result = execute_append(ip, payload, n, after, bytes);
  iunlockput(ip);
  return result;
}

int
effect_fs_execute_checked_append(char *path, uint8 *payload, uint32 n,
                                 uint32 target_inum, uint32 target_gen,
                                 uint64 bound_version,
                                 struct file_id_snapshot *after, int *bytes)
{
  struct inode *ip = namei(path);
  struct file_id_snapshot current;
  int result;
  if (ip == 0)
    return EFFECT_ERR_NOENT;
  ilock(ip);
  snapshot_locked(ip, &current);
  if (current.inum != target_inum || current.gen != target_gen ||
      current.version != bound_version) {
    iunlockput(ip);
    return EFFECT_ERR_STALE;
  }
  result = execute_append(ip, payload, n, after, bytes);
  iunlockput(ip);
  return result;
}

int
effect_auth_can_mutate_inode(struct inode *ip)
{
  (void)ip;
  return myproc()->effect_role == ROLE_AGENT ? -1 : 0;
}

int
effect_auth_can_create_in_dir(struct inode *dp)
{
  (void)dp;
  return myproc()->effect_role == ROLE_AGENT ? -1 : 0;
}

void
effect_test_double_bump_version(struct inode *ip)
{
  int slot;
#if EFFECT_USE_MEM_DOUBLE
  if (myproc()->effect_role == ROLE_AGENT)
    return;
  slot = version_slot(ip->dev, ip->inum, 1);
  versions[slot]++;
#else
  (void)ip;
#endif
}
