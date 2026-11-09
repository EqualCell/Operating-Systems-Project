#include "types.h"
#include "param.h"
#include "riscv.h"
#include "defs.h"
#include "spinlock.h"
#include "proc.h"
#include "sleeplock.h"
#include "effect.h"
#include "effect_store.h"

#ifndef EFFECT_USE_MEM_DOUBLE
#define EFFECT_USE_MEM_DOUBLE 1
#endif

struct sleeplock effect_gate_lock;
static uint64 next_grant_id = 1;

static uint64
effect_hash(uint32 op, char *path, uint8 *buf, uint32 n)
{
  uint64 hash = 1469598103934665603ULL;
  uint i;
  for (i = 0; i < sizeof(op); i++) {
    hash ^= (uint8)(op >> (i * 8));
    hash *= 1099511628211ULL;
  }
  for (i = 0; path[i] != 0; i++) {
    hash ^= (uint8)path[i];
    hash *= 1099511628211ULL;
  }
  hash ^= 0xff;
  hash *= 1099511628211ULL;
  for (i = 0; i < n; i++) {
    hash ^= buf[i];
    hash *= 1099511628211ULL;
  }
  for (i = 0; i < sizeof(n); i++) {
    hash ^= (uint8)(n >> (i * 8));
    hash *= 1099511628211ULL;
  }
  return hash;
}

void
effect_init(void)
{
  initsleeplock(&effect_gate_lock, "effect_gate");
  effect_store_init();
}

static int
copy_checked_req(uint64 addr, struct effect_checked_req *req)
{
  struct proc *p = myproc();
  return copyin(p->pagetable, p->sz, (char *)req, addr, sizeof(*req));
}

static int
valid_path(char *path)
{
  int i;
  for (i = 0; i < EFFECT_MAX_PATH; i++)
    if (path[i] == 0)
      return 1;
  return 0;
}

uint64
sys_effect(void)
{
  int op, n, bytes = 0, result;
  uint64 key, buf_addr;
  char path[EFFECT_MAX_PATH];
  uint8 payload[EFFECT_MAX_PAYLOAD];
  struct effect_record record, cached;
  struct file_id_snapshot snapshot;
  uint64 arg_hash;

  argaddr(0, &key);
  argint(1, &op);
  if (argstr(2, path, sizeof(path)) < 0)
    return EFFECT_ERR_INVALID;
  argaddr(3, &buf_addr);
  argint(4, &n);
  if (n < 0 || n > EFFECT_MAX_PAYLOAD || !valid_path(path))
    return EFFECT_ERR_INVALID;
  if (n && copyin(myproc()->pagetable, myproc()->sz, (char *)payload,
                  buf_addr, n) < 0)
    return EFFECT_ERR_INVALID;

  arg_hash = effect_hash((uint32)op, path, payload, (uint32)n);
  begin_op();
  acquiresleep(&effect_gate_lock);
  if (effect_store_lookup_base(key, &cached)) {
    releasesleep(&effect_gate_lock);
    log_end_op_and_wait();
    if (cached.arg_hash != arg_hash || cached.op != (uint32)op)
      return EFFECT_ERR_ARG_MISMATCH;
    return cached.result_bytes;
  }
  if (!effect_store_has_free_slot()) {
    releasesleep(&effect_gate_lock);
    log_end_op_and_wait();
    return EFFECT_ERR_TABLE_FULL;
  }
  result = effect_fs_execute_base((uint32)op, path, payload, (uint32)n,
                                  &snapshot, &bytes);
  if (result == EFFECT_OK_COMMITTED) {
    memset(&record, 0, sizeof(record));
    record.is_extended = 0;
    record.key_or_req_id = key;
    record.arg_hash = arg_hash;
    record.op = (uint32)op;
    record.target_inum = snapshot.inum;
    record.target_gen = snapshot.gen;
    record.result_bytes = bytes;
    record.post_version = snapshot.version;
    if (effect_store_insert(&record) < 0)
      result = EFFECT_ERR_TABLE_FULL;
  }
  releasesleep(&effect_gate_lock);
  log_end_op_and_wait();
  return result == EFFECT_OK_COMMITTED ? bytes : result;
}

