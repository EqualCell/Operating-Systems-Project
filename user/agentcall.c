// agentcall -- the ONLY entry point the host agent's bridge uses inside xv6.
//
//   agentcall ID list
//   agentcall ID read   /path
//   agentcall ID append KEYHEX /path HEXPAYLOAD
//   agentcall ID create KEYHEX /path HEXPAYLOAD
//
// Why it exists (see docs/bridge.md):
//   * FRAMING   every reply is   @@BEGIN ID  ...body...  @@END ID rc=N status=S
//               so the host knows exactly where a reply starts and stops, even
//               though the xv6 console also echoes what we type.
//   * ALLOWLIST only the four commands above exist.  Anything else (e.g. "rm")
//               is refused HERE, in the guest, as a second line of defence in
//               addition to the Python validator.  It is still NOT the final
//               security boundary: that would be kernel enforcement (taint).
//   * NO SHELL  payload arrives hex-encoded, so no quoting or shell
//               metacharacters can ever matter (xv6 sh has no quoting).
//   * SAFE BODY every line of file content is printed with a "| " prefix, so a
//               hostile file containing "@@END ..." cannot forge a frame marker.
//
// This program calls the real effect() syscall; nothing is simulated.

#include "kernel/types.h"
#include "kernel/stat.h"
#include "kernel/fcntl.h"
#include "kernel/fs.h"
#include "kernel/effect.h"
#include "user/user.h"

#define MAXHEX 64 // 32 payload bytes: keeps the console line (128 B) short

static char *id = "0";

static void
finish(int rc, char *status)
{
  printf("@@END %s rc=%d status=%s\n", id, rc, status);
  exit(rc < 0 ? 1 : 0);
}

static int
okpath(char *p)
{
  int n = strlen(p);
  if (n < 2 || n > 32 || p[0] != '/')
    return 0;
  for (int i = 0; i < n; i++) {
    char c = p[i];
    int good = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
               (c >= '0' && c <= '9') || c == '.' || c == '_' || c == '-' ||
               (c == '/' && i == 0);
    if (!good)
      return 0; // only a single leading '/': no subdirs, no "..", no tricks
  }
  return 1;
}

static int
hexval(char c)
{
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}

// 1..16 hex digits, non-zero -> 64-bit key
static int
parsekey(char *s, uint64 *out)
{
  int n = strlen(s);
  uint64 v = 0;
  if (n < 1 || n > 16)
    return -1;
  for (int i = 0; i < n; i++) {
    int d = hexval(s[i]);
    if (d < 0)
      return -1;
    v = (v << 4) | d;
  }
  if (v == 0)
    return -1;
  *out = v;
  return 0;
}

// hex string -> printable ASCII bytes. returns length or -1.
static int
decode(char *hex, char *out)
{
  int n = strlen(hex);
  if (n == 0 || n % 2 || n > MAXHEX)
    return -1;
  for (int i = 0; i < n; i += 2) {
    int a = hexval(hex[i]), b = hexval(hex[i + 1]);
    if (a < 0 || b < 0)
      return -1;
    int c = a * 16 + b;
    if (c < 0x20 || c > 0x7e)
      return -1; // printable ASCII only
    out[i / 2] = c;
  }
  out[n / 2] = 0;
  return n / 2;
}

static void
do_list(void)
{
  struct dirent de;
  struct stat st;
  char path[DIRSIZ + 2];
  int fd = open("/", O_RDONLY);
  if (fd < 0)
    finish(-1, "ERR:open-root");
  while (read(fd, &de, sizeof(de)) == sizeof(de)) {
    if (de.inum == 0)
      continue;
    path[0] = '/';
    memmove(path + 1, de.name, DIRSIZ);
    path[DIRSIZ + 1] = 0;
    if (stat(path, &st) < 0)
      continue;
    printf("| %s %d %d\n", de.name, st.type, (int)st.size);
  }
  close(fd);
  finish(0, "OK");
}

static void
do_read(char *path)
{
  char buf[128];
  int n, total = 0, bol = 1;
  int fd = open(path, O_RDONLY);
  if (fd < 0)
    finish(-1, "ERR:not-found");
  while ((n = read(fd, buf, sizeof(buf))) > 0 && total < 1024) {
    for (int i = 0; i < n && total < 1024; i++, total++) {
      char c = buf[i];
      if (bol) {
        printf("| ");
        bol = 0;
      }
      if (c == '\n') {
        printf("\n");
        bol = 1;
      } else if (c >= 0x20 && c <= 0x7e) {
        printf("%c", c);
      } else {
        printf("?");
      }
    }
  }
  if (!bol)
    printf("\n");
  close(fd);
  finish(total, total >= 1024 ? "OK:truncated" : "OK");
}

static void
do_effect(int op, char *keyhex, char *path, char *hex)
{
  uint64 key;
  char payload[MAXHEX / 2 + 1];
  int n;
  if (parsekey(keyhex, &key) < 0)
    finish(-1, "ERR:bad-key");
  if (!okpath(path))
    finish(-1, "ERR:bad-path");
  if ((n = decode(hex, payload)) < 0)
    finish(-1, "ERR:bad-payload");

  struct effstats b, a;
  effstat(&b);
  int rc = effect(key, op, path, payload, n);
  effstat(&a);
  char *outcome = rc < 0 ? "ERROR" : (a.executed > b.executed ? "EXECUTED" : "REPLAYED");
  printf("| EFFECT op=%s key=%p rc=%d outcome=%s\n", op == EFF_APPEND ? "APPEND" : "CREATE",
         (void *)key, rc, outcome);
  finish(rc, rc < 0 ? "ERR:kernel" : outcome);
}

int
main(int argc, char *argv[])
{
  if (argc < 3 || strlen(argv[1]) > 9) {
    printf("@@BEGIN 0\n");
    id = "0";
    finish(-1, "ERR:usage");
  }
  id = argv[1];
  printf("@@BEGIN %s\n", id);
  char *cmd = argv[2];

  if (strcmp(cmd, "list") == 0 && argc == 3)
    do_list();
  else if (strcmp(cmd, "read") == 0 && argc == 4) {
    if (!okpath(argv[3]))
      finish(-1, "ERR:bad-path");
    do_read(argv[3]);
  } else if (strcmp(cmd, "append") == 0 && argc == 6)
    do_effect(EFF_APPEND, argv[3], argv[4], argv[5]);
  else if (strcmp(cmd, "create") == 0 && argc == 6)
    do_effect(EFF_CREATE, argv[3], argv[4], argv[5]);
  else
    finish(-1, "ERR:unknown-command");
  return 0;
}
