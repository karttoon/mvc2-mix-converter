#!/usr/bin/env python3
"""afs.py - Read/write the Steam Fighting Collection's MvC2 game data blob.

The Steam "Marvel vs. Capcom Fighting Collection" stores the MvC2 game image as
a single file inside game_50.arc:  bin/mvsc2.21D3D8A7

That blob is an **IBIS** wrapper (0x40-byte header) around a **CRI AFS** archive
(Sega/CRI "Archive File System"). The AFS holds ~890 indexed entries which are
exactly the Dreamcast game's files (STG*POL.BIN, PL*, DM*, etc.) but stored by
INDEX with no embedded filename table -- names come from an external manifest.

Layout (all little-endian):

  IBIS header @ 0x00
    0x00  char[4]  "IBIS"
    0x04  u32      version (1)
    0x08  u32      afs_offset (0x40 -- where the AFS payload begins)
    0x0C  u32      afs_size   (payload length in bytes)
    0x10..0x40     zero padding

  AFS @ afs_offset (0x40)                (all entry offsets are AFS-relative)
    0x00  char[4]  "AFS\0"
    0x04  u32      count
    0x08  count x {u32 offset, u32 size} table of contents
    ...   u32 meta_offset, u32 meta_size (filename-table ptr; (0,0) here = none)
    data begins at AFS-relative 0x80000, each entry 0x800-aligned.

Index 0 is a zero-size dummy ("AFS" per the mod-manager name list).

This module round-trips the blob byte-for-byte (see tests/test_afs.py) and lets
you replace individual entries by index.
"""
import struct

IBIS_MAGIC = b"IBIS"
AFS_MAGIC = b"AFS\x00"
ALIGN = 0x800           # AFS entries are aligned to 2 KiB
DATA_START = 0x80000    # first entry's AFS-relative offset (TOC padded to here)


class AfsBlob:
    """Parsed IBIS+AFS blob.

    `entries` is a list of bytes (b'' for dummies). We also keep the original
    TOC offsets and the raw pre-data region (TOC + padding + the mod-manager's
    appended-metadata pointer at DATA_START-8) so an unmodified blob round-trips
    byte-for-byte and same-size entry replacement is exact.
    """

    def __init__(self, ibis_version, afs_offset, entries, offsets, meta_size):
        self.ibis_version = ibis_version
        self.afs_offset = afs_offset      # normally 0x40
        self.entries = entries            # list[bytes], index-aligned
        self.offsets = offsets            # list[int] original AFS-relative offsets
        self.meta_size = meta_size        # size field of the @DATA_START-8 ptr (count*48)

    # ---------------------------------------------------------------- parse
    @classmethod
    def parse(cls, data: bytes) -> "AfsBlob":
        if data[:4] != IBIS_MAGIC:
            raise ValueError("not an IBIS blob (bad magic %r)" % data[:4])
        version, afs_off, afs_size = struct.unpack_from("<III", data, 4)
        if data[afs_off:afs_off + 4] != AFS_MAGIC:
            raise ValueError("no AFS magic at 0x%X" % afs_off)
        (count,) = struct.unpack_from("<I", data, afs_off + 4)
        entries, offsets = [], []
        for i in range(count):
            off, sz = struct.unpack_from("<II", data, afs_off + 8 + i * 8)
            offsets.append(off)
            entries.append(data[afs_off + off: afs_off + off + sz] if sz else b"")
        # the CRI filename-table pointer lives at DATA_START-8: (afs_size, count*48)
        _, meta_size = struct.unpack_from("<II", data, afs_off + DATA_START - 8)
        return cls(version, afs_off, entries, offsets, meta_size)

    # ---------------------------------------------------------------- build
    def build(self) -> bytes:
        """Serialize to an IBIS+AFS blob by re-laying-out the whole archive.

        Entries are placed in index order, each 0x800-aligned, from DATA_START.
        A dummy (empty) entry takes the current cursor without advancing it. The
        TOC and the DATA_START-8 filename-table pointer (afs_size, count*48) are
        regenerated. This round-trips an unmodified blob byte-for-byte AND handles
        entries that GREW (bigger entries just push everything after them later),
        so oversized DC->Steam files repack cleanly.
        """
        count = len(self.entries)
        hdr = bytearray(DATA_START)                     # header region [0, DATA_START)
        hdr[0:4] = AFS_MAGIC
        struct.pack_into("<I", hdr, 4, count)
        data_region = bytearray()
        cursor = DATA_START
        for i, b in enumerate(self.entries):
            sz = len(b)
            struct.pack_into("<II", hdr, 8 + i * 8, cursor, sz)
            if sz:
                pos = cursor - DATA_START
                if len(data_region) < pos + sz:
                    data_region.extend(b"\x00" * (pos + sz - len(data_region)))
                data_region[pos:pos + sz] = b
                cursor += (sz + ALIGN - 1) // ALIGN * ALIGN
            # dummy entries keep `cursor` (offset points at current data end)
        afs_size = cursor                                # 0x800-aligned end of data
        if len(data_region) < afs_size - DATA_START:     # pad last slot
            data_region.extend(b"\x00" * (afs_size - DATA_START - len(data_region)))
        struct.pack_into("<II", hdr, DATA_START - 8, afs_size, self.meta_size)
        afs = bytes(hdr) + bytes(data_region)
        out = bytearray()
        out += IBIS_MAGIC
        out += struct.pack("<III", self.ibis_version, self.afs_offset, len(afs))
        out += b"\x00" * (self.afs_offset - len(out))
        out += afs
        return bytes(out)

    # ---------------------------------------------------------------- helpers
    def replace(self, index: int, new_bytes: bytes):
        self.entries[index] = new_bytes

    def __len__(self):
        return len(self.entries)


class EntryTooLarge(Exception):
    def __init__(self, index, size, slot):
        super().__init__(f"entry {index}: {size}B exceeds slot {slot}B")
        self.index, self.size, self.slot = index, size, slot


def _slot_size(offsets, i, count):
    """Bytes available to entry i before the next non-empty entry's data."""
    for j in range(i + 1, count):
        if offsets[j] > offsets[i]:
            return offsets[j] - offsets[i]
    return None  # last entry: unbounded (tail follows)


if __name__ == "__main__":
    import sys, hashlib
    d = open(sys.argv[1], "rb").read()
    blob = AfsBlob.parse(d)
    print(f"IBIS v{blob.ibis_version} afs@0x{blob.afs_offset:X} entries={len(blob)}")
    nonzero = sum(1 for e in blob.entries if e)
    print(f"non-empty entries: {nonzero}  meta_size=0x{blob.meta_size:X}")
    rebuilt = blob.build()
    print("round-trip identical:", rebuilt == d,
          f"(orig {len(d)} vs rebuilt {len(rebuilt)})")
    if rebuilt != d:
        # locate first diff
        for i in range(min(len(d), len(rebuilt))):
            if d[i] != rebuilt[i]:
                print(f"  first diff at 0x{i:X}")
                break
