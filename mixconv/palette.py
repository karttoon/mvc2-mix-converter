#!/usr/bin/env python3
"""palette.py - port character palettes between DC and Steam PL??_DAT.BIN files.

A character's colour data lives inside PL??_DAT.BIN. A uint32 LE at offset 0x08
gives the palette-block start and 0x0C the end (relative to the file). The block
is the same length and colour format (ARGB4444) on both platforms — only its
absolute position differs (Steam's header region is 0x20 smaller, so every offset
is shifted). Therefore porting a recolour = copy the palette block from the source
file (located by ITS header) into the target file (located by ITS header).

`build_target_dat(src_dat, stock_target_dat)` returns a target-platform _DAT with
its palette block replaced by the source's — same size as stock_target_dat, so it
patches into the target container in place.
"""
import struct


def palette_span(dat: bytes):
    """Return (start, end) of the palette block.

    0x08 = palette start, 0x0C = palette end. Some mixes use an EXTENDED palette:
    they relocate the block to a larger region appended at EOF and update 0x08 but
    leave 0x0C stale (pointing at the old, now-earlier end). When 0x0C <= start we
    treat EOF as the end (extended-palette layout).
    """
    start, end = struct.unpack_from("<II", dat, 0x08)
    if not (0 < start < len(dat)):
        raise ValueError(f"bad palette start {start:#x} in {len(dat)}B file")
    if not (start < end <= len(dat)):
        end = len(dat)                       # extended-palette: 0x0C stale -> EOF
    return start, end


def build_target_dat(src_dat: bytes, stock_target_dat: bytes):
    """Return (out_bytes, note). out is stock_target_dat with its palette block
    overwritten from src_dat. Copies min(src,target) bytes so an extended-palette
    source ports its base costume colours into the target's fixed slot (extra
    slots the target can't hold are dropped -> note explains)."""
    ss, se = palette_span(src_dat)
    ts, te = palette_span(stock_target_dat)
    src_len, tgt_len = se - ss, te - ts
    n = min(src_len, tgt_len)
    out = bytearray(stock_target_dat)
    out[ts:ts + n] = src_dat[ss:ss + n]
    note = None
    if src_len > tgt_len:
        note = f"extended palette: ported base {n}B, dropped {src_len-tgt_len}B extra"
    return bytes(out), note
