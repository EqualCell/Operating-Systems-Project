// Intentionally unsafe comparison experiments; excluded from normal builds.
#include "kernel/types.h"
#include "kernel/fcntl.h"
#include "kernel/effect.h"
#include "kernel/grant.h"
#include "user/user.h"
#ifdef UNSAFE_COMPARISONS
static void ordinary(char *path) {
  int fd=open(path,O_CREATE|O_RDWR);
  char c;
  while(read(fd,&c,1)==1) ;
  write(fd,"X",1); close(fd);
}
int main(void) {
  ordinary("/ordinary"); ordinary("/ordinary"); // lost reply + blind retry
  effect(1, EFF_CREATE,"/dedup","",0);
  effect(2,EFF_APPEND,"/dedup","X",1);
  effect(2,EFF_APPEND,"/dedup","X",1);
  int fd=open("/nonatomic",O_CREATE|O_RDWR); close(fd);
  struct grant_request q;
  memset(&q,0,sizeof(q)); q.grant_id=1; q.op=1; q.n=1;
  strcpy(q.path,"/nonatomic"); q.payload[0]='X';
  grant_issue(&q);
  struct grant_status st;
  grant_status(1,0,&st); // WRONG: check separated from effect
  grant_revoke(1);
  if(st.state==GR_ACTIVE) ordinary("/nonatomic");
  fd=open("/atomic",O_CREATE|O_RDWR); close(fd);
  strcpy(q.path,"/atomic"); q.grant_id=2;
  grant_issue(&q); q.request_id=3;
  controller_drop();
  int a=grant_effect(&q), b=grant_effect(&q);
  printf("COMPARE atomic=%d retry=%d outcome=%d\n",a,b,effect_result());
  exit(a!=1 || b!=1);
}
#else
int main(void) { printf("unsafe comparisons disabled\n"); exit(1); }
#endif
