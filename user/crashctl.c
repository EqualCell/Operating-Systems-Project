// crashctl -- arm / disarm the kernel crash hooks (TEST BUILDS ONLY).
//   crashctl at N          panic at the N-th log_write           (0 = disarm)
//   crashctl stage S N     panic when commit() reaches stage S, hit N
//                          S: 1=BEFORE_HEADER 2=AFTER_HEADER 3=DURING_INSTALL
//                             4=AFTER_INSTALL                    (S=0 disarm)
// The agent bridge never runs this program; only the test harness does.
#include "kernel/types.h"
#include "user/user.h"

int
main(int argc, char *argv[])
{
  int rc = -1;
  if (argc == 3 && strcmp(argv[1], "at") == 0)
    rc = crashat(atoi(argv[2]));
  else if (argc == 4 && strcmp(argv[1], "stage") == 0)
    rc = crashhook(atoi(argv[2]), atoi(argv[3]));
  else if (argc == 3 && strcmp(argv[1], "stage") == 0)
    rc = crashhook(atoi(argv[2]), 1);
  else {
    fprintf(2, "usage: crashctl at N | crashctl stage S [N]\n");
    exit(2);
  }
  printf("CRASHCTL rc=%d\n", rc);
  exit(rc < 0);
}
