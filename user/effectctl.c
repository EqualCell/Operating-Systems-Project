/*
 * effectctl — dedicated guest utility for the agent bridge.
 *
 * This is the ONLY program the host agent ever executes inside xv6.
 * It accepts a fixed set of subcommands, each mapped to one syscall
 * or a small sequence of syscalls.  It never interprets arbitrary
 * input as shell commands.
 *
 * Protocol:
 *   effectctl <subcommand> <correlation_id> [args...]
 *
 * Output:
 *   RESPONSE:<correlation_id>:<result>
 *   ERROR:<correlation_id>:<error_description>
 *
 * Subcommands:
 *   ready    <corr_id>               — echo ready (health check)
 *   ls       <corr_id> [path]        — list files (space-separated)
 *   cat      <corr_id> <path>        — read file contents
 *   append   <corr_id> <path> <data> [grant_id req_id]
 *   status   <corr_id> <key> [grant_id]
 *   grantstatus <corr_id> <grant_id>
 */

#include "kernel/types.h"
#include "kernel/stat.h"
#include "kernel/fcntl.h"
#include "kernel/fs.h"
#include "kernel/effect.h"
#include "user/user.h"

/* Protocol output helpers */
static void
respond(const char *corr_id, const char *payload)
{
  printf("RESPONSE:%s:%s\n", corr_id, payload);
}

static void
respond_err(const char *corr_id, const char *msg)
{
  printf("ERROR:%s:%s\n", corr_id, msg);
}

/* ------------------------------------------------------------------ */
/* Subcommand: ls                                                     */
/* ------------------------------------------------------------------ */

static void
cmd_ls(const char *corr_id, const char *path)
{
  int fd;
  struct dirent de;
  struct stat st;
  char buf[512];
  int off = 0;
  int first = 1;

  fd = open(path, O_RDONLY);
  if (fd < 0) {
    respond_err(corr_id, "cannot open directory");
    return;
  }
  if (fstat(fd, &st) < 0 || st.type != T_DIR) {
    respond_err(corr_id, "not a directory");
    close(fd);
    return;
  }

  while (read(fd, &de, sizeof(de)) == sizeof(de)) {
    if (de.inum == 0)
      continue;
    if (!first && off < (int)sizeof(buf) - 1)
      buf[off++] = ' ';
    first = 0;
    int i;
    for (i = 0; i < DIRSIZ && de.name[i] && off < (int)sizeof(buf) - 1; i++)
      buf[off++] = de.name[i];
  }
  buf[off] = 0;
  close(fd);
  respond(corr_id, buf);
}

/* ------------------------------------------------------------------ */
/* Subcommand: cat                                                    */
/* ------------------------------------------------------------------ */

static void
cmd_cat(const char *corr_id, const char *path)
{
  int fd, n;
  char buf[512];

  fd = open(path, O_RDONLY);
  if (fd < 0) {
    respond_err(corr_id, "cannot open file");
    return;
  }

  /* Read first chunk for the bridge */
  n = read(fd, buf, sizeof(buf) - 1);
  if (n < 0) {
    respond_err(corr_id, "read error");
    close(fd);
    return;
  }
  buf[n] = 0;
  close(fd);
  respond(corr_id, buf);
}

/* ------------------------------------------------------------------ */
/* Subcommand: append (via effect ABI)                                */
/* ------------------------------------------------------------------ */

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

static uint64
corr_id_to_key(const char *s)
{
  uint64 val = 0;
  int i;
  for (i = 0; s[i] && i < 16; i++) {
    char c = s[i];
    int digit;
    if (c >= '0' && c <= '9')
      digit = c - '0';
    else if (c >= 'a' && c <= 'f')
      digit = c - 'a' + 10;
    else if (c >= 'A' && c <= 'F')
      digit = c - 'A' + 10;
    else
      break;
    val = (val << 4) | digit;
  }
  if (val == 0)
    val = 1;
  return val;
}

