"""stagemerge.py - repackage a slim full-replacement custom stage into the stock
slot structure, so it survives the game's per-slot stage code.

Community "custom stages" (Paxtez-builder style) replace the whole STG??POL.BIN
with a slim 1-model file. The game's per-slot stage code walks the STOCK file's
structure (stock POLs hold 4-16 texture records and up to 83 models and the code
rewrites mesh headers in them every frame), so a slim file makes it fall over:
tolerated by lenient hosts (Flycast, the Steam port) but a crash on strict ones
(real hardware, nullDC - seen live: a custom training stage in slot 0B).

The fix, proven by the CPS2 stage-port pipeline (merge_slot.py, from which this
is adapted): keep the stock POL byte-for-byte - size, model count, record count,
nothing moves - and splice the port in.

  * the port's model replaces stock model 0 (or the largest model when 0 is too
    small, with the table entries swapped so the port still DRAWS at index 0);
  * the port's texture records take table slots 0..k-1; every remaining stock
    slot becomes a 128x128 record pointing at a zeroed stub inside the TEX;
  * every stock mesh is re-pointed at the stub, moved to the translucent list
    (the stub's zero alpha blends it away) and set to depth-compare Never.

Unlike merge_slot.py this keeps the port's art at full size: the output TEX is
the port's TEX with the stub appended in its padding (the converter grows files
on both platforms, so the stock TEX budget does not apply).
"""
import struct

POL_RAM = 0x0CEA0000
TEX_RAM = 0x0CC00000
REC = 16
MHDR = 0x18          # model header: u32 1, u32 3, float cx, cy, cz, radius
XHDR = 0x50          # mesh header: pcw, isp, tsp, tcw, 12 B, radius, texId, -1, 5 floats, 16 B, strip bytes
TEXID = 0x20         # texId offset inside a mesh header
TOTAL = 0x4C         # strip-bytes offset inside a mesh header
PCW = 0x00           # param control word: bits 26-24 are the list type (0 = opaque, 2 = translucent)
ISP = 0x04           # ISP/TSP word: bits 31-29 are the depth compare mode (0 = Never)
TSP = 0x08           # TSP word: bits 5-3 = texture U size, 2-0 = V size (8 << code)
PORT_MARK = bytes.fromhex("fec0a148")  # the CPS2 builder's constant mesh radius; absent from third-party ports
SHADE = 6            # TSP bits 7-6: texture shading instruction (0 = decal, 1 = modulate)
STUB = 128 * 128 * 2


def _header(b):
    return struct.unpack_from("<4I", b, 0)


def records(b):
    """Texture records from a POL header (stops at the all-zero terminator)."""
    mt, mc, trs, tre = _header(b)
    out, i = [], trs - POL_RAM
    while i + REC <= tre - POL_RAM:
        w, h, fmt, fl, _, base, _ = struct.unpack_from("<HHBBHII", b, i)
        if w == 0 and h == 0:
            break
        out.append(dict(w=w, h=h, fmt=fmt, fl=fl, base=base))
        i += REC
    return out


def model_spans(b):
    mt, mc, trs, tre = _header(b)
    ptrs = list(struct.unpack_from(f"<{mc}I", b, mt - POL_RAM))
    return [(ptrs[k] - POL_RAM, (ptrs[k + 1] - POL_RAM) if k + 1 < len(ptrs) else len(b))
            for k in range(mc)]


def model_count(b):
    try:
        return _header(b)[1]
    except struct.error:
        return 0


def _mesh_texids(b, start, end):
    """Offsets of every mesh's texId field in a model, walking the strip sizes.
    The walk is structural (no magic numbers); trailing non-mesh data after the
    last mesh is normal (STG03/0C keep ~42 KB there) and ends the walk."""
    out, j = [], start + MHDR
    while j + XHDR <= end:
        pcw = struct.unpack_from("<I", b, j)[0]
        tot = struct.unpack_from("<I", b, j + TOTAL)[0]
        if pcw >> 28 not in (8, 9) or tot == 0 or j + XHDR + tot > end:
            return out if out else []
        out.append(j + TEXID)
        j += XHDR + tot
    return out


def is_slim_custom(pol, stock_pol):
    """A full-replacement custom POL: fewer models than stock (the Paxtez-style
    slim files hold 1 model vs stock's dozens). Retextures and merged ports keep
    the stock model count and pass through untouched."""
    try:
        mc, smc = model_count(pol), model_count(stock_pol)
        return 0 < mc < smc and len(pol) < len(stock_pol)
    except Exception:
        return False