uint64
sys_grant_create(void)
{
  uint64 addr;
  struct grant_spec spec;
  struct grant_record grant;
  struct file_id_snapshot snapshot;
  if (myproc()->effect_role != ROLE_CONTROLLER)
    return EFFECT_ERR_PERM;
  argaddr(0, &addr);
  if (copyin(myproc()->pagetable, myproc()->sz, (char *)&spec, addr,
             sizeof(spec)) < 0 ||
      spec.abi_version != EFFECT_ABI_VERSION ||
      spec.allowed_op != EFFECT_OP_APPEND ||
      spec.max_payload_len > EFFECT_MAX_PAYLOAD || spec.flags != 0 ||
      !valid_path(spec.path))
    return EFFECT_ERR_INVALID;
  begin_op();
  acquiresleep(&effect_gate_lock);
  if (!effect_store_grant_has_slot() ||
      effect_fs_snapshot_path(spec.path, &snapshot) != EFFECT_OK_COMMITTED) {
    releasesleep(&effect_gate_lock);
    log_end_op_and_wait();
    return EFFECT_ERR_NOENT;
  }
  memset(&grant, 0, sizeof(grant));
  grant.state = GRANT_STATE_ACTIVE;
  grant.grant_id = next_grant_id++;
  grant.allowed_op = spec.allowed_op;
  grant.max_payload_len = spec.max_payload_len;
  grant.target_inum = snapshot.inum;
  grant.target_gen = snapshot.gen;
  grant.bound_version = snapshot.version;
  if (effect_store_grant_alloc(&grant) < 0) {
    releasesleep(&effect_gate_lock);
    log_end_op_and_wait();
    return EFFECT_ERR_TABLE_FULL;
  }
  spec.out_grant_id = grant.grant_id;
  spec.out_inum = grant.target_inum;
  spec.out_gen = grant.target_gen;
  spec.out_version = grant.bound_version;
  releasesleep(&effect_gate_lock);
  log_end_op_and_wait();
  if (copyout(myproc()->pagetable, myproc()->sz, addr, (char *)&spec,
              sizeof(spec)) < 0)
    return EFFECT_ERR_INVALID;
  return EFFECT_OK_COMMITTED;
}

uint64
sys_revoke(void)
{
  uint64 grant_id;
  struct grant_record grant;
  argaddr(0, &grant_id);
  begin_op();
  acquiresleep(&effect_gate_lock);
  if (!effect_store_grant_lookup(grant_id, &grant)) {
    releasesleep(&effect_gate_lock);
    log_end_op_and_wait();
    return EFFECT_ERR_NOENT;
  }
  if (myproc()->effect_role != ROLE_CONTROLLER) {
    releasesleep(&effect_gate_lock);
    log_end_op_and_wait();
    return EFFECT_ERR_PERM;
  }
  if (grant.state == GRANT_STATE_CONSUMED) {
    releasesleep(&effect_gate_lock);
    log_end_op_and_wait();
    return EFFECT_ERR_CONSUMED;
  }
  grant.state = GRANT_STATE_REVOKED;
  effect_store_grant_update(&grant);
  releasesleep(&effect_gate_lock);
  log_end_op_and_wait();
  return EFFECT_OK_COMMITTED;
}

