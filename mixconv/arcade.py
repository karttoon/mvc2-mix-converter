#!/usr/bin/env python3
"""arcade.py - CPU/arcade extras for Steam -> DC conversion.

1. CPU AI port. Steam stores each character's 5 AI files (TAIKI/ATCK/WARI/
   YOK/LIB) as separate AFS entries at idx 504 + 59*kind + char (kind 0-4,
   char 0-58; match by INDEX - some archive/manifest names are wrong). On DC
   the same five files are the LAST five subfiles of that character's
   PLxx_DAT.BIN (offset-table slots 9-13, 64-byte aligned, byte-identical to
   stock Steam). Changed AI is spliced in by rebuilding the DAT's tail.

2. Arcade difficulty patches: the Steam companion's live RAM pokes, baked
   into the DC 1ST_READ.BIN (CPU full damage, max rank from round start,
   rank caps lifted at every Options difficulty).

Spec: D:\\Storage\\MvC2Modding\\ArcadeLogic\\docs\\DC_ARCADE_PATCHES.md
(1ST_READ load address 0x8C010000 -> file offset = RAM - 0x8C010000).

The disc stores 1ST_READ.BIN SCRAMBLED (standard Dreamcast bootfile
scramble, deterministic and seeded by file size), so the patcher
descrambles, verifies every stock table at its documented offset, patches,
and rescrambles. It refuses to touch a bootfile it doesn't recognize.
"""
import struct

# ---------------------------------------------------------------------------
# Dreamcast bootfile (de)scramble - Marcus Comstedt's algorithm. The sequence
# of 32-byte slice indices is a deterministic PRNG permutation per chunk, so
# scramble and descramble are the same walk with source/target swapped.
# ---------------------------------------------------------------------------
_MAXCHUNK = 2048 * 1024


class _Rnd:
    def __init__(self, n):
        self.seed = n & 0xFFFF

    def next(self):
        self.seed = (self.seed * 2109 + 9273) & 0x7FFF
        return (self.seed + 0xC000) & 0xFFFF


def _chunk_order(rnd, slices):
    idx = list(range(slices))
    order = []
    for i in range(slices - 1, -1, -1):
        x = (rnd.next() * i) >> 16
        idx[i], idx[x] = idx[x], idx[i]
        order.append(idx[i])
    return order


