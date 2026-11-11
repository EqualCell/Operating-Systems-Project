// effectctl -- command-line front end for the effect() system call.
//
//   effectctl [-c N] [-s STAGE:N] append KEY /path TEXT
//   effectctl [-c N] [-s STAGE:N] create KEY /path TEXT
//
//   KEY   64-bit number, decimal or 0x-hex       (never truncated to 32 bits)
//   -c N  test builds only: crashat(N)  = panic at the N-th log_write
//   -s S:N test builds only: crashhook(S,N) = panic at commit stage S (hit N)
//
// Prints ONE machine-readable line (the test harness and the agent bridge
// parse it):
//   EFFECT op=APPEND key=0x0000000100000001 rc=5 outcome=EXECUTED
// (%p prints all 64 bits of the key; xv6 printf has no width flags)
// outcome is EXECUTED (new key), REPLAYED (known key), or ERROR (rc<0).
// Exit status is 0 on success, 1 on error.

#include "kernel/types.h"
#include "kernel/effect.h"
#include "user/user.h"

// xv6 atoi() is 32-bit; parse a full 64-bit key ourselves.
static int
parsekey(char *s, uint64 *out)
{
  uint64 v = 0;
  int base = 10;
  if (s[0] == '0' && (s[1] == 'x' || s[1] == 'X')) {
    base = 16;
    s += 2;
  }
  if (*s == 0)
    return -1;
  for (; *s; s++) {
    int d;
    if (*s >= '0' && *s <= '9')
      d = *s - '0';
    else if (base == 16 && *s >= 'a' && *s <= 'f')
      d = *s - 'a' + 10;
    else if (base == 16 && *s >= 'A' && *s <= 'F')
      d = *s - 'A' + 10;
    else
      return -1;
    v = v * base + d;
  }
  *out = v;
  return 0;
}

static void
usage(void)
{
  fprintf(2, "usage: effectctl [-c N] [-s STAGE:N] append|create KEY /path TEXT\n");
  exit(2);
}

int
main(int argc, char *argv[])
{
  int i = 1;
  int crash_n = 0, stage = 0, stage_n = 0;

  for (; i < argc && argv[i][0] == '-'; i++) {
    if (strcmp(argv[i], "-c") == 0 && i + 1 < argc) {
      crash_n = atoi(argv[++i]);
    } else if (strcmp(argv[i], "-s") == 0 && i + 1 < argc) {
      char *a = argv[++i];
      stage = atoi(a);
      while (*a && *a != ':')
        a++;
      stage_n = (*a == ':') ? atoi(a + 1) : 1;
    } else {
      usage();
    }
  }
  if (argc - i != 4)
    usage();

  int op;
  char *opname;
  if (strcmp(argv[i], "append") == 0) {
    op = EFF_APPEND;
    opname = "APPEND";
  } else if (strcmp(argv[i], "create") == 0) {
    op = EFF_CREATE;
    opname = "CREATE";
  } else {
    usage();
    return 2;
  }
  uint64 key;
  if (parsekey(argv[i + 1], &key) < 0) {
    fprintf(2, "effectctl: bad key\n");
    exit(2);
  }
  char *path = argv[i + 2];
  char *text = argv[i + 3];

  if (crash_n && crashat(crash_n) < 0) {
    fprintf(2, "effectctl: crashat unavailable (not a test build)\n");
    exit(2);
  }
  if (stage && crashhook(stage, stage_n) < 0) {
    fprintf(2, "effectctl: crashhook unavailable (not a test build)\n");
    exit(2);
  }

  struct effstats before, after;
  effstat(&before);
  int rc = effect(key, op, path, text, strlen(text));
  effstat(&after);

  char *outcome = "ERROR";
  if (rc >= 0)
    outcome = (after.executed > before.executed) ? "EXECUTED" : "REPLAYED";
  printf("EFFECT op=%s key=%p rc=%d outcome=%s\n", opname, (void *)key, rc, outcome);
  exit(rc >= 0 ? 0 : 1);
}