uint64
sys_effect_checked(void)
{
  uint64 addr;
  struct effect_checked_req req;
  struct effect_record record;
  struct grant_record grant;
  struct file_id_snapshot snapshot;
  int result, bytes = 0;

  argaddr(0, &addr);
  if (copy_checked_req(addr, &req) < 0 ||
      req.abi_version != EFFECT_ABI_VERSION || req.op != EFFECT_OP_APPEND ||
      req.flags != 0 || req.payload_len > EFFECT_MAX_PAYLOAD ||
      !valid_path(req.path))
    return EFFECT_ERR_INVALID;
  begin_op();
  acquiresleep(&effect_gate_lock);
  if (effect_store_lookup_ext(req.grant_id, req.req_id, &record)) {
    result = record.arg_hash == req.arg_hash ? EFFECT_OK_CACHED :
                                                EFFECT_ERR_ARG_MISMATCH;
    req.out_status = result;
    req.out_bytes = record.result_bytes;
    releasesleep(&effect_gate_lock);
    log_end_op_and_wait();
    copyout(myproc()->pagetable, myproc()->sz, addr, (char *)&req,
            sizeof(req));
    return result;
  }
  if (!effect_store_grant_lookup(req.grant_id, &grant)) {
    result = EFFECT_ERR_NOENT;
    goto checked_done;
  }
  if (grant.state == GRANT_STATE_REVOKED) {
    result = EFFECT_ERR_REVOKED;
    goto checked_done;
  }
  if (grant.state == GRANT_STATE_CONSUMED) {
    result = EFFECT_ERR_CONSUMED;
    goto checked_done;
  }
  if (grant.allowed_op != req.op || req.payload_len > grant.max_payload_len ||
      !effect_store_has_free_slot()) {
    result = !effect_store_has_free_slot() ? EFFECT_ERR_TABLE_FULL :
                                             EFFECT_ERR_PERM;
    goto checked_done;
  }
  if (effect_hash(req.op, req.path, req.payload, req.payload_len) !=
      req.arg_hash) {
    result = EFFECT_ERR_ARG_MISMATCH;
    goto checked_done;
  }
  result = effect_fs_execute_checked_append(
      req.path, req.payload, req.payload_len, grant.target_inum,
      grant.target_gen, grant.bound_version, &snapshot, &bytes);
  if (result == EFFECT_OK_COMMITTED) {
    grant.state = GRANT_STATE_CONSUMED;
    grant.consumed_req_id = req.req_id;
    grant.consumed_arg_hash = req.arg_hash;
    effect_store_grant_update(&grant);
    log_crash_if(CRASH_HOOK_AFTER_GRANT_CONSUME);
    memset(&record, 0, sizeof(record));
    record.is_extended = 1;
    record.key_or_req_id = req.req_id;
    record.grant_id = req.grant_id;
    record.arg_hash = req.arg_hash;
    record.op = req.op;
    record.target_inum = snapshot.inum;
    record.target_gen = snapshot.gen;
    record.result_bytes = bytes;
    record.post_version = snapshot.version;
    effect_store_insert(&record);
  }
checked_done:
  req.out_status = result;
  req.out_bytes = result == EFFECT_OK_COMMITTED ? bytes : 0;
  releasesleep(&effect_gate_lock);
  log_end_op_and_wait();
  if (copyout(myproc()->pagetable, myproc()->sz, addr, (char *)&req,
              sizeof(req)) < 0)
    return EFFECT_ERR_INVALID;
  return result;
}

uint64
sys_effect_status(void)
{
  uint64 qaddr, raddr;
  struct effect_status_query query;
  struct effect_status_result result;
  struct effect_record record;
  struct grant_record grant;
  int found;
  argaddr(0, &qaddr);
  argaddr(1, &raddr);
  if (copyin(myproc()->pagetable, myproc()->sz, (char *)&query, qaddr,
             sizeof(query)) < 0 ||
      query.abi_version != EFFECT_ABI_VERSION)
    return EFFECT_ERR_INVALID;
  memset(&result, 0, sizeof(result));
  found = query.is_extended
              ? effect_store_lookup_ext(query.grant_id, query.key_or_req_id,
                                        &record)
              : effect_store_lookup_base(query.key_or_req_id, &record);
  if (!found)
    result.status = EFFECT_ERR_NOT_RECORDED;
  else if (query.expected_arg_hash != 0 &&
           query.expected_arg_hash != record.arg_hash)
    result.status = EFFECT_ERR_ARG_MISMATCH;
  else {
    result.status = EFFECT_OK_COMMITTED;
    result.bytes_written = record.result_bytes;
    result.committed_version = record.post_version;
    result.recorded_arg_hash = record.arg_hash;
  }
  if (query.is_extended && effect_store_grant_lookup(query.grant_id, &grant))
    result.grant_state = grant.state;
  if (copyout(myproc()->pagetable, myproc()->sz, raddr, (char *)&result,
              sizeof(result)) < 0)
    return EFFECT_ERR_INVALID;
  return result.status;
}

uint64
sys_crashat(void)
{
  int n;
  if (myproc()->effect_role == ROLE_AGENT)
    return EFFECT_ERR_PERM;
  argint(0, &n);
  if (n == -1)
    log_set_crash(CRASH_HOOK_NONE, -1);
  else if (n >= 0)
    log_set_crash(CRASH_HOOK_LOG_WRITE_COUNT, n);
  else if (n >= -105 && n <= -102)
    log_set_crash(-n - 100, -1);
  else
    return EFFECT_ERR_INVALID;
  return 0;
}

uint64
sys_proc_role(void)
{
  int role;
  argint(0, &role);
  if (role < 0)
    return myproc()->effect_role;
  if (role > ROLE_AGENT || role < ROLE_NORMAL)
    return EFFECT_ERR_INVALID;
  if (myproc()->effect_role == ROLE_AGENT ||
      role > (int)myproc()->effect_role)
    return EFFECT_ERR_PERM;
  myproc()->effect_role = role;
  return role;
}
