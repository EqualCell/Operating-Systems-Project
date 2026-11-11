// effstress -- many callers, for the "hidden test" scenarios.
//
//   effstress same N KEY /path TEXT      N processes, SAME key, SAME payload
//                                        (expect: exactly ONE append reaches the file)
//   effstress diff N KEY /path TEXT      N processes, SAME key, DIFFERENT payloads
//                                        (expect: one wins, the others EMISMATCH)
//   effstress fill N BASEKEY /path TEXT  one process, N DISTINCT keys
//                                        BASEKEY, BASEKEY+1, ... (fills the table)
//   effstress many N BASEKEY /path TEXT  N processes, N DISTINCT keys in parallel
//                                        (expect: N appends, no loss, no duplicate)
//
// Output: a single summary line, e.g.
//   STRESS-SUMMARY mode=same n=3 ok=3 EINVAL=0 ENOENT=0 EFULL=0 EMISMATCH=0 EIO=0 EEXIST=0
// (for "same", all N callers get ok: one EXECUTED and N-1 REPLAYED; the
//  executed/replayed split is visible with effstat.)
#include "kernel/types.h"
#include "kernel/effect.h"
#include "user/user.h"

static uint64
parse(char *s)
{
  uint64 v = 0;
  int base = 10;
  if (s[0] == '0' && s[1] == 'x') {
    base = 16;
    s += 2;
  }
  for (; *s; s++) {
    int d = (*s >= 'a') ? *s - 'a' + 10 : *s - '0';
    v = v * base + d;
  }
  return v;
}

static int codes[8]; // codes[0] = ok, codes[k] = count of error -k

static void
summary(char *mode, int n)
{
  printf("STRESS-SUMMARY mode=%s n=%d ok=%d EINVAL=%d ENOENT=%d EFULL=%d "
         "EMISMATCH=%d EIO=%d EEXIST=%d\n",
         mode, n, codes[0], codes[1], codes[2], codes[3], codes[4], codes[5],
         codes[6]);
}

int
main(int argc, char *argv[])
{
  if (argc != 6) {
    fprintf(2, "usage: effstress same|diff|fill N KEY /path TEXT\n");
    exit(2);
  }
  int n = atoi(argv[2]);
  uint64 key = parse(argv[3]);
  char *path = argv[4];
  char *text = argv[5];

  if (strcmp(argv[1], "fill") == 0) {
    for (int i = 0; i < n; i++) {
      int rc = effect(key + i, EFF_APPEND, path, text, strlen(text));
      codes[rc >= 0 ? 0 : -rc]++;
    }
    summary("fill", n);
    exit(0);
  }

  int diff = strcmp(argv[1], "diff") == 0;
  int many = strcmp(argv[1], "many") == 0;
  for (int i = 0; i < n; i++) {
    if (fork() == 0) {
      char payload[64];
      strcpy(payload, text);
      if (diff) { // make the payload of child i differ from the others
        int l = strlen(payload);
        payload[l] = '0' + (i % 10);
        payload[l + 1] = 0;
      }
      int rc = effect(many ? key + i : key, EFF_APPEND, path, payload,
                      strlen(payload));
      exit(rc >= 0 ? 0 : -rc); // child reports its result code via exit status
    }
  }
  for (int i = 0; i < n; i++) {
    int st = 0;
    wait(&st);
    if (st >= 0 && st < 8)
      codes[st]++;
  }
  summary(argv[1], n);
  exit(0);
}