static void
cmd_append(const char *corr_id, const char *path,
           const char *data, int has_grant, uint64 grant_id, uint64 req_id)
{
  uint32 len = strlen(data);
  int r;

  if (len > EFFECT_MAX_PAYLOAD) {
    respond_err(corr_id, "payload too large");
    return;
  }

  if (has_grant) {
    /* Use checked effect with grant */
    struct effect_checked_req req;
    memset(&req, 0, sizeof(req));
    req.abi_version = EFFECT_ABI_VERSION;
    req.op = EFFECT_OP_APPEND;
    req.grant_id = grant_id;
    req.req_id = req_id;
    req.payload_len = len;
    memmove(req.path, path, strlen(path) + 1);
    memmove(req.payload, data, len);
    req.arg_hash = hash_args(req.op, req.path, data, len);

    r = effect_checked(&req);
    if (r == EFFECT_OK_COMMITTED || r == EFFECT_OK_CACHED) {
      printf("RESPONSE:%s:ok bytes=%d\n", corr_id, req.out_bytes);
    } else {
      respond_err(corr_id, r == EFFECT_ERR_REVOKED ? "revoked" :
                           r == EFFECT_ERR_CONSUMED ? "consumed" :
                           r == EFFECT_ERR_STALE ? "stale" :
                           r == EFFECT_ERR_ARG_MISMATCH ? "arg_mismatch" :
                           r == EFFECT_ERR_PERM ? "permission_denied" :
                           r == EFFECT_ERR_NOENT ? "not_found" :
                           "effect_error");
    }
  } else {
    /* Use base effect (keyed by correlation ID) */
    uint64 key = corr_id_to_key(corr_id);
    r = effect(key, EFFECT_OP_APPEND, path, data, len);
    if (r >= 0) {
      printf("RESPONSE:%s:ok bytes=%d\n", corr_id, r);
    } else {
      respond_err(corr_id, r == EFFECT_ERR_INVALID ? "invalid" :
                           r == EFFECT_ERR_TABLE_FULL ? "table_full" :
                           r == EFFECT_ERR_NOENT ? "not_found" :
                           "effect_error");
    }
  }
}

/* ------------------------------------------------------------------ */
/* Subcommand: status                                                 */
/* ------------------------------------------------------------------ */

static void
cmd_status(const char *corr_id, uint64 key, int has_grant, uint64 grant_id)
{
  struct effect_status_query q;
  struct effect_status_result res;
  int r;

  memset(&q, 0, sizeof(q));
  q.abi_version = EFFECT_ABI_VERSION;
  q.key_or_req_id = key;
  if (has_grant) {
    q.is_extended = 1;
    q.grant_id = grant_id;
  }

  r = effect_status(&q, &res);
  if (r == EFFECT_OK_COMMITTED) {
    printf("RESPONSE:%s:committed bytes=%d version=%llu\n",
           corr_id, res.bytes_written, res.committed_version);
  } else if (r == EFFECT_ERR_NOT_RECORDED) {
    respond(corr_id, "not_recorded");
  } else if (r == EFFECT_ERR_ARG_MISMATCH) {
    respond(corr_id, "arg_mismatch");
  } else {
    respond_err(corr_id, "status_error");
  }
}

/* ------------------------------------------------------------------ */
/* Subcommand: grantstatus                                            */
/* ------------------------------------------------------------------ */

static void
cmd_grantstatus(const char *corr_id, uint64 grant_id)
{
  struct effect_status_query q;
  struct effect_status_result res;
  int r;

  memset(&q, 0, sizeof(q));
  q.abi_version = EFFECT_ABI_VERSION;
  q.is_extended = 1;
  q.grant_id = grant_id;
  q.key_or_req_id = 0;

  r = effect_status(&q, &res);
  if (r == EFFECT_OK_COMMITTED) {
    respond(corr_id, res.grant_state == GRANT_STATE_ACTIVE ? "active" :
                     res.grant_state == GRANT_STATE_CONSUMED ? "consumed" :
                     res.grant_state == GRANT_STATE_REVOKED ? "revoked" :
                     "unknown_state");
  } else {
    respond(corr_id, "not_found");
  }
}

/* ------------------------------------------------------------------ */
/* Argument parsing and validation                                    */
/* ------------------------------------------------------------------ */

