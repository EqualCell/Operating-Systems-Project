// diskfill -- fill the whole disk with junk files f00, f01, ... (for the
// disk-full test). Prints  DISKFILL blocks=<n>  where n = 1 KB blocks written.
#include "kernel/types.h"
#include "kernel/fcntl.h"
#include "user/user.h"

int
main(void)
{
  static char buf[1024];
  int total = 0;
  memset(buf, 'F', sizeof(buf));
  for (int i = 0; i < 30; i++) {
    char name[4] = {'f', '0' + i / 10, '0' + i % 10, 0};
    int fd = open(name, O_CREATE | O_WRONLY);
    if (fd < 0)
      break;
    int wrote_any = 0;
    for (;;) {
      if (write(fd, buf, 1024) != 1024)
        break;
      total++;
      wrote_any = 1;
    }
    close(fd);
    if (!wrote_any)
      break; // disk is full
  }
  printf("DISKFILL blocks=%d\n", total);
  exit(0);
}
