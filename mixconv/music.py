#!/usr/bin/env python3
"""music.py - MvC2 music transcoding between Dreamcast and Steam.

Formats (verified):
  * Dreamcast: ADX_XXXX.BIN  = raw CRI ADX (magic 0x8000), stereo 44.1kHz, inside
    the .cdi filesystem.
  * Steam:     xxxx.sngw      = Ogg Vorbis (OggS/vorbis) in
    nativeDX11x64\\sound\\bgm\\mvc2\\wav\\ (OUTSIDE game_50.arc).

Name mapping is 1:1: ADX_CAPL.BIN <-> capl.sngw, ADX_S000.BIN <-> s000.sngw
(strip "ADX_", lowercase, .BIN->.sngw).

Transcoding uses ffmpeg (native ADX + libvorbis). ffmpeg is NOT bundled; set the
path via MIXCONV_FFMPEG env var or pass ffmpeg= explicitly, or have it on PATH.

DC ADX carries loop points; we read them from the ADX header and write them back
as Vorbis LoopStart/LoopEnd comments (the Steam BGM engine requires those, plus a
"Ver=0002" tag and 48 kHz, or it plays nothing). For OGG->ADX we set a full-file
loop by default.
"""
import os, sys, re, subprocess, shutil, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

# Bundled ffmpeg lives next to the .exe (frozen) / repo root (source) — config
# resolves the folder in both cases, so this is the single source of truth.
_BUNDLED = config.FFMPEG
_NO_WINDOW = config.NO_WINDOW    # suppress console flash under a --windowed exe

def find_ffmpeg(explicit=None):
    for cand in (explicit, os.environ.get("MIXCONV_FFMPEG"), _BUNDLED, "ffmpeg"):
        if not cand:
            continue
        if os.path.sep in cand or (len(cand) > 1 and cand[1] == ":"):
            if os.path.exists(cand):
                return cand
        else:
            hit = shutil.which(cand)
            if hit:
                return hit
    return None


def adx_name_to_sngw(name):
    """ADX_S000.BIN -> s000.sngw"""
    m = re.fullmatch(r"ADX_(.+)\.BIN", name.upper())
    return (m.group(1).lower() + ".sngw") if m else None


def sngw_name_to_adx(name):
    """s000.sngw -> ADX_S000.BIN"""
    m = re.fullmatch(r"(.+)\.sngw", name, re.IGNORECASE)
    return ("ADX_" + m.group(1).upper() + ".BIN") if m else None


def _run(ff, args, data):
    """Run ffmpeg reading `data` from stdin, returning stdout bytes."""
    p = subprocess.run([ff, "-hide_banner", "-loglevel", "error", *args],
                       input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       creationflags=_NO_WINDOW)
    if p.returncode != 0:
        raise RuntimeError("ffmpeg failed: " + p.stderr.decode(errors="replace"))
    return p.stdout


def adx_header_info(adx_bytes):
    """Parse CRI ADX header. Returns dict with sample_rate, total_samples and
    loop (start,end) samples if a loop is present. ADX fields are big-endian.
    See https://github.com/vgmstream ADX notes.
    """
    import struct
    if adx_bytes[:2] != b"\x80\x00":
        return {}
    chans = adx_bytes[7]
    rate, total = struct.unpack_from(">II", adx_bytes, 8)
    info = {"sample_rate": rate, "total_samples": total, "channels": chans}
    ver = adx_bytes[0x12]
    # loop table location depends on version (verified on MvC2's v3 ADX):
    #   v3: enable@0x18, loop_start_sample@0x1C, loop_end_sample@0x24
    #   v4: enable@0x24, loop_start_sample@0x28, loop_end_sample@0x30
    loop_start = loop_end = None
    try:
        base = {3: 0x18, 4: 0x24}.get(ver)
        if base is not None:
            enable = struct.unpack_from(">I", adx_bytes, base)[0]
            ls = struct.unpack_from(">I", adx_bytes, base + 4)[0]
            le = struct.unpack_from(">I", adx_bytes, base + 12)[0]
            if enable:
                loop_start, loop_end = ls, le
    except Exception:
        pass
    info["loop_start"] = loop_start
    info["loop_end"] = loop_end
    return info


def adx_to_sngw(adx_bytes, ffmpeg):
    """DC ADX bytes -> Steam .sngw (Ogg Vorbis) with LoopStart/LoopEnd comments.

    The game's BGM engine requires LoopStart/LoopEnd Vorbis comments or it won't
    play the track. We carry the ADX loop points when present; otherwise loop the
    whole track (LoopStart=0, LoopEnd=total_samples).
    """
    # The Steam BGM engine expects 48 kHz Ogg Vorbis with LoopStart/LoopEnd
    # comments (verified against a known-working community .sngw). The DC ADX is
    # 44.1 kHz, so we resample to 48 kHz and scale the loop points (in samples)
    # to the output rate.
    OUT_RATE = 48000
    info = adx_header_info(adx_bytes)
    rate = info.get("sample_rate", 44100) or 44100
    total = info.get("total_samples", 0)
    ls = info.get("loop_start")
    le = info.get("loop_end")
    if ls is None or le is None or le <= ls:
        ls, le = 0, total
    scale = OUT_RATE / rate
    ls_out = int(round(ls * scale))
    le_out = int(round(le * scale))
    with tempfile.TemporaryDirectory() as d:
        i = os.path.join(d, "in.adx"); o = os.path.join(d, "out.ogg")
        open(i, "wb").write(adx_bytes)
        # The game's .sngw loader requires the Capcom-specific "Ver=0002" (and
        # "Time") Vorbis comments in addition to LoopStart/LoopEnd; without them
        # it silently rejects the track. -bitexact drops ffmpeg's own encoder tag
        # so our comment set matches a known-good file.
        p = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                            "-bitexact", "-i", i, "-ar", str(OUT_RATE),
                            "-c:a", "libvorbis", "-q:a", "8", "-bitexact",
                            "-metadata", f"LoopStart={ls_out}",
                            "-metadata", f"LoopEnd={le_out}",
                            "-metadata", "Ver=0002",
                            "-metadata", "Time=20240101000000", o],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           creationflags=_NO_WINDOW)
        if p.returncode != 0:
            raise RuntimeError("ADX->ogg failed: " + p.stderr.decode(errors="replace"))
        out = open(o, "rb").read()
    return _fix_vendor(out)


