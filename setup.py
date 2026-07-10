#!/usr/bin/env python3
"""setup.py - one-time setup: populate base/ with your own stock game data.

This tool ships with NO game files. It needs three stock references (from your own
legally-owned copies) placed in base/:

  base/stock_game_50.arc      - a CLEAN (unmodified) Steam game_50.arc
  base/stock_music/*.sngw     - the CLEAN Steam MvC2 music (.sngw)
  base/MVC2_STOCK_DC.cdi      - a stock Dreamcast MvC2 disc image (.cdi)

The first two can be copied from your Steam install *after* you verify its
integrity in Steam (right-click the game -> Properties -> Installed Files ->
Verify). The third you provide yourself.

Run:  py setup.py
"""
import os, sys, shutil
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "mixconv"))
import config


FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"


def ask(prompt):
    return input(prompt).strip().strip('"')


def _download_ffmpeg(dest_exe):
    """Download the official ffmpeg Windows build and extract ffmpeg.exe."""
    import urllib.request, zipfile, tempfile, shutil
    os.makedirs(os.path.dirname(dest_exe), exist_ok=True)
    with tempfile.TemporaryDirectory() as d:
        zpath = os.path.join(d, "ffmpeg.zip")
        print(f"    downloading {FFMPEG_URL} ...")
        urllib.request.urlretrieve(FFMPEG_URL, zpath)
        with zipfile.ZipFile(zpath) as z:
            member = next(n for n in z.namelist() if n.endswith("/bin/ffmpeg.exe"))
            with z.open(member) as src, open(dest_exe, "wb") as out:
                shutil.copyfileobj(src, out)


def main():
    print("=" * 60)
    print("  MvC2 Mix Converter - setup")
    print("=" * 60)

    # 1) ffmpeg
    if os.path.exists(config.FFMPEG):
        print(f"\n[ok] ffmpeg found: {config.FFMPEG}")
    else:
        print(f"\n[!] ffmpeg (for music) is not present.")
        if ask("    Download it automatically from ffmpeg.org's Windows builds? [y/N] ").lower() == "y":
            try:
                _download_ffmpeg(config.FFMPEG)
                print(f"    [ok] ffmpeg installed at {config.FFMPEG}")
            except Exception as e:
                print(f"    [!] download failed: {e}")
                print(f"    Get a Windows build manually and place ffmpeg.exe at {config.FFMPEG}")
        else:
            print(f"    Place ffmpeg.exe at {config.FFMPEG} yourself (see tools/README.txt).")

    # 2) stock Steam arc + music (from a VERIFIED-CLEAN install)
    root = config.steam_root()
    if root:
        print(f"\n[ok] Steam Fighting Collection found:\n      {root}")
        print("\n  IMPORTANT: only copy these if your game is currently STOCK")
        print("  (verify integrity in Steam first, then log in once to confirm).")
        if ask("  Copy stock arc + music from this install now? [y/N] ").lower() == "y":
            os.makedirs(config.BASE, exist_ok=True)
            shutil.copyfile(config.steam_arc(root), config.STOCK_STEAM_ARC)
            print(f"    -> {config.STOCK_STEAM_ARC}")
            os.makedirs(config.STOCK_MUSIC, exist_ok=True)
            wav = config.steam_music_dir(root)
            n = 0
            for f in os.listdir(wav):
                if f.lower().endswith(".sngw"):
                    shutil.copyfile(os.path.join(wav, f), os.path.join(config.STOCK_MUSIC, f))
                    n += 1
            print(f"    -> {config.STOCK_MUSIC} ({n} tracks)")
    else:
        print("\n[!] Steam Fighting Collection not found automatically.")
        print(f"    Place a clean game_50.arc at {config.STOCK_STEAM_ARC}")
        print(f"    and clean .sngw music in {config.STOCK_MUSIC}")

    # 3) stock DC cdi (ONLY needed to BUILD Dreamcast discs, Steam->DC)
    if os.path.exists(config.STOCK_DC_CDI):
        print(f"\n[ok] stock DC disc present: {config.STOCK_DC_CDI}")
    else:
        print("\n[ ] A stock Dreamcast .cdi is only needed to BUILD Dreamcast discs")
        print("    (Steam -> DC). Installing mixes into Steam does NOT need it.")
        p = ask("    Path to a stock Dreamcast MvC2 .cdi (blank to skip): ")
        if p and os.path.exists(p):
            os.makedirs(config.BASE, exist_ok=True)
            shutil.copyfile(p, config.STOCK_DC_CDI)
            print(f"    -> {config.STOCK_DC_CDI}")

    # 4) final check
    print("\n" + "=" * 60)
    ok, problems = config.check()
    if ok:
        print("  Ready to install mixes into Steam. Run MixConverter.bat.")
        if not os.path.exists(config.STOCK_DC_CDI):
            print("  (Add a stock DC .cdi later to also build Dreamcast discs.)")
    else:
        print("  Still missing (needed to install mixes into Steam):")
        for p in problems:
            print("    -", p)
    print("=" * 60)


if __name__ == "__main__":
    main()
