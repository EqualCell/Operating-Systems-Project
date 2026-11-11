// effstat -- print the kernel's effect counters on one line (key=value pairs).
#include "kernel/types.h"
#include "kernel/effect.h"
#include "user/user.h"

int
main(void)
{
  struct effstats s;
  if (effstat(&s) < 0) {
    fprintf(2, "effstat: failed\n");
    exit(1);
  }
  printf("EFFSTAT executed=%d replayed=%d mismatched=%d table_full=%d errors=%d "
         "table_used=%d table_slots=%d logwrites=%d diskwrites=%d "
         "last_logged=%d last_logwrites=%d last_diskwrites=%d\n",
         (int)s.executed, (int)s.replayed, (int)s.mismatched,
         (int)s.table_full, (int)s.errors, (int)s.table_used,
         (int)s.table_slots, (int)s.logwrites, (int)s.diskwrites,
         (int)s.last_logged, (int)s.last_logwrites, (int)s.last_diskwrites);
  exit(0);
}
