#!/usr/bin/env python3
"""Assemble the distributable release folder + ZIP from a built exe.

Run AFTER building dist/MixConverter.exe:
    py packaging/make_release.py

Produces:
    dist/MixConverter_v1.0/           (the folder users unzip)
    dist/MixConverter_v1.0.zip        (what you hand out)

Layout:
    MixConverter.exe
    tools/ffmpeg.exe                  (bundled, copied from tools/)
    base/README.txt                   (user's stock files land here)
    mixes/README.txt
    output/                           (empty; discs + backups go here)
    README.txt
"""
import os, shutil, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist")
REL_NAME = "MixConverter_v1.1.1"
REL = os.path.join(DIST, REL_NAME)
README = os.path.join(ROOT, "packaging", "readme")


def main():
    exe = os.path.join(DIST, "MixConverter.exe")
    ff = os.path.join(ROOT, "tools", "ffmpeg.exe")
    if not os.path.exists(exe):
        raise SystemExit("build dist/MixConverter.exe first (see packaging/MixConverter.spec)")
    if not os.path.exists(ff):
        raise SystemExit("tools/ffmpeg.exe not found (needed for music conversion)")

    if os.path.exists(REL):
        shutil.rmtree(REL)
    os.makedirs(os.path.join(REL, "tools"))
    os.makedirs(os.path.join(REL, "base"))
    os.makedirs(os.path.join(REL, "mixes"))
    os.makedirs(os.path.join(REL, "output"))

    shutil.copyfile(exe, os.path.join(REL, "MixConverter.exe"))
    shutil.copyfile(ff, os.path.join(REL, "tools", "ffmpeg.exe"))
    shutil.copyfile(os.path.join(README, "README.txt"), os.path.join(REL, "README.txt"))
    shutil.copyfile(os.path.join(README, "base_README.txt"),
                    os.path.join(REL, "base", "README.txt"))
    shutil.copyfile(os.path.join(README, "mixes_README.txt"),
                    os.path.join(REL, "mixes", "README.txt"))
    open(os.path.join(REL, "output", ".gitkeep"), "w").close()

    zpath = os.path.join(DIST, REL_NAME + ".zip")
    if os.path.exists(zpath):
        os.remove(zpath)
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for dirpath, _, files in os.walk(REL):
            for fn in files:
                full = os.path.join(dirpath, fn)
                arc = os.path.join(REL_NAME, os.path.relpath(full, REL))
                z.write(full, arc)

    size = os.path.getsize(zpath) / (1024 * 1024)
    print(f"release folder: {REL}")
    print(f"release zip   : {zpath}  ({size:.0f} MB)")


if __name__ == "__main__":
    main()
