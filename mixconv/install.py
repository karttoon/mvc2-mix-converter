#!/usr/bin/env python3
"""install.py - high-level install/restore for the terminal front-end.

DC -> Steam: back up the live Steam arc + music, convert the DC mix, patch the arc
in place and drop the .sngw music into the Steam folder.

Steam -> DC: build a burnable .cdi from a Steam arc (defaults to the live one).
"""
import os, shutil, time, zipfile, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
import config
import convert


# --------------------------------------------------------------- helpers
def _prep_mix_cdi(mix_path, workdir):
    """Accept a .cdi directly, or a .zip containing one -> return a .cdi path."""
    if mix_path.lower().endswith(".cdi"):
        return mix_path
    if mix_path.lower().endswith(".zip"):
        z = zipfile.ZipFile(mix_path)
        cdis = [n for n in z.namelist() if n.lower().endswith(".cdi")]
        if not cdis:
            raise ValueError("no .cdi inside " + os.path.basename(mix_path))
        os.makedirs(workdir, exist_ok=True)
        z.extract(cdis[0], workdir)
        return os.path.join(workdir, cdis[0])
    raise ValueError("mix must be a .cdi or a .zip containing one")


def _timestamp():
    return time.strftime("%Y%m%d_%H%M%S")


# --------------------------------------------------------------- DC -> Steam
def install_dc_to_steam(mix_path, progress=print):
    ok, problems = config.check()
    if not ok:
        raise RuntimeError("setup incomplete:\n  " + "\n  ".join(problems))
    root = config.steam_root()
    live_arc = config.steam_arc(root)
    music_dir = config.steam_music_dir(root)

    # 1. back up current live state (undo point)
    bdir = os.path.join(config.OUTPUT, "backups", "steam_" + _timestamp())
    os.makedirs(bdir, exist_ok=True)
    progress(f"Backing up your current Steam files -> {bdir}")
    shutil.copyfile(live_arc, os.path.join(bdir, "game_50.arc"))
    mbak = os.path.join(bdir, "music")
    os.makedirs(mbak, exist_ok=True)
    for f in os.listdir(music_dir):
        if f.lower().endswith(".sngw"):
            shutil.copyfile(os.path.join(music_dir, f), os.path.join(mbak, f))

    # 2. convert the mix straight onto the live install (no stock DC disc needed)
    work = tempfile.mkdtemp(prefix="mixconv_inst_")
    try:
        mix_cdi = _prep_mix_cdi(mix_path, os.path.join(work, "mix"))
        progress("Converting mix (stages, palettes, HUD/effects, music)...")
        convert.dc_to_steam(mix_cdi, config.STOCK_STEAM_ARC,
                            out_arc=live_arc, music_out=music_dir)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    progress("\nDone. Your mix is installed. Fully quit & relaunch Steam to play.")
    progress(f"To undo: restore files from {bdir}")
    return bdir


# --------------------------------------------------------------- Steam -> DC
def build_dc_from_steam(out_cdi, mix_arc=None, base_cdi=None, conflict_mode="steam",
                        progress=print):
    """Build/patch a DC .cdi from the Steam install.

    base_cdi is the disc to patch your Steam changes onto. Default = the bundled
    stock DC disc (a fresh disc). Pass any other .cdi (e.g. one built on the
    Paxtez site with custom stages) to patch your Steam colors/HUD/etc. on top of
    it, keeping that disc's mods where the Steam side didn't also change them.

    conflict_mode ("steam"|"disc") decides who wins where both the base disc and
    your Steam install changed the same file.
    """
    ok, problems = config.check()
    if not ok:
        raise RuntimeError("setup incomplete:\n  " + "\n  ".join(problems))
    base = base_cdi or config.STOCK_DC_CDI
    if not os.path.exists(base):
        raise RuntimeError(
            "Need a base Dreamcast .cdi to patch onto:\n  " + base +
            "\n  (provide a stock disc in base/, or point at an existing .cdi).")
    mix_arc = mix_arc or config.steam_arc()
    progress(f"Base disc: {base}")
    progress(f"Reading Steam arc: {mix_arc}")
    progress("Including your Steam music (transcoding to DC ADX)...")
    convert.steam_to_dc(mix_arc, base, out_cdi,
                        music_dir=config.steam_music_dir(),
                        stock_music_dir=config.STOCK_MUSIC,
                        conflict_mode=conflict_mode,
                        stock_arc=config.STOCK_STEAM_ARC)
    progress(f"\nDone. Burnable/emulator-ready disc: {out_cdi}")
    return out_cdi


