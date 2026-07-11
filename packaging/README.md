# Packaging — standalone Windows app

Builds `MixConverter.exe`, a single-file GUI (`mixconv/gui.py`) so non-technical
users don't need Python. The engine is unchanged; this is packaging + a front-end.

## Build

```
py -m pip install pyinstaller
py -m PyInstaller packaging/MixConverter.spec --noconfirm
py packaging/make_release.py
```

Outputs:
- `dist/MixConverter.exe` — the app (manifest embedded, `--onefile --windowed`)
- `dist/MixConverter_v1.0/` — the release folder (exe + `tools/ffmpeg.exe` + empty
  `base/ mixes/ output/` + READMEs)
- `dist/MixConverter_v1.0.zip` — what you hand out

`make_release.py` copies `tools/ffmpeg.exe` beside the exe, so make sure ffmpeg is
present (`py setup.py` can fetch it) before assembling the ZIP.

## How the freeze works

- **User-writable paths** (`base/ tools/ output/ mixes/`, ffmpeg, `steam_path.txt`)
  resolve next to the `.exe` via `config.app_dir()` → `dirname(sys.executable)`
  when frozen. Nothing is written into the temp extraction dir.
- **Bundled read-only data** (`data/afs_manifest.json`) is embedded with
  `--add-data` and loaded from `sys._MEIPASS` via `config.resource_dir()`.
- **ffmpeg is NOT embedded** — it ships beside the exe in `tools/` (smaller exe,
  and `config.FFMPEG` points there either way).
- Because the app is `--windowed`, ffmpeg/`reg` subprocess calls pass
  `creationflags=CREATE_NO_WINDOW` (via `config.NO_WINDOW`) so no console flashes.

## Sanity-check a frozen build

`_selftest.py` is a throwaway console script that imports the same engine modules
and prints where they resolve. Build it into a release folder and run it to
confirm the frozen path shim, manifest load, and ffmpeg discovery before shipping:

```
py -m PyInstaller --onefile --console --name _selftest --paths mixconv \
  --add-data "<abs>/data/afs_manifest.json;data" packaging/_selftest.py
```

## Notes

- **Not code-signed**, so Windows SmartScreen shows "unknown publisher" on first
  run (the README tells users to click *More info → Run anyway*). Code signing or
  `--onedir` are possible follow-ups if Defender heuristics ever flag it.
