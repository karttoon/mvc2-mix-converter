r"""menu.py - MvC2 Mix Converter, terminal front-end (redraws in place, app-like).

Run:  py mixconv\menu.py     (or double-click MixConverter.bat)
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import config
import install

PAGE = 15
LINE = "=" * 62


def clear():
    os.system("cls" if os.name == "nt" else "clear")


def header(subtitle=""):
    clear()
    print(LINE)
    print("        MARVEL VS. CAPCOM 2   -   MIX CONVERTER")
    if subtitle:
        print("        " + subtitle)
    print(LINE)


def pause():
    input("\n  Press Enter to continue...")


def list_mixes():
    if not os.path.isdir(config.MIXES):
        return []
    return sorted(os.path.join(config.MIXES, f) for f in os.listdir(config.MIXES)
                  if f.lower().endswith((".cdi", ".zip", ".rar")))


def pick_mix(items):
    """Paged picker with stable, increasing global numbering. Returns path or None."""
    if not items:
        header("Install a DC mix")
        print(f"\n  No mixes found. Drop .cdi or .zip mixes into:\n    {config.MIXES}\n")
        pause()
        return None
    page = 0
    pages = (len(items) + PAGE - 1) // PAGE
    while True:
        start = page * PAGE
        chunk = items[start:start + PAGE]
        header(f"Install a DC mix   (page {page + 1}/{pages}, {len(items)} mixes)")
        print()
        for n, it in enumerate(chunk, start + 1):
            print(f"   [{n:3}] {os.path.basename(it)}")
        nav = []
        if page > 0:
            nav.append("[<] prev")
        if page < pages - 1:
            nav.append("[>] next")
        nav.append("[B] back")
        print("\n  " + "    ".join(nav))
        c = input("\n  Enter a number, or a command: ").strip().lower()
        if c == "b":
            return None
        if c == "<" and page > 0:
            page -= 1; continue
        if c == ">" and page < pages - 1:
            page += 1; continue
        if c.isdigit() and 1 <= int(c) <= len(items):
            return items[int(c) - 1]


def do_install():
    mix = pick_mix(list_mixes())
    if not mix:
        return
    header("Install a DC mix")
    print(f"\n  Mix:   {os.path.basename(mix)}")
    print(f"  Steam: {config.steam_root()}")
    print("\n  This backs up your current Steam arc + music, then installs the")
    print("  mix's stages, palettes, HUD/effects and music.")
    if input("\n  Proceed? [y/N] ").strip().lower() != "y":
        return
    print()
    try:
        install.install_dc_to_steam(mix, progress=lambda m: print("  " + str(m)))
    except Exception as e:
        print("\n  ERROR:", e)
    pause()


def do_build_dc():
    header("Build a Dreamcast disc from your Steam install")
    print("\n  Patches your Steam colors / HUD / effects / stages / music into a")
    print("  Dreamcast .cdi you can burn to DVD-R or load in an emulator (Flycast).")
    print("\n  Base disc to patch onto:")
    print("    - press Enter to build on a fresh STOCK disc, or")
    print("    - paste the path to an existing .cdi (e.g. one from the Paxtez site)")
    print("      to keep its mods and add your Steam changes on top.")
    base = input("\n  Base .cdi [stock]: ").strip().strip('"')
    if base and not os.path.exists(base):
        print("  not found."); pause(); return
    base_cdi = base or None
    conflict_mode = "steam"
    if base_cdi:
        print("\n  NOTE: patching onto a heavily-modified disc may not behave as")
        print("  expected. In particular, mixes that add EXTRA PALETTE SLOTS")
        print('  ("more colors for every character") relocate the palette data, so')
        print("  your Steam colors may only partly apply, or clash, for those chars.")
        print("  Stages, HUD, effects and music patch on top fine.")
        if input("\n  Continue? [y/N] ").strip().lower() != "y":
            return
        print("\n  If a file was changed by BOTH the disc and your Steam install,")
        print("  which should win?")
        print("     [S] your Steam version  (default)")
        print("     [D] keep the disc's version")
        if input("\n  > ").strip().lower() == "d":
            conflict_mode = "disc"
    print(f"\n  The disc is always saved into:\n    {config.OUTPUT}")
    name = input("\n  Output filename [MVC2_from_steam]: ").strip().strip('"') or "MVC2_from_steam"
    name = os.path.basename(name)                     # ignore any path the user typed
    if not name.lower().endswith(".cdi"):
        name += ".cdi"                                # auto-append .cdi
    out = os.path.join(config.OUTPUT, name)
    if input(f"\n  Build {name}? [y/N] ").strip().lower() != "y":
        return
    print()
    try:
        install.build_dc_from_steam(out, base_cdi=base_cdi, conflict_mode=conflict_mode,
                                    progress=lambda m: print("  " + str(m)))
    except Exception as e:
        print("\n  ERROR:", e)
    pause()


def do_restore():
    bdir = os.path.join(config.OUTPUT, "backups")
    backups = []
    if os.path.isdir(bdir):
        backups = sorted((os.path.join(bdir, d) for d in os.listdir(bdir)
                          if d.startswith("steam_") and os.path.isdir(os.path.join(bdir, d))),
                         reverse=True)
    if not backups:
        header("Restore from a backup")
        print("\n  No backups yet (they're made automatically when you install a mix).")
        pause()
        return
    header("Restore from a backup   (newest first)")
    print()
    for n, b in enumerate(backups[:PAGE], 1):
        print(f"   [{n:2}] {os.path.basename(b)}")
    print("\n  [B] back")
    c = input("\n  Enter a number: ").strip().lower()
    if not (c.isdigit() and 1 <= int(c) <= len(backups[:PAGE])):
        return
    b = backups[int(c) - 1]
    if input(f"\n  Restore {os.path.basename(b)} over your live Steam files? [y/N] ").strip().lower() == "y":
        print()
        try:
            install.restore_steam(b, progress=lambda m: print("  " + str(m)))
        except Exception as e:
            print("\n  ERROR:", e)
        pause()


def do_reset():
    header("Reset to stock")
    print("\n  Overwrites your live Steam arc + music with the clean stock baseline")
    print("  bundled with this tool (no Steam re-download needed).")
    if input("\n  Reset to stock now? [y/N] ").strip().lower() == "y":
        print()
        try:
            install.reset_to_stock(progress=lambda m: print("  " + str(m)))
        except Exception as e:
            print("\n  ERROR:", e)
        pause()


def main():
    while True:
        header()
        ok, problems = config.check()
        if not ok:
            print("\n  SETUP ISSUES:")
            for p in problems:
                print("    -", p)
        print("""
   [1] Install a DC mix into Steam        (DC  -> Steam)
   [2] Build a Dreamcast disc from Steam  (Steam -> DC)
   [3] Restore Steam from a backup
   [4] Reset Steam to stock
   [5] Exit
""")
        c = input("  > ").strip()
        if c == "1":
            do_install()
        elif c == "2":
            do_build_dc()
        elif c == "3":
            do_restore()
        elif c == "4":
            do_reset()
        elif c == "5":
            return


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nbye")
