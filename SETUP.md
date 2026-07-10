# Setup

This tool ships with **no game data** — you use your own, from your own
legally-owned copies. The good news: most of it is automatic.

**Just run `py setup.py`** and follow the prompts. It will:

1. Offer to **download ffmpeg** for you (used for music).
2. Copy your **stock Steam files** (arc + music) straight from your own install.
3. Optionally take a **stock Dreamcast disc** — only needed if you want to *build*
   DC discs (see below).

That's it. Details and the manual alternative are below.

---

## To install mixes INTO Steam (DC → Steam)

You only need:

- **ffmpeg** — `setup.py` can download it, or drop `ffmpeg.exe` in `tools\`
  yourself (see `tools/README.txt`).
- **A clean Steam install.** Before running setup, make sure your game is stock:
  in Steam, right-click **MARVEL vs. CAPCOM Fighting Collection** → **Properties**
  → **Installed Files** → **Verify integrity of game files**, then launch once.
  `setup.py` copies the clean `game_50.arc` and music into `base\` for you.

**No Dreamcast disc is required for this direction.** The tool figures out what a
mix changed using the checksums it already ships (`data\afs_manifest.json`).

Then drop your mixes (`.cdi`/`.zip`) into `mixes\` and run `MixConverter.bat`.

## To BUILD a Dreamcast disc FROM Steam (Steam → DC)

This one extra thing is required:

- **`base\MVC2_STOCK_DC.cdi`** — a stock (unmodified) Dreamcast MvC2 disc image.
  Provide your own dump. It's the clean base the disc is built from.

> A DC disc **cannot** be generated from the Steam files — the Steam build has no
> Dreamcast bootloader or executable, so there's nothing to boot. It has to be a
> real Dreamcast image.

## Manual copy (if you skip `setup.py`)

```
<Steam>\...\nativeDX11x64\arc\pc\game_50.arc        ->  base\stock_game_50.arc
<Steam>\...\nativeDX11x64\sound\bgm\mvc2\wav\*.sngw  ->  base\stock_music\
your stock Dreamcast disc image                     ->  base\MVC2_STOCK_DC.cdi
a Windows ffmpeg.exe                                 ->  tools\ffmpeg.exe
```

## Notes

- **Windows only.** The Steam collection is Windows-only and paths assume it.
- The Steam `game_50.arc` is unpacked/repacked in **pure Python** (a single zlib
  stream) — no external archive tool is required.
- `data\afs_manifest.json` (the index↔filename + portability map) is included and
  works for the current game version. If a game update changes files, regenerate
  it with `py tools\build_manifest.py` (needs a stock `game_50.arc`).
