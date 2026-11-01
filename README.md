# MvC2 Mix Converter

Convert **Marvel vs. Capcom 2 "mixes"** between the **Dreamcast** (`.cdi` disc image)
and the **Steam Marvel vs. Capcom Fighting Collection** (`game_50.arc`) — in both
directions, from a simple point-and-click app (or a terminal menu, if you prefer).

- **DC → Steam** — point it at a Dreamcast mix and it installs the mix's stages,
  character palettes, HUD/effects, UI and music straight into your Steam game.
- **Steam → DC** — it reads your live Steam install and builds a `.cdi` you can
  burn to a DVD-R or load in an emulator (Flycast), music and all.

It backs up your files first, can restore or reset to stock, and is meant to be
usable by non-technical people.

> This tool contains **no game data**. You supply your own files from your own
> legally-owned copies — see **[SETUP.md](SETUP.md)**.

---

## What actually converts

| In-game element | DC ⇄ Steam |
|---|---|
| **Stages** (including custom / oversized) | ✅ |
| **Character palettes** (skins/recolors) | ✅ |
| **HUD, lifebars, effects, font, char-select** | ✅ (portable ones) |
| **Music** | ✅ (transcoded ADX ⇄ Ogg; loop points preserved) |
| **CPU AI mods** | ✅ Steam → DC (spliced into each character's DC data file) |

Nothing is silently dropped — every changed file is reported as converted or, if
it genuinely can't cross platforms, listed with the reason.

Building a disc from the CLI also offers an optional **arcade difficulty** bake
(`--arcade-patches`): the CPU deals/takes full damage, starts every fight at max
AI rank, and the Options difficulty no longer caps it — patched into the disc's
own executable, no trainer needed.

## Two ways to run it

Both use the same engine and do the same things — pick whichever you like.

### A) Standalone app — easiest, no Python

Grab the `MixConverter_v1.0.zip` from the release, unzip it (keep the files
together), and double-click **`MixConverter.exe`**. ffmpeg is bundled; there's no
Python install and no console.

1. **Setup tab** → **Build initial backup from Steam** (it auto-detects your Steam
   install; use *Change Steam folder…* if it's on another drive). For a clean
   baseline, verify the game in Steam first.
2. **Install into Steam** → pick a mix (`.cdi`/`.zip`) → *Convert & Install*.
3. **Build a Disc** → optionally pick a base `.cdi` → *Build Disc*.
4. **Restore / Reset** → undo a mix or return to your baseline.

### B) From source — advanced / cross-checking

- **Windows**, **Python 3.10+** (standard library only — no pip packages)
- **ffmpeg** (for music) — `setup.py` can download it for you
- **Your own game data** — a clean Steam install (setup copies from it). A stock
  Dreamcast disc is only needed to *build* DC discs.

1. Run **`py setup.py`** once (fetches ffmpeg, copies your stock Steam files — see
   [SETUP.md](SETUP.md)).
2. Put your mixes (`.cdi`/`.zip`) into `mixes\`.
3. Launch the GUI with **`py mixconv\gui.py`**, or the terminal menu via
   **`MixConverter.bat`** / `py mixconv\menu.py`:

```
   [1] Install a DC mix into Steam        (DC  -> Steam)
   [2] Build a Dreamcast disc from Steam  (Steam -> DC)
   [3] Restore Steam from a backup
   [4] Reset Steam to stock
   [5] Exit
```

**Building a DC disc** can start from a fresh stock disc, or **patch an existing
`.cdi`** — an already-modded disc with custom stages/mods. In that case your Steam
palettes, HUD, effects and music are patched on top, keeping the base disc's mods
wherever the Steam side didn't also change them.

> **Maintainers:** the standalone app is built with PyInstaller from
> [`packaging/MixConverter.spec`](packaging/MixConverter.spec); run
> `py packaging/make_release.py` to assemble the distributable ZIP. See
> [`packaging/`](packaging/) for details.

## How it works (short version)

- **Steam side** — `game_50.arc` is an MT-Framework archive wrapping a single
  `IBIS`+`AFS` blob of ~890 indexed files (a single zlib stream). The tool
  decompresses it, edits files by name via a recovered index↔name map, and
  recompresses — all in pure Python — growing the archive when a file doesn't fit.
- **DC side** — the `.cdi` is an ISO9660 disc. Same-size files are patched in
  place; oversized files (custom stages, transcoded music) are appended as new
  sectors and their directory records repointed, with the disc extended to match.
- **Music** — Steam `.sngw` are Ogg Vorbis; Dreamcast uses CRI ADX. ffmpeg
  transcodes both ways, carrying loop points and the game's required metadata.

See [docs/PROJECT-BRIEF.md](docs/PROJECT-BRIEF.md) for the full format write-up.

## Credits

- The MvC2 modding community for the format groundwork
- FFmpeg project

## License

MIT (this tool's code). See [LICENSE](LICENSE). Bundled/needed third-party tools
retain their own licenses; no game assets are included.