def _walk(data, unscramble):
    out = bytearray(len(data))
    rnd = _Rnd(len(data))
    pos = base = 0
    left = len(data)
    chunk = _MAXCHUNK
    while chunk >= 32:
        while left >= chunk:
            for sl in _chunk_order(rnd, chunk // 32):
                o = base + 32 * sl
                if unscramble:
                    out[o:o + 32] = data[pos:pos + 32]
                else:
                    out[pos:pos + 32] = data[o:o + 32]
                pos += 32
            left -= chunk
            base += chunk
        chunk >>= 1
    if left:
        if unscramble:
            out[base:base + left] = data[pos:pos + left]
        else:
            out[pos:pos + left] = data[base:base + left]
    return bytes(out)


def descramble(data):
    return _walk(data, True)


def scramble(data):
    return _walk(data, False)


# ---------------------------------------------------------------------------
# Arcade difficulty patches (1ST_READ.BIN, unscrambled offsets)
# ---------------------------------------------------------------------------
_DMG_ATK = 0x13F3DA        # CPU damage scale tables, tbl[0]/32: 0x18 -> 0x20
_DMG_VIC = 0x13F3FA
_DMG_SIG = bytes.fromhex("18181A1A1C1C1C1C1E1E1E1E")
_THR_OFF = 0x13E538        # 32 x u16 LE rank thresholds: 79 + 80*i
_CAP_A = 0x13E49C          # 64-byte rank-cap tables per Options difficulty
_CAP_B = 0x13E4DC
_CAP_A_SIG = bytes.fromhex("04080C101214181A")
_CAP_B_SIG = bytes.fromhex("060A12161A1A1A1A")


def _verify_stock_tables(plain):
    probs = []
    for off in (_DMG_ATK, _DMG_VIC):
        if plain[off:off + 12] != _DMG_SIG:
            probs.append("damage table @0x%X" % off)
    thr = struct.unpack_from("<32H", plain, _THR_OFF)
    if list(thr) != [79 + 80 * i for i in range(32)]:
        probs.append("rank-threshold table @0x%X" % _THR_OFF)
    if plain[_CAP_A:_CAP_A + 8] != _CAP_A_SIG:
        probs.append("cap table A @0x%X" % _CAP_A)
    if plain[_CAP_B:_CAP_B + 8] != _CAP_B_SIG:
        probs.append("cap table B @0x%X" % _CAP_B)
    return probs


def patch_arcade_tables(fr):
    """Return 1ST_READ.BIN bytes with the three difficulty patches applied.

    Accepts the bootfile as stored on the disc (scrambled) or plain; the
    result comes back in the same form. Raises ValueError when the stock
    tables are not exactly where/what the spec says."""
    was_scrambled = False
    plain = fr
    if _verify_stock_tables(plain):
        plain = descramble(fr)
        was_scrambled = True
        probs = _verify_stock_tables(plain)
        if probs:
            raise ValueError("1ST_READ.BIN not recognized (plain or "
                             "descrambled): " + ", ".join(probs))
        if scramble(plain) != fr:
            raise ValueError("1ST_READ.BIN scramble round-trip failed")

    out = bytearray(plain)
    out[_DMG_ATK] = 0x20                       # CPU deals 32/32 damage
    out[_DMG_VIC] = 0x20                       # CPU takes 32/32 damage
    out[_THR_OFF:_THR_OFF + 62] = b"\x00" * 62  # rank 31 on the first tick
    out[_CAP_A:_CAP_A + 64] = b"\x1f" * 64      # every difficulty caps at 31
    out[_CAP_B:_CAP_B + 64] = b"\x1f" * 64
    return scramble(bytes(out)) if was_scrambled else bytes(out)


# ---------------------------------------------------------------------------
# CPU AI files: Steam AFS entries -> DC PLxx_DAT.BIN tail rebuild
# ---------------------------------------------------------------------------
AI_BASE, AI_KINDS, AI_CHARS = 504, 5, 59
_AI_SLOTS = (9, 10, 11, 12, 13)     # DAT offset-table slots of AI files 0-4


def ai_idx(char, kind):
    return AI_BASE + AI_CHARS * kind + char


def is_ai_idx(i):
    return AI_BASE <= i < AI_BASE + AI_CHARS * AI_KINDS


def changed_ai(mix_entries, stock_entries):
    """{char: (stock_files, mix_files)} for chars whose 5 AI files differ."""
    out = {}
    for ch in range(AI_CHARS):
        stk = [stock_entries[ai_idx(ch, k)] for k in range(AI_KINDS)]
        mix = [mix_entries[ai_idx(ch, k)] for k in range(AI_KINDS)]
        if stk != mix:
            out[ch] = (stk, mix)
    return out


def rebuild_dat(dat, stock_ai, new_ai):
    """Replace the 5 AI subfiles at the tail of a DC PLxx_DAT.BIN.

    Keeps everything before the first AI subfile, re-appends each new AI
    file 64-byte aligned, updates the offset table, pads the end to 32.
    AI offsets are found by the stock Steam bytes; if the DAT already
    carries non-stock AI (modified base disc), table slots 9-13 are used."""
    n = struct.unpack_from("<I", dat, 0)[0] // 4
    table = list(struct.unpack_from("<%dI" % n, dat, 0))
    offs = []
    for f in stock_ai:
        o = dat.find(f)
        if o < 0 or o not in table:
            offs = None
            break
        offs.append(o)
    if offs is None:
        if n <= max(_AI_SLOTS):
            raise ValueError("DAT offset table has no AI slots")
        offs = [table[s] for s in _AI_SLOTS]
        if sorted(offs) != offs or min(offs) <= 0:
            raise ValueError("AI slots 9-13 don't look like subfile offsets")
    first = min(offs)
    if any(t > first for t in table if t and t not in offs):
        raise ValueError("a non-AI subfile sits after the AI files")
    # resolve each AI file's TABLE POSITION up front: a new offset written
    # for one file can collide with another slot's old value, so looking the
    # table up by value mid-rewrite swaps slots (hit on PL34 file2/file3)
    probe = list(table)
    slots = []
    for o in offs:
        s = probe.index(o)
        probe[s] = None
        slots.append(s)
    out = bytearray(dat[:first])
    for s, f in zip(slots, new_ai):
        while len(out) % 64:
            out.append(0)
        table[s] = len(out)
        out += f
    while len(out) % 32:
        out.append(0)
    struct.pack_into("<%dI" % n, out, 0, *table)
    return bytes(out)
