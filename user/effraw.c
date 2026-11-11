// effraw -- hostile / boundary calls to effect(), to prove the kernel validates
// everything and never trusts a user pointer.   Output: RAW case=<name> rc=<rc>
//
//   effraw len    KEY OP PATH N    payload of N bytes ('x'), N may exceed the limit
//   effraw badptr KEY OP PATH      buffer pointer = unmapped/kernel-range address
//   effraw endptr  KEY OP PATH     buffer pointer = first byte AFTER the process memory
//   effraw straddle KEY OP PATH    8-byte buffer starting 4 bytes before the end of memory
//   effraw badpath KEY OP          path pointer = unmapped address
//   effraw negn   KEY OP PATH      n = -5
//   effraw plain  KEY OP PATH      ordinary 3-byte payload "abc" (any OP number)
#include "kernel/types.h"
#include "kernel/effect.h"
#include "user/user.h"

static char big[2048];

static uint64
parse(char *s)
{
  uint64 v = 0;
  int base = 10;
  if (s[0] == '0' && s[1] == 'x') { base = 16; s += 2; }
  for (; *s; s++) {
    int d = (*s >= 'a') ? *s - 'a' + 10 : *s - '0';
    v = v * base + d;
  }
  return v;
}

int
main(int argc, char *argv[])
{
  if (argc < 4) {
    fprintf(2, "usage: effraw mode KEY OP [PATH [N]]\n");
    exit(2);
  }
  char *mode = argv[1];
  uint64 key = parse(argv[2]);
  int op = atoi(argv[3]);
  char *path = argc > 4 ? argv[4] : "/log.txt";
  int rc = -99;

  memset(big, 'x', sizeof(big));
  if (strcmp(mode, "len") == 0 && argc == 6)
    rc = effect(key, op, path, big, atoi(argv[5]));
  else if (strcmp(mode, "badptr") == 0)
    rc = effect(key, op, path, (void *)0x3fffffe000UL, 8); // above user memory
  else if (strcmp(mode, "endptr") == 0)
    rc = effect(key, op, path, sbrk(0), 8);
  else if (strcmp(mode, "straddle") == 0)
    rc = effect(key, op, path, (char *)sbrk(0) - 4, 8);
  else if (strcmp(mode, "badpath") == 0)
    rc = effect(key, op, (char *)0x3fffffe000UL, "abc", 3);
  else if (strcmp(mode, "negn") == 0)
    rc = effect(key, op, path, "abc", -5);
  else if (strcmp(mode, "plain") == 0)
    rc = effect(key, op, path, "abc", 3);
  else {
    fprintf(2, "effraw: bad mode\n");
    exit(2);
  }
  printf("RAW case=%s rc=%d\n", mode, rc);
  exit(0);
}
