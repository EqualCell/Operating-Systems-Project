# Disk format

```
block 0        boot (unused)
block 1        superblock
blocks 2..32   log: header (2) + 30 data blocks (LOGBLOCKS)          nlog = 31
blocks 33..45  inode blocks (200 inodes, 16 per block)               13 blocks
block 46       free-block bitmap
block 47       EFFECT TABLE   <-- reserved by mkfs (EFF_TABLE_BLOCKS = 1)
blocks 48..    data blocks
```
(numbers for `FSSIZE = 2000`; always read them from the superblock.)

## Superblock (`kernel/fs.h`) – two fields appended
```
uint magic, size, nblocks, ninodes, nlog, logstart, inodestart, bmapstart;
uint effstart;    // first effect-table block         (47)
uint effblocks;   // number of effect-table blocks    (1)
```
## Effect-table entry – 16 bytes, little-endian
```
offset 0   uint64 key      full 64-bit key; 0 = empty slot
offset 8   int32  result   saved result (>= 0)
offset 12  uint32 sig      FNV-1a of (op, path, 0, payload)
```
64 entries per block. Slot of a key: `hash(key) % nslots`, then **linear probing** over all slots of
all table blocks; no deletion, so an empty slot ends a probe. Hash = high half of
`key * 0x9E3779B97F4A7C15`.

## Why ordinary files can never overwrite the table
`mkfs` counts the table in `nmeta`, and `balloc(freeblock)` marks blocks `0..nmeta-1` used in the
bitmap, so xv6's allocator never hands them out. The independent checker verifies it
(`Image.check_consistency`: table blocks marked in bitmap; no inode owns a block below the first
data block; no block owned twice).

## Rebuilding
Any change to `fs.h` or `mkfs.c` needs `make clean && make qemu` (stale `fs.img` = garbage). Never
rebuild `fs.img` between a crash and its replay: tests copy the pristine image once per **trial**
and use that one file for crash, reboot and replay (the test records the file's inode number to prove it).
