#!/usr/bin/env python3
"""config.py - resolve all paths the converter needs (Steam install, bases, tools).

Auto-detects the Steam Fighting Collection install from the registry (same App IDs
the community CollectionTool.bat uses), with fallbacks to the common default path.
"""
import os, subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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


def _reg_install_location():
    try:
        out = subprocess.run(
            ["reg", "query",
             rf"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Steam App {_APPID}",
             "/v", "InstallLocation"],
            capture_output=True, text=True)
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
    """Return the Fighting Collection install folder, or None."""
    for cand in (_reg_install_location(), _DEFAULT_STEAM):
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