static uint64
atou64(const char *s)
{
  uint64 val = 0;
  if (s[0] == '0' && (s[1] == 'x' || s[1] == 'X')) {
    s += 2;
    while ((*s >= '0' && *s <= '9') ||
           (*s >= 'a' && *s <= 'f') ||
           (*s >= 'A' && *s <= 'F')) {
      if (*s >= '0' && *s <= '9')
        val = val * 16 + (*s - '0');
      else if (*s >= 'a' && *s <= 'f')
        val = val * 16 + (*s - 'a' + 10);
      else
        val = val * 16 + (*s - 'A' + 10);
      s++;
    }
    return val;
  }
  while (*s >= '0' && *s <= '9') {
    val = val * 10 + (*s - '0');
    s++;
  }
  return val;
}

static int
valid_corr_id(const char *s)
{
  int i;
  for (i = 0; s[i]; i++) {
    char c = s[i];
    if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F')))
      return 0;
  }
  return i >= 1 && i <= 32;
}

static int
valid_path(const char *s)
{
  int i;
  if (s[0] == 0)
    return 0;
  for (i = 0; s[i]; i++) {
    if (i >= 127)
      return 0;
  }
  /* Check for '..' components */
  for (i = 0; s[i]; i++) {
    if (s[i] == '.' && s[i+1] == '.') {
      if (i == 0 || s[i-1] == '/') {
        if (s[i+2] == 0 || s[i+2] == '/')
          return 0;
      }
    }
  }
  return 1;
}

/* ------------------------------------------------------------------ */
/* Main dispatch                                                      */
/* ------------------------------------------------------------------ */

int
main(int argc, char *argv[])
{
  if (argc < 3) {
    printf("ERROR:0:usage: effectctl <cmd> <corr_id> [args...]\n");
    exit(1);
  }

  const char *cmd = argv[1];
  const char *corr_id = argv[2];

  /* Validate correlation ID first — reject all malformed input */
  if (!valid_corr_id(corr_id)) {
    printf("ERROR:0:invalid correlation_id\n");
    exit(1);
  }

  if (strcmp(cmd, "ready") == 0) {
    respond(corr_id, "ready");

  } else if (strcmp(cmd, "ls") == 0) {
    const char *path = argc > 3 ? argv[3] : ".";
    if (!valid_path(path)) {
      respond_err(corr_id, "invalid_path");
      exit(1);
    }
    cmd_ls(corr_id, path);

  } else if (strcmp(cmd, "cat") == 0) {
    if (argc < 4) {
      respond_err(corr_id, "missing path argument");
      exit(1);
    }
    if (!valid_path(argv[3])) {
      respond_err(corr_id, "invalid_path");
      exit(1);
    }
    cmd_cat(corr_id, argv[3]);

  } else if (strcmp(cmd, "append") == 0) {
    if (argc < 5) {
      respond_err(corr_id, "usage: append <path> <data> [grant_id req_id]");
      exit(1);
    }
    if (!valid_path(argv[3])) {
      respond_err(corr_id, "invalid_path");
      exit(1);
    }
    if (argc >= 7) {
      cmd_append(corr_id, argv[3], argv[4], 1, atou64(argv[5]), atou64(argv[6]));
    } else {
      cmd_append(corr_id, argv[3], argv[4], 0, 0, 0);
    }

  } else if (strcmp(cmd, "status") == 0) {
    if (argc < 4) {
      respond_err(corr_id, "usage: status <key> [grant_id]");
      exit(1);
    }
    if (argc >= 5) {
      cmd_status(corr_id, atou64(argv[3]), 1, atou64(argv[4]));
    } else {
      cmd_status(corr_id, atou64(argv[3]), 0, 0);
    }

  } else if (strcmp(cmd, "grantstatus") == 0) {
    if (argc < 4) {
      respond_err(corr_id, "usage: grantstatus <grant_id>");
      exit(1);
    }
    cmd_grantstatus(corr_id, atou64(argv[3]));

  } else {
    respond_err(corr_id, "unknown subcommand");
  }

  exit(0);
}

