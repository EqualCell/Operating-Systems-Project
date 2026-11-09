#include "kernel/types.h"
#include "kernel/stat.h"
#include "kernel/fcntl.h"
#include "kernel/effect.h"
#include "user.h"

static uint64
hash_args(uint32 op, const char *path, const char *payload, uint32 n)
{
  uint64 h = 1469598103934665603ULL;
  uint i;
  for (i = 0; i < 4; i++) {
    h ^= (uint8)(op >> (i * 8));
    h *= 1099511628211ULL;
  }
  for (i = 0; path[i]; i++) {
    h ^= (uint8)path[i];
    h *= 1099511628211ULL;
  }
  h ^= 0xff;
  h *= 1099511628211ULL;
  for (i = 0; i < n; i++) {
    h ^= (uint8)payload[i];
    h *= 1099511628211ULL;
  }
  for (i = 0; i < 4; i++) {
    h ^= (uint8)(n >> (i * 8));
    h *= 1099511628211ULL;
  }
  return h;
}

int
main(void)
{
  char payload[] = "effect\n";
  struct grant_spec grant;
  struct effect_checked_req req;
  int r;

  unlink("effect-p1");
  r = effect(0x100000000ULL, EFFECT_OP_CREATE, "effect-p1", 0, 0);
  if (r != 0)
    printf("create failed: %d\n", r);
  r = effect(0x100000000ULL, EFFECT_OP_CREATE, "effect-p1", 0, 0);
  if (r != EFFECT_OK_CACHED)
    printf("retry failed: %d\n", r);
  grant.abi_version = EFFECT_ABI_VERSION;
  grant.allowed_op = EFFECT_OP_APPEND;
  grant.max_payload_len = sizeof(payload) - 1;
  grant.flags = 0;
  memmove(grant.path, "effect-p1", 10);
  if (grant_create(&grant) == 0) {
    memset(&req, 0, sizeof(req));
    req.abi_version = EFFECT_ABI_VERSION;
    req.op = EFFECT_OP_APPEND;
    req.grant_id = grant.out_grant_id;
    req.req_id = 1;
    req.payload_len = sizeof(payload) - 1;
    memmove(req.path, "effect-p1", 10);
    memmove(req.payload, payload, sizeof(payload) - 1);
    req.arg_hash = hash_args(req.op, req.path, payload, req.payload_len);
    r = effect_checked(&req);
    printf("checked: %d bytes=%d\n", r, req.out_bytes);
  }
  exit(0);
}
