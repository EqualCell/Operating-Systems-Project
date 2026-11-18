// Kernel-facing adversarial checks; assertions inspect actual syscall results.
#include "kernel/types.h"
#include "kernel/stat.h"
#include "kernel/fcntl.h"
#include "kernel/effect.h"
#include "kernel/grant.h"
#include "user/user.h"
static int failures;
static void ck(char *name, int ok) {
  if (!ok) { printf("FAIL %s\n", name); failures++; }
}
static struct grant_request q;
static void setup(uint64 g, uint64 r, int op, char *path, char *text) {
  memset(&q, 0, sizeof(q)); q.grant_id=g; q.request_id=r; q.op=op;
  strcpy(q.path,path); q.n=strlen(text); memmove(q.payload,text,q.n);
}
static void finish(void) {
  printf("GRTEST failures=%d\n",failures); exit(failures != 0);
}
static void auth(void) {
  int fd=open("/log.txt",O_WRONLY), status;
  setup(1,0,EFF_APPEND,"/log.txt","SAFE");
  ck("issue",grant_issue(&q)==0);
  ck("issue retry",grant_issue(&q)==0);
  ck("protected unlink",unlink("/log.txt")<0);
  ck("protected link",link("/log.txt","/alias")<0);
  int parent=getpid();
  if (fork()==0) {
    controller_drop();
    ck("untrusted issuance",grant_issue(&q)==EFF_EPERM);
    ck("untrusted revoke",grant_revoke(1)==EFF_EPERM);
    ck("preopened write",write(fd,"BAD",3)<0);
    ck("truncate",open("/log.txt",O_WRONLY|O_TRUNC)<0);
    ck("ordinary create",open("/evil",O_WRONLY|O_CREATE)<0);
    ck("unlink",unlink("/log.txt")<0);
    ck("hard link",link("/log.txt","/alias")<0);
    ck("mknod",mknod("/raw",0,0)<0);
    ck("mkdir",mkdir("/evil")<0);
    ck("legacy bypass",effect(8,EFF_APPEND,"/log.txt","BAD",3)==EFF_EPERM);
    ck("kill controller",kill(parent)<0);
    ck("crash hook",crashhook(2,1)==EFF_EPERM);
    if (fork()==0) { ck("fork inherits dropped",grant_issue(&q)==EFF_EPERM); finish(); }
    wait(&status); ck("grandchild",status==0);
    if (fork()==0) {
      char *args[]={"grantctl","issue","2","0","append","/log.txt","BAD",0};
      exec("grantctl",args); exit(9);
    }
    wait(&status); ck("exec does not confer controller",status==1);
    q.request_id=9;
    ck("effect allowed",grant_effect(&q)==4 && effect_result()==1);
    ck("exact replay",grant_effect(&q)==4 && effect_result()==2);
    q.payload[0]='X'; ck("payload mismatch",grant_effect(&q)==EFF_EMISMATCH);
    q.payload[0]='S'; q.op=EFF_CREATE; ck("operation mismatch",grant_effect(&q)==EFF_EMISMATCH);
    q.op=EFF_APPEND; strcpy(q.path,"/other"); ck("path mismatch",grant_effect(&q)==EFF_EMISMATCH);
    strcpy(q.path,"/log.txt"); q.request_id=10;
    ck("consumed different request",grant_effect(&q)==GR_CONSUMED_ERR);
    finish();
  }
  wait(&status); ck("untrusted checks",status==0);
  ck("cannot undo completion",grant_revoke(1)==GR_CONSUMED_ERR);
  q.request_id=9; ck("completion survives revoke",grant_effect(&q)==4 && effect_result()==2);
  close(fd);
  finish();
}
static void invalid(void) {
  ck("null request",grant_effect(0)==EFF_EINVAL);
  ck("bad pointer",grant_issue((void *)~0ULL)==EFF_EINVAL);
  setup(0,0,1,"/log.txt","x"); ck("grant zero",grant_issue(&q)==EFF_EINVAL);
  q.grant_id=1; q.n=257; ck("length",grant_issue(&q)==EFF_EINVAL);
  q.n=-1; ck("negative length",grant_issue(&q)==EFF_EINVAL);
  q.n=1; memset(q.path,'a',sizeof(q.path)); ck("unterminated path",grant_issue(&q)==EFF_EINVAL);
  strcpy(q.path,"/../x"); ck("traversal",grant_issue(&q)==EFF_EINVAL);
  strcpy(q.path,"/."); ck("dot",grant_issue(&q)==EFF_EINVAL);
  strcpy(q.path,"/log.txt"); ck("issue valid",grant_issue(&q)==0);
  ck("request zero",grant_effect(&q)==EFF_EINVAL);
  ck("bad status pointer",grant_status(1,0,(void *)~0ULL)==EFF_EINVAL);
  ck("revoke missing",grant_revoke(7)==GR_ENOENT);
  finish();
}
static void stale(void) {
  setup(1,0,1,"/log.txt","APP"); ck("issue",grant_issue(&q)==0);
  int fd=open("/log.txt",O_WRONLY);
  ck("controller legitimate write",write(fd,"NEW",3)==3); close(fd);
  ck("issue retry does not refresh version",grant_issue(&q)==0);
  q.request_id=1; ck("stale ordinary write",grant_effect(&q)==GR_STALE);
  setup(2,0,1,"/log.txt","APP"); ck("issue2",grant_issue(&q)==0);
  fd=open("/log.txt",O_WRONLY|O_TRUNC); ck("controller truncate",fd>=0); close(fd);
  q.request_id=2; ck("stale truncate",grant_effect(&q)==GR_STALE);
  setup(3,0,2,"/new.txt","CREATE"); ck("create approval",grant_issue(&q)==0);
  fd=open("/unrelated",O_CREATE|O_WRONLY); close(fd);
  q.request_id=3; ck("parent namespace stale",grant_effect(&q)==GR_STALE);
  fd=open("/linked",O_CREATE|O_WRONLY); close(fd);
  ck("unprotected link",link("/linked","/linked2")==0);
  setup(4,0,1,"/linked","APP"); ck("aliased inode rejected",grant_issue(&q)==EFF_EINVAL);
  setup(5,0,1,"/log.txt","ONE"); ck("grant5",grant_issue(&q)==0);
  setup(6,0,1,"/log.txt","TWO"); ck("grant6",grant_issue(&q)==0);
  q.request_id=6; ck("effect6",grant_effect(&q)==3);
  setup(5,5,1,"/log.txt","ONE"); ck("stale after effect",grant_effect(&q)==GR_STALE);
  setup(8,0,1,"/log.txt","COPY"); ck("grant8",grant_issue(&q)==0);
  char *top=sbrk(4096);
  if(top!=(char *)-1) {
    char *end=sbrk(0);
    memmove(end-6,"PREFIX",6);
    fd=open("/log.txt",O_WRONLY);
    ck("failed user copy",write(fd,end-6,12)<0); close(fd);
    q.request_id=8; ck("partial copy invalidates approval",grant_effect(&q)==GR_STALE);
  } else ck("copy test allocation",0);
  setup(7,0,1,"/log.txt","STOP"); ck("grant7",grant_issue(&q)==0);
  ck("revoke",grant_revoke(7)==0); ck("revoke retry",grant_revoke(7)==0);
  q.request_id=7; ck("revoked",grant_effect(&q)==GR_REVOKED_ERR);
  finish();
}
static void race(int revoke_race, int different) {
  int p[2], status;
  setup(1,0,1,"/log.txt","RACE"); ck("issue",grant_issue(&q)==0);
  pipe(p);
  for(int i=0;i<8;i++) if(fork()==0) {
    char c; close(p[1]); read(p[0],&c,1); close(p[0]);
    int r;
    if (revoke_race && i==0) r=grant_revoke(1);
    else { q.request_id=different ? i+1 : 7; controller_drop(); r=grant_effect(&q); }
    if (revoke_race && i==0) exit(r==0 || r==GR_CONSUMED_ERR ? 0:1);
    exit(r==4 || (revoke_race && r==GR_REVOKED_ERR) || (different && r==GR_CONSUMED_ERR) ? 0:1);
  }
  close(p[0]); write(p[1],"12345678",8); close(p[1]);
  for(int i=0;i<8;i++){ wait(&status); ck("race child",status==0); }
  struct grant_status st; ck("status",grant_status(1,0,&st)==0);
  ck("race final state",st.state==GR_CONSUMED || (revoke_race && st.state==GR_REVOKED));
  printf("RACE state=%d request=%p\n",st.state,(void *)st.request_id);
  finish();
}
static void capacity(void) {
  for(int i=1;i<=GR_SLOTS;i++){ setup(i,0,1,"/log.txt","X"); ck("issue slot",grant_issue(&q)==0); }
  setup(100,0,2,"/cap.txt","BAD"); ck("full before create",grant_issue(&q)==EFF_EFULL);
  setup(1,1,1,"/log.txt","X"); ck("existing still executes",grant_effect(&q)==1);
  ck("existing still replays",grant_effect(&q)==1 && effect_result()==2);
  finish();
}
static void create_races(int legacy) {
  for(int trial=0;trial<8;trial++) {
    char path[]="/cr0"; path[3]='0'+trial;
    int barrier[2], result[2], status;
    setup(100+trial,0,2,path,"NEW");
    if(!legacy) ck("create race issue",grant_issue(&q)==0);
    pipe(barrier); pipe(result);
    for(int i=0;i<2;i++) if(fork()==0) {
      char c; close(barrier[1]); read(barrier[0],&c,1); close(barrier[0]);
      if(i==0) {
        int r;
        if(legacy) r=effect(100+trial,2,path,"NEW",3);
        else { controller_drop(); q.request_id=200+trial; r=grant_effect(&q); }
        write(result[1],&r,sizeof(r));
      } else { int fd=open(path,O_CREATE|O_WRONLY); close(fd); }
      exit(0);
    }
    close(barrier[0]); write(barrier[1],"12",2); close(barrier[1]);
    close(result[1]); int r=-100; read(result[0],&r,sizeof(r)); close(result[0]);
    wait(&status); wait(&status);
    struct stat st; ck("destination exists",stat(path,&st)==0);
    ck("exclusive CREATE race",(r==3 && st.size==3) ||
       (legacy && (r==EFF_EEXIST || r==EFF_EINVAL) && st.size==0) ||
       (!legacy && r==GR_STALE && st.size==0));
  }
  finish();
}

