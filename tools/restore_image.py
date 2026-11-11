#!/usr/bin/env python3
"""Rebuild a full disk image from the evidence folder.
   python3 tools/restore_image.py evidence/final/pristine-fs.img.gz evidence/final/C1/append-inblock.stage2-after-header.postcrash.blockdiff.gz out.img
The result can be booted (`agent.qemu.VM`) or parsed (`tests.lib.fsimage.Image.load`)."""
import gzip
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.lib.fsimage import apply_diff  # noqa: E402

base_gz, diff, out = sys.argv[1:4]
with tempfile.NamedTemporaryFile(delete=False) as t:
    t.write(gzip.open(base_gz, "rb").read())
open(out, "wb").write(apply_diff(t.name, diff))
os.unlink(t.name)
print("wrote", out)
