#ifndef GRANT_H
#define GRANT_H
#define GR_MAGIC 0x47524e54
#define GR_FORMAT 1
#define GR_SLOTS 32
#define GR_OBJECTS 256
#define GR_BLOCKS (1 + GR_SLOTS + 2)
#define GR_PATH 16
#define GR_ACTIVE 1
#define GR_REVOKED 2
#define GR_CONSUMED 3
#define GR_ENOENT -20
#define GR_REVOKED_ERR -21
#define GR_STALE -22
#define GR_CONSUMED_ERR -23
#define GR_PENDING -24
#define GR_CORRUPT -25

// Entire request is copied once. No user pointers, ABI fits one syscall arg.
struct grant_request {
  uint64 grant_id;
  uint64 request_id;
  int op;
  int n;
  char path[GR_PATH];
  char payload[256];
};
struct grant_record {
  struct grant_request binding;
  uint64 version;
  uint inum;
  int state;
  int result;
  uint reserved;
};
struct grant_header {
  uint magic, format, slots, objects;
};
struct grant_status {
  uint64 request_id, expected_version, current_version;
  int state, result;
};
#endif
