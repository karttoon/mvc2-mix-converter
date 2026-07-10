# MvC2 Mix Converter — formats & architecture

Technical reference for how the converter works. For usage see the top-level
README and SETUP.md.

## The two containers

### Dreamcast — `.cdi`
- DiscJuggler CD image; one big **ISO9660** data track holds the game files
  (`STGxxTEX.BIN`, `PLxx_DAT.BIN`, `ADX_*.BIN`, …).
- Read: `mixconv/disc.py` — parses the CDI footer (DiscJuggler track table) and
  walks ISO9660 with auto LBA-bias detection (handles relative- and
  absolute-addressed discs).
- Write: `mixconv/dc_oversize.py` — same-size files are patched into their sectors
  in place; oversized files are appended (see below).

### Steam — `game_50.arc`
- MT-Framework ARC containing a **single** file: an `IBIS`-wrapped **CRI AFS**
  archive of ~890 index-addressed files (the same game files as the DC disc,
  minus DC-only files, plus arcade-only files).
- Outer ARC: a `"ARC\0"` header + a single **zlib** stream at `0x8000`.
  `mixconv/steam.py` reads/writes it in pure Python (decompress / recompress +
  patch the two size fields) — no external archive tool.
- Inner IBIS+AFS: `mixconv/afs.py`. The AFS has no filename table; names come from
  a recovered index↔name map (`data/afs_manifest.json`).

## What converts (portability)

The Steam build (NAOMI arcade) and the DC console build are related but not
identical. Comparing stock-vs-stock decides what can cross by simple file copy:

- **Stages** — byte-identical → copy 1:1.
- **HUD / lifebars / effects / font / char-select / portraits** — mostly identical
  → copy 1:1 (a handful differ and are reported).
- **Character palettes** — live inside `PLxx_DAT.BIN`; the palette *block* is the
  same ARGB4444 format on both platforms (just at a slightly different offset), so
  it's region-copied (`mixconv/palette.py`). The rest of the `_DAT` file differs,
  so whole-file copy would corrupt it.
- **Music** — different formats → transcoded (below).

`data/afs_manifest.json` carries, per AFS index: the filename, size, stock md5s,
and a `portable` flag (byte-identical between stock DC and stock Steam).

## Oversize handling

Files bigger than their slot need special handling in both containers.

### Steam AFS — relayout
`afs.py build()` re-lays-out the whole archive: entries placed in index order,
`0x800`-aligned; the table-of-contents and the trailing CRI filename-table pointer
are regenerated. This round-trips an unmodified blob byte-for-byte and lets any
entry grow (later entries just shift). The game reads by TOC, so shifting is safe.

### Dreamcast ISO — append + repoint
The stock disc is packed (no free space), so oversized files are **appended** as
new sectors after the data track; the file's ISO9660 directory record is
**repointed** (extent LBA + size, both-endian) at the appended region; and the CDI
track length + the ISO PVD volume-space size are extended to cover the new sectors.
Same-size files are still patched in place. (`dc_oversize.grow_cdi`.)

## Music

Steam `.sngw` are **Ogg Vorbis** (renamed); Dreamcast uses **CRI ADX**. Name map
is 1:1 (`ADX_S000.BIN` ↔ `s000.sngw`). ffmpeg transcodes both ways.

- The Steam BGM engine requires **48 kHz**, **LoopStart/LoopEnd** Vorbis comments,
  and a **`Ver=0002`** tag, or it plays silence. `music.py` supplies all three,
  carrying loop points from the ADX header.
- Steam music lives *outside* the arc, as loose `.sngw` in the game's
  `sound\bgm\mvc2\wav` folder (drop-in). On DC the ADX are files inside the disc.

## Module map

| Module | Role |
|---|---|
| `disc.py` | DC CDI/ISO9660 read |
| `dc_oversize.py` | DC write (in-place + append/repoint/grow) |
| `afs.py` | Steam IBIS+AFS read/write/relayout |
| `steam.py` | ARC ⇄ blob (pure-Python zlib de/compress) |
| `manifest.py` | AFS index↔name map + file classification |
| `palette.py` | `PLxx_DAT` palette region-port |
| `music.py` | ADX ⇄ Ogg transcode with loop/format metadata |
| `convert.py` | DC→Steam and Steam→DC orchestration |
| `install.py` | backup / install / restore / reset-to-stock |
| `config.py` | path resolution + Steam auto-detect |
| `menu.py` | terminal front-end |

## Known limitations

- **EDC/ECC** on appended DC sectors is left zero (Flycast ignores it). Real
  hardware / some burners may want it recomputed — future work.
- Music transcode is lossy (ADX → Ogg → ADX round-trips lose a little fidelity).
