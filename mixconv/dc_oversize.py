#!/usr/bin/env python3
"""dc_oversize.py - grow a DC .cdi so oversized files fit (append + repoint).

The stock disc is packed (no free space), so to fit a file bigger than its slot
we must EXTEND the data track: append new sectors after it (before the footer),
point the file's ISO9660 directory record at the appended region, and update the
CDI footer track length + the ISO volume-space size to cover the new sectors.

Data track here is mode-2, 2336-byte sectors (8-byte subheader + 2048 user + 280
EDC/ECC). We copy a real sector's subheader and leave EDC/ECC zero (Flycast ignores
it; parity for real hardware is future work).

Multi-session safe: self-boot mix discs (e.g. Boot Dreams output) have a second
session after the game data. Appended sectors are inserted BEFORE session 2, which
is shifted later, and all of its footer geometry fields (start/end LBA, plus the
duplicate copies DiscJuggler keeps) are bumped -- otherwise session 2 is clobbered
and the disc won't boot.

This module first exposes the footer field offsets so we can patch track length
in place, verified against disc.parse_cdi before any mutation.
"""
import struct
import disc as D

CDI_V2, CDI_V3, CDI_V35 = 0x80000004, 0x80000005, 0x80000006


def footer_offsets(path):
    """Return dict with absolute file offsets of the DATA track's `length` and
    `total_length` fields in the CDI footer, plus footer_start and version.
    Mirrors disc._read_track but records positions instead of just values.
    """
    f = open(path, "rb")
    f.seek(0, 2); size = f.tell()
    f.seek(size - 8)
    version, header_offset = struct.unpack("<II", f.read(8))
    foot_start = size - header_offset if version == CDI_V35 else header_offset
    f.seek(foot_start)
    (sessions,) = struct.unpack("<H", f.read(2))
    tracks = []
    for s in range(sessions):
        (ntracks,) = struct.unpack("<H", f.read(2))
        for t in range(ntracks):
            tracks.append(_read_track_off(f, version))
        f.read(4); f.read(8)
        if version != CDI_V2:
            f.read(1)
    f.close()
    # pick the data track the same way build_iso does (largest mode-1/2 track)
    data = max((t for t in tracks if t["mode"] in (1, 2) and t["length"] > 1000),
               key=lambda t: t["length"])
    return {"version": version, "footer_start": foot_start, "file_size": size,
            "data": data, "all": tracks}


def _read_track_off(f, version):
    tv, = struct.unpack("<I", f.read(4))
    if tv != 0:
        f.read(8)
    f.read(10); f.read(10)
    f.read(4)
    (flen,) = struct.unpack("<B", f.read(1))
    f.read(flen); f.read(11); f.read(4); f.read(4)
    tv, = struct.unpack("<I", f.read(4))
    if tv == 0x80000000:
        f.read(8)
    f.read(2)
    pregap, = struct.unpack("<I", f.read(4))
    length_off = f.tell()
    (length,) = struct.unpack("<i", f.read(4))
    f.read(6)
    (mode,) = struct.unpack("<I", f.read(4))
    f.read(12)
    (start_lba,) = struct.unpack("<I", f.read(4))
    total_off = f.tell()
    (total_length,) = struct.unpack("<I", f.read(4))
    f.read(16)
    (ssv,) = struct.unpack("<I", f.read(4))
    sector_size = {0: 2048, 1: 2336, 2: 2352}.get(ssv)
    f.read(29)
    if version != CDI_V2:
        f.read(5)
        tv, = struct.unpack("<I", f.read(4))
        if tv == 0xffffffff:
            f.read(78)
    return {"pregap": pregap, "length": length, "length_off": length_off,
            "mode": mode, "start_lba": start_lba, "total_length": total_length,
            "total_off": total_off, "sector_size": sector_size}


def _detect_bias(iso, start_lba):
    """LBA bias: physical_sector = stored_lba - bias (see disc.walk_iso)."""
    pvds = D._find_pvd(iso)
    pvd = D._sec(iso, pvds)
    root = pvd[156:156 + 34]
    root_lba = struct.unpack("<I", root[2:6])[0]
    root_size = struct.unpack("<I", root[10:14])[0]
    for b in (start_lba, 0, root_lba - 23, root_lba - 20):
        if b is None or b < 0 or (root_lba - b) < 0:
            continue
        recs = D._parse_dir(iso, root_lba - b, root_size)
        if len(recs) >= 2 and recs[0][0] == b"\x00" and recs[1][0] == b"\x01":
            return b
    raise ValueError("could not detect LBA bias")


