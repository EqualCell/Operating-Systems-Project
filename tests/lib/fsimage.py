"""Independent oracle: parse an xv6 fs.img WITHOUT using any kernel code.

The checker deliberately re-implements the on-disk format from the xv6 book /
kernel/fs.h so a kernel bug cannot hide itself. It supports exactly what the
tests need: superblock, log header, log replay, inodes, root-directory files,
the effect table and a small consistency check.
"""
import struct

BSIZE = 1024
IPB = BSIZE // 64
T_DIR, T_FILE, T_DEVICE = 1, 2, 3


class Image:
    def __init__(self, data):
        self.d = bytearray(data)
        f = struct.unpack("<10I", self.d[BSIZE:BSIZE + 40])
        (self.magic, self.size, self.nblocks, self.ninodes, self.nlog,
         self.logstart, self.inodestart, self.bmapstart,
         self.effstart, self.effblocks) = f

    @classmethod
    def load(cls, path):
        with open(path, "rb") as fh:
            return cls(fh.read())

    def block(self, n):
        return self.d[n * BSIZE:(n + 1) * BSIZE]

    # ---- log --------------------------------------------------------------
    def log_header(self):
        b = self.block(self.logstart)
        n = struct.unpack("<i", b[:4])[0]
        blocks = list(struct.unpack("<30i", b[4:124]))[:max(n, 0)]
        return n, blocks

    def with_log_replayed(self):
        """What xv6 recovery would produce: copy every logged block home and
        clear the header. Returns a NEW Image (self is untouched)."""
        n, blocks = self.log_header()
        img = Image(self.d)
        for i, home in enumerate(blocks):
            src = self.block(self.logstart + 1 + i)
            img.d[home * BSIZE:(home + 1) * BSIZE] = src
        if n:
            img.d[self.logstart * BSIZE:self.logstart * BSIZE + 4] = b"\0\0\0\0"
        return img

    # ---- inodes / files ---------------------------------------------------
    def inode(self, inum):
        blk = self.inodestart + inum // IPB
        off = (inum % IPB) * 64
        raw = self.block(blk)[off:off + 64]
        t, major, minor, nlink, size = struct.unpack("<hhhhI", raw[:12])
        addrs = list(struct.unpack("<13I", raw[12:64]))
        return dict(type=t, nlink=nlink, size=size, addrs=addrs)

    def file_blocks(self, ino):
        out = []
        nblk = (ino["size"] + BSIZE - 1) // BSIZE
        for i in range(nblk):
            if i < 12:
                out.append(ino["addrs"][i])
            else:
                ind = struct.unpack("<256I", self.block(ino["addrs"][12]))
                out.append(ind[i - 12])
        return out

    def read_inode(self, ino):
        data = b""
        for b in self.file_blocks(ino):
            data += bytes(self.block(b))
        return data[:ino["size"]]

    def root_entries(self):
        root = self.inode(1)
        raw = self.read_inode(root)
        ents = {}
        for i in range(0, len(raw), 16):
            inum, name = struct.unpack("<H14s", raw[i:i + 16])
            if inum:
                ents[name.split(b"\0")[0].decode()] = inum
        return ents

    def read_file(self, path):
        """path like '/log.txt' (root directory only). None if missing."""
        name = path.lstrip("/")
        inum = self.root_entries().get(name)
        if inum is None:
            return None
        return self.read_inode(self.inode(inum))

    # ---- effect table -----------------------------------------------------
    def table(self):
        ents = []
        for b in range(self.effblocks):
            raw = self.block(self.effstart + b)
            for i in range(BSIZE // 16):
                key, res, sig = struct.unpack("<QiI", raw[i * 16:(i + 1) * 16])
                if key:
                    ents.append(dict(key=key, result=res, sig=sig, slot=b * 64 + i))
        return ents

    def free_blocks(self):
        """Number of free data blocks according to the bitmap."""
        bm = self.block(self.bmapstart)
        first_data = self.effstart + self.effblocks
        return sum(1 for b in range(first_data, self.size) if not bm[b // 8] & (1 << (b % 8)))

    # ---- consistency ------------------------------------------------------
    def check_consistency(self):
        """Return a list of problems (empty = consistent).
        Checks: magic, table blocks marked used in bitmap, no inode owns a
        table/log/meta block, no data block owned twice, bitmap covers files."""
        problems = []
        if self.magic != 0x10203040:
            problems.append("bad magic")
        first_data = self.effstart + self.effblocks
        bm = self.block(self.bmapstart)

        def used(b):
            return bool(bm[b // 8] & (1 << (b % 8)))

        for b in range(self.effstart, first_data):
            if not used(b):
                problems.append(f"effect-table block {b} not marked in bitmap")
        owners = {}
        for inum in range(1, self.ninodes):
            ino = self.inode(inum)
            if ino["type"] == 0:
                continue
            blocks = [a for a in ino["addrs"][:12] if a] if ino["size"] or True else []
            if ino["addrs"][12]:
                blocks.append(ino["addrs"][12])
                ind = struct.unpack("<256I", self.block(ino["addrs"][12]))
                blocks += [x for x in ind if x]
            for b in blocks:
                if b < first_data:
                    problems.append(f"inode {inum} owns reserved/meta block {b}")
                if b in owners:
                    problems.append(f"block {b} owned by inodes {owners[b]} and {inum}")
                owners[b] = inum
                if not used(b):
                    problems.append(f"inode {inum} block {b} not marked in bitmap")
        return problems


def fnv_sig(op, path, payload):
    """Independent re-implementation of the kernel's request signature
    (32-bit FNV-1a over op byte, path, 0, payload)."""
    h = 2166136261
    for b in bytes([op]) + path.encode() + b"\0" + payload:
        h = ((h ^ b) * 16777619) & 0xFFFFFFFF
    return h


def entries_by_key(img):
    return {e["key"]: e for e in img.table()}


def make_diff(base_path, img_path, out_path):
    """Write every 1 KB block of img that differs from base: [u32 blockno][1024 bytes]..., gzipped.
    (Rebuild with apply_diff(base_path, out_path).)"""
    import gzip
    base = open(base_path, "rb").read()
    img = open(img_path, "rb").read()
    assert len(base) == len(img)
    with gzip.open(out_path, "wb") as g:
        for b in range(len(img) // BSIZE):
            if img[b * BSIZE:(b + 1) * BSIZE] != base[b * BSIZE:(b + 1) * BSIZE]:
                g.write(struct.pack("<I", b) + img[b * BSIZE:(b + 1) * BSIZE])


def apply_diff(base_path, diff_path):
    import gzip
    data = bytearray(open(base_path, "rb").read())
    raw = gzip.open(diff_path, "rb").read()
    for i in range(0, len(raw), 4 + BSIZE):
        b = struct.unpack("<I", raw[i:i + 4])[0]
        data[b * BSIZE:(b + 1) * BSIZE] = raw[i + 4:i + 4 + BSIZE]
    return bytes(data)
