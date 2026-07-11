#!/usr/bin/env python3
"""config.py - resolve all paths the converter needs (Steam install, bases, tools).

Auto-detects the Steam Fighting Collection install from the registry (same App IDs
the community CollectionTool.bat uses), with fallbacks to the common default path.
"""
import os, sys, subprocess


def app_dir():
    """Folder that holds the user-writable data (base/, tools/, output/, mixes/).

    Frozen as a PyInstaller .exe, that's the folder the .exe lives in (NOT the
    temp _MEIPASS extraction dir). Running from source, it's the repo root
    (two levels up from this file).
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_dir():
    """Folder that holds read-only bundled resources (data/afs_manifest.json).

    Frozen, PyInstaller extracts --add-data resources under sys._MEIPASS; from
    source it's the same as app_dir()."""
    return getattr(sys, "_MEIPASS", app_dir())


# Windows flag to keep helper subprocesses (ffmpeg, reg) from flashing a console
# when we run as a --windowed GUI exe.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0

ROOT = app_dir()
BASE = os.path.join(ROOT, "base")
TOOLS = os.path.join(ROOT, "tools")
OUTPUT = os.path.join(ROOT, "output")
MIXES = os.path.join(ROOT, "mixes")          # users drop .cdi/.zip mixes here

STOCK_DC_CDI = os.path.join(BASE, "MVC2_STOCK_DC.cdi")
STOCK_STEAM_ARC = os.path.join(BASE, "stock_game_50.arc")
STOCK_MUSIC = os.path.join(BASE, "stock_music")   # 30 true-stock .sngw (reset-to-stock)
FFMPEG = os.path.join(TOOLS, "ffmpeg.exe")

# Fighting Collection Steam App ID.
_APPID = "2634890"
_DEFAULT_STEAM = r"C:\Program Files (x86)\Steam\steamapps\common\MARVEL vs. CAPCOM Fighting Collection"

# Manual override (used when the game is on another drive / auto-detect fails).
# A plain text file next to the exe holding the install folder path.
STEAM_OVERRIDE = os.path.join(ROOT, "steam_path.txt")


def _read_override():
    try:
        if os.path.exists(STEAM_OVERRIDE):
            return open(STEAM_OVERRIDE, encoding="utf-8").read().strip() or None
    except Exception:
        pass
    return None


def set_steam_root(path):
    """Persist a manual Steam-install override (folder that contains
    nativeDX11x64\\...\\game_50.arc)."""
    with open(STEAM_OVERRIDE, "w", encoding="utf-8") as fh:
        fh.write((path or "").strip())


def _reg_install_location():
    try:
        out = subprocess.run(
            ["reg", "query",
             rf"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Steam App {_APPID}",
             "/v", "InstallLocation"],
            capture_output=True, text=True, creationflags=NO_WINDOW)
        for line in out.stdout.splitlines():
            if "InstallLocation" in line:
                # tokens: InstallLocation  REG_SZ  <path...>
                parts = line.split("REG_SZ")
                if len(parts) == 2:
                    return parts[1].strip()
    except Exception:
        pass
    return None


def steam_root():
    """Return the Fighting Collection install folder, or None.

    Order: manual override -> registry auto-detect -> common default path."""
    for cand in (_read_override(), _reg_install_location(), _DEFAULT_STEAM):
        if cand and os.path.isdir(cand):
            return cand
    return None


def steam_arc(root=None):
    root = root or steam_root()
    return os.path.join(root, "nativeDX11x64", "arc", "pc", "game_50.arc") if root else None


def steam_music_dir(root=None):
    root = root or steam_root()
    return os.path.join(root, "nativeDX11x64", "sound", "bgm", "mvc2", "wav") if root else None


def check():
    """Return (ok, list_of_problems) for the essentials needed to install mixes
    into Steam (DC->Steam). The stock DC .cdi is only needed to BUILD a Dreamcast
    disc (Steam->DC) and is checked there, so it isn't required here."""
    problems = []
    if not os.path.exists(STOCK_STEAM_ARC):
        problems.append(f"missing stock Steam arc: {STOCK_STEAM_ARC}")
    if not os.path.exists(FFMPEG):
        problems.append(f"missing ffmpeg: {FFMPEG}")
    if not steam_root():
        problems.append("Steam Fighting Collection install not found")
    return (not problems), problems
