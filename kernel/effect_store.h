#ifndef _KERNEL_EFFECT_STORE_H_
#define _KERNEL_EFFECT_STORE_H_

#include "types.h"
#include "effect.h"

struct inode;

struct file_id_snapshot {
  uint32 dev;
  uint32 inum;
  uint32 gen;
  uint32 exists;
  uint64 version;
  uint64 size;
};

struct effect_record {
  uint32 valid;
  uint32 is_extended;
  uint64 key_or_req_id;
  uint64 grant_id;
  uint64 arg_hash;
  uint32 op;
  uint32 target_inum;
  uint32 target_gen;
  int32 result_bytes;
  uint64 post_version;
  uint64 pad;
};

struct grant_record {
  uint32 valid;
  uint32 state;
  uint64 grant_id;
  uint32 allowed_op;
  uint32 max_payload_len;
  uint32 target_inum;
  uint32 target_gen;
  uint64 bound_version;
  uint64 consumed_req_id;
  uint64 consumed_arg_hash;
  uint64 pad;
};

typedef char assert_effect_record_size[
    (sizeof(struct effect_record) == 64) ? 1 : -1];
typedef char assert_grant_record_size[
    (sizeof(struct grant_record) == 64) ? 1 : -1];

void effect_store_init(void);
int effect_store_lookup_base(uint64 key, struct effect_record *);
int effect_store_lookup_ext(uint64 grant_id, uint64 req_id,
                            struct effect_record *);
int effect_store_has_free_slot(void);
int effect_store_insert(const struct effect_record *);
int effect_store_grant_lookup(uint64 grant_id, struct grant_record *);
int effect_store_grant_has_slot(void);
int effect_store_grant_alloc(const struct grant_record *);
int effect_store_grant_update(const struct grant_record *);

int effect_fs_snapshot_path(char *, struct file_id_snapshot *);
int effect_fs_execute_base(uint32, char *, uint8 *, uint32,
                          struct file_id_snapshot *, int *);
int effect_fs_execute_checked_append(char *, uint8 *, uint32,
                                     uint32, uint32, uint64,
                                     struct file_id_snapshot *, int *);

int effect_auth_can_mutate_inode(struct inode *);
int effect_auth_can_create_in_dir(struct inode *);
void effect_test_double_bump_version(struct inode *);

#endif