def _fix_vendor(ogg_bytes, vendor=b"Xiph.Org libVorbis I 20200704 (Reducing Environment)"):
    """Rewrite the Vorbis comment vendor string to match Capcom's known-good file.

    The vendor lives in the comment header packet: 0x03 'vorbis' <u32 len><vendor>.
    We only rewrite it when the new vendor is the same length is unnecessary — we
    rebuild the length field, so the ogg page's payload grows/shrinks; to stay
    safe we only swap when lengths match, else leave as-is (vendor is rarely
    checked; Ver/loop comments are the functional part).
    """
    import struct
    i = ogg_bytes.find(b"\x03vorbis")
    if i < 0:
        return ogg_bytes
    p = i + 7
    (vlen,) = struct.unpack_from("<I", ogg_bytes, p)
    if vlen == len(vendor):
        b = bytearray(ogg_bytes)
        b[p+4:p+4+vlen] = vendor
        return bytes(b)
    return ogg_bytes


def _read_loop_comments(ogg_bytes):
    """Pull LoopStart/LoopEnd (in samples) from the .sngw Vorbis comments, or
    (None, None) if absent. Values are ASCII digits after the tag."""
    def val(tag):
        i = ogg_bytes.find(tag + b"=")
        if i < 0:
            return None
        j = i + len(tag) + 1
        d = bytearray()
        while j < len(ogg_bytes) and 0x30 <= ogg_bytes[j] <= 0x39:
            d.append(ogg_bytes[j]); j += 1
        return int(d) if d else None
    return val(b"LoopStart"), val(b"LoopEnd")


def _adx_set_loop(adx_bytes, loop_start, loop_end):
    """Rebuild an ffmpeg ADX (which carries no loop table) as a type-3 ADX with a
    loop table, so the Dreamcast BGM engine loops it. loop_start/loop_end are in
    samples at the ADX's own sample rate. Byte offsets follow the CRI layout
    verified against stock MvC2 ADX:
        byte = header_size + frame_index * (block_size * channels)
        loop-start frame = start // 32 ;  loop-end frame = ceil(end / 32)
    """
    import struct
    co = struct.unpack_from(">H", adx_bytes, 2)[0]
    payload = adx_bytes[co + 4:]                 # ffmpeg's ADPCM data (audio starts at co+4)
    block = adx_bytes[5]; ch = adx_bytes[7]
    rate = struct.unpack_from(">I", adx_bytes, 8)[0]
    total = struct.unpack_from(">I", adx_bytes, 12)[0]
    highpass = struct.unpack_from(">H", adx_bytes, 16)[0]

    HS = 0x34                                    # new header size (audio starts here)
    frame = block * ch
    ls_byte = HS + (loop_start // 32) * frame
    le_byte = HS + ((loop_end + 31) // 32) * frame

    h = bytearray(HS)
    h[0:2] = b"\x80\x00"
    struct.pack_into(">H", h, 2, HS - 4)         # copyright offset (audio at +4)
    h[4] = 3; h[5] = block; h[6] = 4; h[7] = ch
    struct.pack_into(">I", h, 8, rate)
    struct.pack_into(">I", h, 12, total)
    struct.pack_into(">H", h, 16, highpass)
    h[18] = 3; h[19] = 0                          # version 3, flags 0
    struct.pack_into(">H", h, 0x14, 0)
    struct.pack_into(">H", h, 0x16, 1)
    struct.pack_into(">I", h, 0x18, 1)           # loop enabled
    struct.pack_into(">I", h, 0x1C, loop_start)
    struct.pack_into(">I", h, 0x20, ls_byte)
    struct.pack_into(">I", h, 0x24, loop_end)
    struct.pack_into(">I", h, 0x28, le_byte)
    h[HS - 6:HS] = b"(c)CRI"
    return bytes(h) + payload


def sngw_to_adx(sngw_bytes, ffmpeg):
    """Steam .sngw (Ogg) bytes -> DC ADX bytes.

    The DC BGM engine reads loop points from the ADX header. ffmpeg's adpcm_adx
    encoder writes none, so we transcode, then inject a loop table built from the
    .sngw's LoopStart/LoopEnd Vorbis comments (same sample rate, so no scaling).
    Tracks with no loop comments (one-shot jingles: continue, "here we go", etc.)
    are left un-looped, matching stock."""
    with tempfile.TemporaryDirectory() as d:
        i = os.path.join(d, "in.ogg"); o = os.path.join(d, "out.adx")
        open(i, "wb").write(sngw_bytes)
        p = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                            "-i", i, "-c:a", "adpcm_adx", o],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           creationflags=_NO_WINDOW)
        if p.returncode != 0:
            raise RuntimeError("ogg->ADX failed: " + p.stderr.decode(errors="replace"))
        adx = open(o, "rb").read()
    ls, le = _read_loop_comments(sngw_bytes)
    if ls is None or le is None or le <= ls:
        return adx                               # one-shot: no loop table (matches stock)
    return _adx_set_loop(adx, ls, le)
