#!/usr/bin/env python3
"""steam.py - Steam-side container I/O: game_50.arc <-> mvsc2 blob (pure Python).

game_50.arc is an MT-Framework v7 ARC holding ONE file, "bin\\mvsc2", which is a
zlib-compressed IBIS+AFS blob. Layout:

  0x00  "ARC\\0"
  0x04  u16 version (7)
  0x06  u16 file count (1)
  0x08  file entry (80 bytes):
          [0x00] char[64] name ("bin\\mvsc2")
          [0x40] u32 ext_hash (0x21D3D8A7)
          [0x44] u32 compressed_size
          [0x48] u32 (flags<<29) | decompressed_size
          [0x4C] u32 data offset (0x8000)
  0x8000 zlib stream

So reading is zlib.decompress; writing is zlib.compress + patch the two size
fields in the header region. No external tools, no temp files.
"""
import os, struct, zlib

DATA_OFFSET = 0x8000
ENTRY = 0x08                  # file entry start
F_COMP = ENTRY + 0x44         # compressed_size field
F_DECOMP = ENTRY + 0x48       # (flags<<29)|decompressed_size field


def read_arc(arc_path):
    """Return the decompressed mvsc2 blob (bytes) from a game_50.arc."""
    data = open(arc_path, "rb").read()
    if data[:4] != b"ARC\x00":
        raise ValueError("not an ARC file (magic %r)" % data[:4])
    comp_size = struct.unpack_from("<I", data, F_COMP)[0]
    off = struct.unpack_from("<I", data, ENTRY + 0x4C)[0] or DATA_OFFSET
    return zlib.decompress(data[off:off + comp_size])


def write_arc(blob, out_arc, template_arc, level=9):
    """Write `blob` (bytes) as a game_50.arc, reusing template_arc's header.

    Only the compressed/decompressed size fields change; the file entry (name,
    hash, offset) and header padding are copied from the template verbatim, so
    the result is a structurally identical ARC the game accepts.
    """
    tmpl = open(template_arc, "rb").read()
    if tmpl[:4] != b"ARC\x00":
        raise ValueError("template is not an ARC file")
    header = bytearray(tmpl[:DATA_OFFSET])         # header + entry + padding
    compressed = zlib.compress(bytes(blob), level)
    flags = struct.unpack_from("<I", header, F_DECOMP)[0] >> 29   # keep quality bits
    struct.pack_into("<I", header, F_COMP, len(compressed))
    struct.pack_into("<I", header, F_DECOMP, (flags << 29) | len(blob))
    os.makedirs(os.path.dirname(os.path.abspath(out_arc)), exist_ok=True)
    with open(out_arc, "wb") as f:
        f.write(header)
        f.write(compressed)
    return out_arc