# --------------------------------------------------------------- first-run setup
def copy_stock_from_steam(progress=print):
    """Populate base/ with the user's CURRENT Steam arc + music as their backup /
    baseline. For a truly clean baseline they should Verify integrity in Steam
    first, but any current state works as a restore point. ffmpeg is bundled, so
    nothing is downloaded."""
    root = config.steam_root()
    if not root:
        raise RuntimeError("Steam Fighting Collection install not found")
    os.makedirs(config.BASE, exist_ok=True)
    progress("Copying your current Steam files as your backup...")
    shutil.copyfile(config.steam_arc(root), config.STOCK_STEAM_ARC)
    progress(f"  game_50.arc -> {config.STOCK_STEAM_ARC}")
    os.makedirs(config.STOCK_MUSIC, exist_ok=True)
    wav = config.steam_music_dir(root)
    n = 0
    for f in os.listdir(wav):
        if f.lower().endswith(".sngw"):
            shutil.copyfile(os.path.join(wav, f), os.path.join(config.STOCK_MUSIC, f))
            n += 1
    progress(f"  {n} music tracks -> {config.STOCK_MUSIC}")
    progress("\nBackup created. You're ready to install mixes into Steam.")
    return n


def set_stock_dc(cdi_path, progress=print):
    """Copy a user-provided stock Dreamcast .cdi into base/ (needed only to BUILD
    Dreamcast discs, Steam -> DC)."""
    if not cdi_path or not os.path.exists(cdi_path):
        raise RuntimeError("file not found: " + str(cdi_path))
    os.makedirs(config.BASE, exist_ok=True)
    progress("Copying stock Dreamcast disc...")
    shutil.copyfile(cdi_path, config.STOCK_DC_CDI)
    progress(f"  -> {config.STOCK_DC_CDI}\nYou can now build Dreamcast discs.")


# --------------------------------------------------------------- reset to stock
def reset_to_stock(progress=print):
    """Overwrite the live Steam arc + music with the bundled true-stock baseline."""
    root = config.steam_root()
    if not root:
        raise RuntimeError("Steam Fighting Collection install not found")
    if not os.path.exists(config.STOCK_STEAM_ARC) or not os.path.isdir(config.STOCK_MUSIC):
        raise RuntimeError("stock baseline missing from base/ (arc / stock_music)")
    shutil.copyfile(config.STOCK_STEAM_ARC, config.steam_arc(root))
    progress("restored stock game_50.arc")
    wav = config.steam_music_dir(root)
    n = 0
    for f in os.listdir(config.STOCK_MUSIC):
        if f.lower().endswith(".sngw"):
            shutil.copyfile(os.path.join(config.STOCK_MUSIC, f), os.path.join(wav, f))
            n += 1
    progress(f"restored {n} stock music tracks")
    progress("\nGame reset to stock. Fully quit & relaunch Steam.")


# --------------------------------------------------------------- restore
def restore_steam(backup_dir, progress=print):
    root = config.steam_root()
    live_arc = config.steam_arc(root)
    music_dir = config.steam_music_dir(root)
    arc = os.path.join(backup_dir, "game_50.arc")
    if os.path.exists(arc):
        shutil.copyfile(arc, live_arc)
        progress("restored game_50.arc")
    mbak = os.path.join(backup_dir, "music")
    if os.path.isdir(mbak):
        for f in os.listdir(mbak):
            shutil.copyfile(os.path.join(mbak, f), os.path.join(music_dir, f))
        progress(f"restored {len(os.listdir(mbak))} music files")
