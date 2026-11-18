// Trusted console/controller client. Executing this binary never adds authority.
#include "kernel/types.h"
#include "kernel/effect.h"
#include "kernel/grant.h"
#include "user/user.h"

static uint64
key(char *s)
{
  uint64 n = 0;
  int count = 0;
  if (s[0] == '0' && s[1] == 'x') s += 2;
  for (; *s; s++) {
    int v = *s >= '0' && *s <= '9' ? *s - '0' :
            *s >= 'a' && *s <= 'f' ? *s - 'a' + 10 : -1;
    if (v < 0 || ++count > 16) return 0;
    n = (n << 4) | v;
  }
  return n;
}

int
main(int argc, char **argv)
{
  int i = 1;
  if (argc > 1 && !strcmp(argv[i], "drop")) { controller_drop(); i++; }
  if (argc > i + 1 && !strcmp(argv[i], "-s")) {
    if (crashhook(atoi(argv[i+1]), 1) < 0) exit(2);
    i += 2;
  }
  if (argc <= i + 1) {
    fprintf(2, "usage: grantctl [drop] [-s STAGE] issue|effect G R append|create /name TEXT\n"
               "       grantctl [drop] revoke G | status G R\n");
    exit(2);
  }
  char *cmd = argv[i++];
  uint64 id = key(argv[i++]);
  int rc = -1;
  struct grant_request q;
  memset(&q, 0, sizeof(q));
  if (!strcmp(cmd, "revoke") && argc == i) rc = grant_revoke(id);
  else if (!strcmp(cmd, "status") && argc == i+1) {
    struct grant_status st;
    rc = grant_status(id, key(argv[i]), &st);
    if (!rc) printf("STATE state=%d result=%d request=%p expected=%p current=%p\n",
                   st.state, st.result, (void *)st.request_id,
                   (void *)st.expected_version, (void *)st.current_version);
  } else if ((!strcmp(cmd, "issue") || !strcmp(cmd, "issuehex") || !strcmp(cmd, "effect")) && argc == i+4) {
    q.grant_id = id;
    q.request_id = key(argv[i++]);
    q.op = !strcmp(argv[i], "append") ? EFF_APPEND : !strcmp(argv[i], "create") ? EFF_CREATE : 0;
    i++;
    if (strlen(argv[i]) >= sizeof(q.path) || strlen(argv[i+1]) > sizeof(q.payload)) exit(2);
    strcpy(q.path, argv[i++]);
    q.n = strlen(argv[i]);
    memmove(q.payload, argv[i], q.n);
    if (!strcmp(cmd, "issuehex")) {
      if (q.n % 2) exit(2);
      q.n /= 2;
      for (int j = 0; j < q.n; j++) {
        char pair[3] = {argv[i][j*2], argv[i][j*2+1], 0};
        // payload may contain spaces but not NUL; exact bytes enter kernel.
        q.payload[j] = key(pair);
      }
    }
    rc = strcmp(cmd, "effect") ? grant_issue(&q) : grant_effect(&q);
  }
  char *outcome = rc < 0 ? "ERROR" : effect_result() == 2 ? "REPLAYED" : "EXECUTED";
  printf("GRANT action=%s id=%p rc=%d outcome=%s\n", cmd, (void *)id, rc, outcome);
  exit(rc < 0);
}