static void distinct(void) {
  int p[2],status; pipe(p);
  for(int i=0;i<8;i++) {
    char path[]="/dist0"; path[5]='0'+i;
    int fd=open(path,O_CREATE|O_WRONLY); close(fd);
    setup(i+1,0,1,path,"DIST"); ck("distinct issue",grant_issue(&q)==0);
    if(fork()==0) {
      close(p[1]); char c; read(p[0],&c,1); close(p[0]);
      controller_drop(); q.request_id=100+i;
      exit(grant_effect(&q)==4 ? 0:1);
    }
  }
  close(p[0]); write(p[1],"12345678",8); close(p[1]);
  for(int i=0;i<8;i++){wait(&status);ck("distinct concurrent effect",status==0);}
  finish();
}

int main(int argc,char **argv) {
  if(argc<2) exit(2);
  if(!strcmp(argv[1],"overlap")) {
    setup(1,0,1,"/log.txt","DURABLE"); ck("issue",grant_issue(&q)==0);
    int p[2]; pipe(p);
    if(fork()==0) {
      close(p[0]);
      static char bytes[8192]; memset(bytes,'W',sizeof(bytes));
      for(int i=0;i<3000;i++) {
        int fd=open("/traffic",O_CREATE|O_RDWR);
        if(write(fd,bytes,sizeof(bytes))!=sizeof(bytes)) exit(2);
        close(fd);
        if(i==0) { write(p[1],"1",1); close(p[1]); }
      }
      exit(0);
    }
    close(p[1]); char ready; read(p[0],&ready,1); close(p[0]);
    controller_drop(); q.request_id=9;
    ck("durable effect",grant_effect(&q)==7);
    printf("DURABLE-ACK\n"); // harness cuts power immediately at this marker
    pause(100000);
    finish();
  }
  if(!strcmp(argv[1],"create-race")) create_races(0);
  if(!strcmp(argv[1],"legacy-create-race")) create_races(1);
  if(!strcmp(argv[1],"distinct")) distinct();
  if(!strcmp(argv[1],"disksetup")) {
    static char bytes[1024]; memset(bytes,'S',sizeof(bytes));
    int fd=open("/spare",O_CREATE|O_WRONLY);
    ck("spare",write(fd,bytes,sizeof(bytes))==sizeof(bytes)); close(fd);
    ck("align big to indirect boundary",effect(100,1,"/big.txt","12345678",8)==8);
    finish();
  }
  if(!strcmp(argv[1],"auth")) auth();
  if(!strcmp(argv[1],"invalid")) invalid();
  if(!strcmp(argv[1],"stale")) stale();
  if(!strcmp(argv[1],"same")) race(0,0);
  if(!strcmp(argv[1],"different")) race(0,1);
  if(!strcmp(argv[1],"revoke")) race(1,0);
  if(!strcmp(argv[1],"capacity")) capacity();
  exit(2);
}