def merge(stock_pol, stock_tex, port_pol, port_tex):
    """Return (pol, tex) with the port spliced into the stock slot structure.
    Raises ValueError when the port cannot be merged safely - the caller should
    then fall back to porting the files untouched and say so."""
    sb, stex, ob, otex = stock_pol, stock_tex, port_pol, port_tex
    smt, smc, strs, stre = _header(sb)
    srecs, orecs = records(sb), records(ob)
    spans, ospans = model_spans(sb), model_spans(ob)

    # the last stock record slot must stay free as the zeroed stub
    if len(orecs) > len(srecs) - 1:
        raise ValueError(f"port has {len(orecs)} texture records, slot only {len(srecs)} "
                         "(one must stay free as the stub)")
    off = 0
    for i, r in enumerate(orecs):   # bases are rewritten as a running sum below
        if r["base"] - TEX_RAM != off:
            raise ValueError(f"port texture record {i} not contiguous in record order")
        off += r["w"] * r["h"] * 2

    # the port's model goes to stock model 0's span, or the largest span when 0
    # is too small (table entries swapped so the port still draws at index 0)
    o0s, o0e = ospans[0]
    blob = bytearray(ob[o0s:o0e])
    sizes = [e - s for s, e in spans]
    victim = 0
    if len(blob) > sizes[0]:
        victim = max(range(smc), key=lambda i: sizes[i])
        if len(blob) > sizes[victim]:
            raise ValueError(f"port model is {len(blob)} B, largest stock model span "
                             f"only {sizes[victim]} B")
    for w in range(0, len(blob) - 3, 4):  # the port model must be position-independent
        v = struct.unpack_from("<I", blob, w)[0]
        if 0x0CC00000 <= v < 0x0CF00000:
            raise ValueError(f"port model holds an absolute pointer ({v:#x}) at +{w:#x}")

    # CPS2-builder ports: switch their meshes to decal shading so per-slot base
    # colour writes can't tint them. Third-party ports lack the marker: no-op.
    j = 0
    while True:
        j = blob.find(PORT_MARK, j)
        if j < 0:
            break
        to = j - 0x14
        struct.pack_into("<I", blob, to, struct.unpack_from("<I", blob, to)[0] & ~(3 << SHADE))
        j += 4

    # assemble IN PLACE: start from the stock POL and never move a byte (models
    # shifting is what crashed STG03/0C - their last span carries non-mesh data)
    out = bytearray(sb)
    vs, ve = spans[victim]
    out[vs:ve] = bytes(blob) + b"\0" * (ve - vs - len(blob))
    if victim != 0:
        ptrs = list(struct.unpack_from(f"<{smc}I", sb, smt - POL_RAM))
        ptrs[0], ptrs[victim] = ptrs[victim], ptrs[0]
        struct.pack_into(f"<{smc}I", out, smt - POL_RAM, *ptrs)

    # output TEX: the port's art, padded, with the stub in the padding. Kept at
    # the stock size when it fits (same-size patch); grown when the art is big.
    pad = (len(otex) + 31) & ~31
    out_len = max(len(stex), pad + STUB)
    out_tex = otex + b"\0" * (out_len - len(otex))
    stub = pad

    # records rewritten in the stock table's own slots; stock slots the port
    # doesn't use become 128x128 records over the zeroed stub
    trs = strs - POL_RAM
    off = 0
    for i, r in enumerate(orecs):
        struct.pack_into("<HHBBHII", out, trs + i * REC,
                         r["w"], r["h"], r["fmt"], r["fl"], 0, TEX_RAM + off, 0)
        off += r["w"] * r["h"] * 2
    for i in range(len(orecs), len(srecs)):
        struct.pack_into("<HHBBHII", out, trs + i * REC,
                         128, 128, 0, srecs[i]["fl"], 0, TEX_RAM + stub, 0)
    struct.pack_into("<HHBBHII", out, trs + len(srecs) * REC, 0, 0, 0, 0, 0, 0, 0)

    # neutralise every stock mesh: texId -> stub, reader shrunk to 8x8, moved to
    # the translucent list with SRC_ALPHA/INV_SRC_ALPHA (the stub's zero alpha
    # blends it away), depth compare Never (strict hosts honour it)
    for k in range(smc):
        if k == victim:
            continue
        s, e = spans[k]
        for o in _mesh_texids(sb, s, e):
            struct.pack_into("<I", out, o, len(srecs) - 1)
            struct.pack_into("<I", out, o - TEXID + PCW,
                             (struct.unpack_from("<I", out, o - TEXID + PCW)[0] & ~0x07000000)
                             | 0x02000000)
            struct.pack_into("<I", out, o - TEXID + TSP,     # U/V size bits also cleared:
                             (struct.unpack_from("<I", out, o - TEXID + TSP)[0] & 0x0007FFC0)
                             | 0x94800000)                   # the 8x8 stub reader
            struct.pack_into("<I", out, o - TEXID + ISP,
                             struct.unpack_from("<I", out, o - TEXID + ISP)[0] & 0x1FFFFFFF)

    # self-check (the DC stub rule): stub zeroed and inside the TEX, every stock
    # mesh samples a stub record, no port mesh does
    if any(out_tex[stub:stub + STUB]):
        raise ValueError("stub region is not zero")
    # (file ranges from the STOCK table: after a swap the new pointer list is no
    # longer monotonic, so spans re-derived from it would be wrong)
    outb = bytes(out)
    for k, (s, e) in enumerate(spans):
        tids = [struct.unpack_from("<I", outb, o)[0] for o in _mesh_texids(outb, s, e)]
        if k == victim:
            bad = [t for t in tids if t >= len(orecs)]
        else:
            bad = [t for t in tids if not (len(orecs) <= t < len(srecs))]
        if bad:
            raise ValueError(f"model {k} still samples records {sorted(set(bad))}")
    return bytes(out), out_tex