def _find_records(iso, targets, bias):
    """{NAME: (dir_phys_lba, off_in_dir, elba, size)} for files in `targets`."""
    pvds = D._find_pvd(iso)
    pvd = D._sec(iso, pvds)
    root = pvd[156:156 + 34]
    root_lba = struct.unpack("<I", root[2:6])[0]
    root_size = struct.unpack("<I", root[10:14])[0]
    found, stack, seen = {}, [(root_lba, root_size)], set()
    while stack:
        lba, size = stack.pop()
        if (lba, size) in seen:
            continue
        seen.add((lba, size))
        phys = lba - bias
        blob = iso[phys * 2048: phys * 2048 + ((size + 2047) // 2048) * 2048]
        i = 0
        while i < len(blob):
            rl = blob[i]
            if rl == 0:
                nxt = ((i // 2048) + 1) * 2048
                if nxt <= i:
                    break
                i = nxt; continue
            rec = blob[i:i + rl]
            if len(rec) < 33:
                break
            elba = struct.unpack("<I", rec[2:6])[0]
            sz = struct.unpack("<I", rec[10:14])[0]
            fl, nl = rec[25], rec[32]
            name = rec[33:33 + nl].split(b";")[0].decode("ascii", "ignore")
            if fl & 2 and rec[33:33 + nl] not in (b"\x00", b"\x01"):
                stack.append((elba, sz))
            elif name.upper() in targets:
                found[name.upper()] = (phys, i, elba, sz)
            i += rl
    return found


def grow_cdi(src, dst, files: dict):
    """Copy src->dst and write `files` {NAME: bytes}, growing the disc for any
    file bigger than its on-disc slot.

    Same-size (<= slot) files are patched in place. Oversized files are appended
    as new mode-2 sectors after the data track and their ISO9660 directory record
    is repointed (LBA + size). The CDI footer track length + the ISO PVD volume
    size are extended to cover the new sectors.

    Returns (patched, appended, skipped).
    """
    import shutil
    shutil.copyfile(src, dst)
    data = bytearray(open(dst, "rb").read())

    fo = footer_offsets(dst)
    dt = fo["data"]
    ss, mode = dt["sector_size"], dt["mode"]
    hlen = D._header_len(mode, ss)
    # base = file offset of ISO physical sector 0 (after pregap)
    _, tracks = D.parse_cdi(dst)
    tr = max((t for t in tracks if t.mode in (1, 2) and t.length > 1000), key=lambda t: t.length)
    base = tr.data_offset + tr.pregap_length * ss

    iso, start_lba = D.build_iso(dst)
    bias = _detect_bias(iso, start_lba)
    total_iso_sectors = len(iso) // 2048           # physical sectors of ISO data
    recs = _find_records(iso, set(files), bias)

    def sec_file_off(phys):                         # file offset of a sector's user data
        return base + phys * ss + hlen

    def write_sector_user(phys, chunk):             # chunk up to 2048 bytes
        off = sec_file_off(phys)
        if off + 2048 > len(data):
            data.extend(b"\x00" * (off + 2048 - len(data)))
        data[off:off + len(chunk)] = chunk

    subheader = bytes(data[base:base + hlen]) if hlen else b""  # reuse a real subheader

    # Multi-session aware: the grown track's file region ends at insert_point. On a
    # 2-session self-boot disc (e.g. Boot Dreams output) session 2's data and then the
    # footer follow it. Capture both, then drop everything from insert_point on, so
    # appended sectors INSERT before session 2 (which is shifted later) instead of
    # overwriting it -- the single-track assumption otherwise clobbers session 2 and
    # leaves its TOC fields stale, producing a disc that won't boot.
    insert_point = tr.data_offset + tr.total_length * ss
    later_data = bytes(data[insert_point:fo["footer_start"]])   # session 2+ (empty if single-session)
    footer_bytes = bytes(data[fo["footer_start"]:])
    later_tracks = [t for t in tracks if t is not tr and t.start_lba > tr.start_lba]

    patched, appended, skipped = [], [], []
    append_phys = total_iso_sectors                 # next free physical sector (at track end)
    del data[insert_point:]                          # appends extend cleanly before session 2

    for name in sorted(files):
        u = name.upper()
        if u not in recs:
            skipped.append((u, "not on disc")); continue
        dir_phys, off_in_dir, elba, slot = recs[u]
        payload = files[u]
        nsec = (len(payload) + 2047) // 2048
        if len(payload) <= slot:
            # in place: overwrite existing extent (padded), keep record
            phys0 = elba - bias
            for k in range(nsec):
                write_sector_user(phys0 + k, payload[k * 2048:(k + 1) * 2048])
            # update only the size fields in the directory record
            _patch_record(data, base, ss, hlen, dir_phys, off_in_dir, elba, len(payload))
            patched.append(u)
        else:
            # append into new sectors + repoint the record
            new_lba = append_phys + bias
            for k in range(nsec):
                # frame each appended sector: subheader then user
                so = base + (append_phys + k) * ss
                if so + ss > len(data):
                    data.extend(b"\x00" * (so + ss - len(data)))
                if subheader:
                    data[so:so + hlen] = subheader
                write_sector_user(append_phys + k, payload[k * 2048:(k + 1) * 2048])
            _patch_record(data, base, ss, hlen, dir_phys, off_in_dir, new_lba, len(payload))
            appended.append((u, len(payload), append_phys, nsec))
            append_phys += nsec

    added = append_phys - total_iso_sectors
    fb = bytearray(footer_bytes)
    if added:
        # 1) extend ISO PVD volume-space size (LE @0x50, BE @0x54 in PVD sector 16)
        pvd_phys = D._find_pvd(iso)
        new_vol = struct.unpack_from("<I", iso, pvd_phys * 2048 + 80)[0] + added
        struct.pack_into("<I", data, base + pvd_phys * ss + hlen + 80, new_vol)
        struct.pack_into(">I", data, base + pvd_phys * ss + hlen + 84, new_vol)
        # 2) bump EVERY geometry field by `added`. The DiscJuggler footer keeps
        #    duplicate copies (a secondary total_length, and a re-listed start/end LBA
        #    per track in the tail), so patching just the primary offsets leaves stale
        #    values behind. A value-based bump catches all copies: the grown track's
        #    length + total_length grow; every LATER session's start-LBA and end-LBA
        #    shift by the inserted amount. (Values are far apart -- session gap ~11250
        #    -- so no old/new collisions in practice.)
        bumps = {dt["length"]: dt["length"] + added,
                 dt["total_length"]: dt["total_length"] + added}
        for lt in later_tracks:
            bumps[lt.start_lba] = lt.start_lba + added
            bumps[lt.start_lba + lt.total_length] = lt.start_lba + lt.total_length + added
        for old, new in bumps.items():
            fb[:] = fb.replace(struct.pack("<I", old), struct.pack("<I", new))
        # header_offset: v3.5 stores it as distance from EOF (footer length is
        # unchanged); v2/v3 store it from file start (moves by the inserted bytes).
        hdr_off = len(fb) if fo["version"] == CDI_V35 else (insert_point + added * ss + len(later_data))
        struct.pack_into("<II", fb, len(fb) - 8, fo["version"], hdr_off)

    data += later_data                              # session 2+ data, now shifted later
    data += fb                                      # footer last
    open(dst, "wb").write(bytes(data))
    return patched, appended, skipped


def _patch_record(data, base, ss, hlen, dir_phys, off_in_dir, lba, size):
    """Rewrite an ISO9660 directory record's extent LBA + size (both-endian)."""
    def cdi_off(iso_byte):
        sec, within = divmod(iso_byte, 2048)
        return base + sec * ss + hlen + within
    db = dir_phys * 2048 + off_in_dir
    struct.pack_into("<I", data, cdi_off(db + 2), lba)
    struct.pack_into(">I", data, cdi_off(db + 6), lba)
    struct.pack_into("<I", data, cdi_off(db + 10), size)
    struct.pack_into(">I", data, cdi_off(db + 14), size)


if __name__ == "__main__":
    import sys
    fo = footer_offsets(sys.argv[1])
    d = fo["data"]
    print(f"version=0x{fo['version']:08X} footer_start={fo['footer_start']} size={fo['file_size']}")
    print(f"data track: mode={d['mode']} ss={d['sector_size']} length={d['length']} "
          f"total_length={d['total_length']} start_lba={d['start_lba']}")
    print(f"  length field  @ file offset {d['length_off']}")
    print(f"  total  field  @ file offset {d['total_off']}")
    # cross-check against disc.parse_cdi
    _, tracks = D.parse_cdi(sys.argv[1])
    dt = max((t for t in tracks if t.mode in (1, 2) and t.length > 1000), key=lambda t: t.length)
    ok = (dt.length == d["length"] and dt.total_length == d["total_length"])
    # verify offsets by reading raw
    raw = open(sys.argv[1], "rb")
    raw.seek(d["length_off"]); L = struct.unpack("<i", raw.read(4))[0]
    raw.seek(d["total_off"]); T = struct.unpack("<I", raw.read(4))[0]
    raw.close()
    print(f"cross-check: parse_cdi length={dt.length} total={dt.total_length} ; "
          f"raw@offsets length={L} total={T} ; MATCH={ok and L==d['length'] and T==d['total_length']}")
