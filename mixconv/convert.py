#!/usr/bin/env python3
"""convert.py - orchestrate DC <-> Steam mix conversion.

v1 scope: whole-file portable files (stages, portraits, char-select, UI, effects)
are copied 1:1. Palette (PL??_DAT.BIN) and music files are detected and reported
as "not yet ported" (phase 2). Everything else is reported as unconvertible.
"""
import os, sys, hashlib, argparse
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import disc as D
from afs import AfsBlob, EntryTooLarge
from manifest import Manifest, WHOLE_FILE, PALETTE, MUSIC, REPORT
import steam
import dc_oversize
import palette as pal
import music as musicmod


def md5(b): return hashlib.md5(b).hexdigest()


def read_cdi(path):
    iso, sl = D.build_iso(path)
    return {n.upper(): iso[p * 2048:p * 2048 + s] for n, p, s in D.walk_iso(iso, sl)}


def diff(mix, stock):
    """Return {name: bytes} of files present+changed (or new) in the mix."""
    out = {}
    for n, b in mix.items():
        if n not in stock or md5(b) != md5(stock[n]):
            out[n] = b
    return out


def dc_to_steam(mix_cdi, stock_arc, out_arc, blob_out=None,
                files_out=None, music_out=None):
    man = Manifest()
    mix = read_cdi(mix_cdi)
    # Detect what the mix changed using the shipped stock-DC md5s in the manifest,
    # so no stock DC disc is needed for DC->Steam. A file counts as changed if it
    # exists in the manifest (i.e. is a real DC+Steam game file) and differs from
    # its stock DC md5. DC-only / unknown files aren't convertible and are skipped.
    changed = {}
    for n, b in mix.items():
        e = man.by_name.get(n)
        if e and e.get("dc_md5") and md5(b) != e["dc_md5"]:
            changed[n] = b
    print(f"DC mix changed {len(changed)} game files vs stock")

    plan = {WHOLE_FILE: [], PALETTE: [], MUSIC: [], REPORT: []}
    for name in sorted(changed):
        plan[man.classify(name)].append(name)

    blob = AfsBlob.parse(steam.read_arc(stock_arc))

    ported, pal_ported, skipped, grown = [], [], [], []
    for name in plan[WHOLE_FILE]:
        idx = man.idx(name)
        newb = changed[name]
        old = len(blob.entries[idx])
        blob.replace(idx, newb)                 # AFS relayout handles any size
        ported.append(name)
        if len(newb) != old:
            grown.append((name, old, len(newb)))

    pal_notes = []
    for name in plan[PALETTE]:
        idx = man.idx(name)
        steam_stock = blob.entries[idx]
        try:
            new_steam, note = pal.build_target_dat(changed[name], steam_stock)
        except ValueError as ex:
            skipped.append((name, str(ex)))
            continue
        blob.replace(idx, new_steam)          # same size as stock Steam slot
        pal_ported.append(name)
        if note:
            pal_notes.append((name, note))

    # --- music: transcode changed DC ADX -> Steam .sngw (drop into the Steam
    #     sound/bgm/mvc2/wav folder; music lives OUTSIDE the arc) ---
    music_done, music_fail = [], []
    if music_out and plan[MUSIC]:
        ff = musicmod.find_ffmpeg()
        if not ff:
            music_fail = [(n, "ffmpeg not found") for n in plan[MUSIC]]
        else:
            os.makedirs(music_out, exist_ok=True)
            for name in plan[MUSIC]:
                sngw = musicmod.adx_name_to_sngw(name)
                if not sngw:
                    music_fail.append((name, "no .sngw name")); continue
                try:
                    ogg = musicmod.adx_to_sngw(changed[name], ff)
                    open(os.path.join(music_out, sngw), "wb").write(ogg)
                    music_done.append((name, sngw))
                except Exception as ex:
                    music_fail.append((name, str(ex)[:60]))

    # --- named-file output: drop-in files for the community mvsc2-folder workflow
    #     (unpack game_50.arc into a folder of named files, drop these in, repack) ---
    if files_out:
        os.makedirs(files_out, exist_ok=True)
        for name in ported + pal_ported:
            with open(os.path.join(files_out, name), "wb") as fh:
                fh.write(blob.entries[man.idx(name)])

    if blob_out or out_arc:
        built = blob.build()
        if blob_out:
            os.makedirs(os.path.dirname(os.path.abspath(blob_out)), exist_ok=True)
            open(blob_out, "wb").write(built)
        if out_arc:
            steam.write_arc(built, out_arc, stock_arc)

    # ---- report ----
    print("\n=== conversion report (DC -> Steam) ===")
    print(f"ported (whole-file): {len(ported)}")
    for n in ported:
        print(f"   OK  {n}")
    if grown:
        print(f"   ({len(grown)} resized -> AFS repacked: " +
              ", ".join(f"{n} {a}->{b}B" for n, a, b in grown[:6]) +
              (" ..." if len(grown) > 6 else "") + ")")
    if pal_ported:
        print(f"palettes region-ported: {len(pal_ported)}")
        for n, note in pal_notes:
            print(f"   ~   {n}: {note}")
    if music_done:
        print(f"music transcoded ADX->.sngw: {len(music_done)}  (drop into Steam sound\\bgm\\mvc2\\wav)")
        for n, s in music_done:
            print(f"   OK  {n} -> {s}")
    if music_fail:
        print(f"music not transcoded: {len(music_fail)}")
        for n, why in music_fail:
            print(f"   XX  {n}: {why}")
    elif plan[MUSIC] and not music_out:
        print(f"music changed: {len(plan[MUSIC])} (pass --music-out to transcode to .sngw)")
    if plan[REPORT]:
        print(f"cannot convert (not portable between platforms): {len(plan[REPORT])}")
        for n in plan[REPORT]:
            print(f"   XX  {n}")
    for n, why in skipped:
        print(f"   SKIP {n}: {why}")
    print(f"\nwrote {out_arc}")
    return out_arc, ported


def steam_to_dc(mix_arc, stock_cdi, out_cdi, music_dir=None, stock_music_dir=None,
                conflict_mode="steam"):
    """Build a bootable DC .cdi from a Steam game_50.arc mix.

    Whole-file portable changes and region-ported palettes are written into the
    disc; oversized files (custom stages, and transcoded music) grow the disc via
    dc_oversize.grow_cdi. If music_dir is given, changed Steam .sngw are transcoded
    to DC ADX and appended.

    A CONFLICT is a file that BOTH the base disc modified (vs true stock DC) and
    the Steam side changed. conflict_mode decides who wins: "steam" (default,
    overwrite the disc's version) or "disc" (keep the base disc's version).
    """
    man = Manifest()
    stock_steam_md5 = {e["idx"]: e["steam_md5"] for e in man.entries}
    name_by_idx = {e["idx"]: e["name"] for e in man.entries}

    stock_dc = read_cdi(stock_cdi)                    # the BASE disc's files
    mix = AfsBlob.parse(steam.read_arc(mix_arc))

    changed = []  # (name, mix_bytes)
    for i, e in enumerate(mix.entries):
        if e and stock_steam_md5.get(i) and md5(e) != stock_steam_md5[i]:
            nm = name_by_idx.get(i)
            if nm:
                changed.append((nm, e))
    print(f"Steam mix changed {len(changed)} files vs stock Steam")

    files = {}                     # NAME -> DC-format bytes to patch
    plan = {WHOLE_FILE: [], PALETTE: [], MUSIC: [], REPORT: []}
    problems = []
    conflicts_over, conflicts_kept = [], []           # base-modified files
    for name, mixbytes in changed:
        disp = man.classify(name)
        plan[disp].append(name)
        # conflict = the base disc already modified this file vs true stock DC
        base_file = stock_dc.get(name)
        dcmd5 = man.by_name.get(name, {}).get("dc_md5")
        conflict = base_file is not None and dcmd5 and md5(base_file) != dcmd5
        if conflict and conflict_mode == "disc":
            conflicts_kept.append(name)               # keep the disc's version
            continue
        if conflict:
            conflicts_over.append(name)               # Steam overwrites the disc
        if disp == WHOLE_FILE:
            files[name] = mixbytes
        elif disp == PALETTE:
            dc_stock = stock_dc.get(name)
            if dc_stock is None:
                problems.append((name, "no stock DC file")); continue
            try:
                files[name], _ = pal.build_target_dat(mixbytes, dc_stock)
            except ValueError as ex:
                problems.append((name, str(ex)))

    # --- music: transcode the FULL Steam .sngw set -> DC ADX (appended, oversized)
    #     so the disc is a complete copy of your Steam audio, including menu tracks
    #     the mix itself didn't change. (stock_music_dir kept for API compat/unused) ---
    music_ported = []
    if music_dir and os.path.isdir(music_dir):
        ff = musicmod.find_ffmpeg()
        for f in sorted(os.listdir(music_dir)):
            if not f.lower().endswith(".sngw"):
                continue
            adx_name = musicmod.sngw_name_to_adx(f)
            if not adx_name or adx_name.upper() not in stock_dc:
                continue
            try:
                files[adx_name] = musicmod.sngw_to_adx(
                    open(os.path.join(music_dir, f), "rb").read(), ff)
                music_ported.append((f, adx_name, len(files[adx_name])))
            except Exception as ex:
                problems.append((f, str(ex)[:60]))

    patched, appended, cskip = dc_oversize.grow_cdi(stock_cdi, out_cdi, files)

    print("\n=== conversion report (Steam -> DC) ===")
    print(f"written into disc: {len(patched)+len(appended)}  "
          f"(in-place {len(patched)}, appended/oversized {len(appended)})")
    print(f"   stages/UI: {len([n for n in patched if not n.startswith('PL')])} in-place, "
          f"{len([a for a in appended if not a[0].startswith(('PL','ADX'))])} oversized")
    print(f"   palettes: {len([n for n in patched if n.startswith('PL')])}")
    if music_ported:
        print(f"   music (transcoded .sngw->ADX, appended): {len(music_ported)}")
        for f, adx, sz in music_ported[:6]:
            print(f"      {f} -> {adx} ({sz//1024}KB)")
        if len(music_ported) > 6:
            print(f"      ... +{len(music_ported)-6} more")
    if conflicts_over:
        print(f"\nconflicts (base disc also modified these; STEAM version won): {len(conflicts_over)}")
        for n in conflicts_over:
            print(f"   >>  {n}  (disc's version replaced by your Steam version)")
    if conflicts_kept:
        print(f"\nconflicts (base disc also modified these; DISC version KEPT): {len(conflicts_kept)}")
        for n in conflicts_kept:
            print(f"   ==  {n}  (kept the disc's version; your Steam change skipped)")
    if plan[REPORT]:
        print(f"cannot convert (not portable between platforms): {len(plan[REPORT])}  {plan[REPORT]}")
    for n, why in cskip + problems:
        print(f"   SKIP {n}: {why}")
    print(f"\nwrote {out_cdi}")
    return out_cdi, patched + [a[0] for a in appended]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a1 = sub.add_parser("dc2steam")
    a1.add_argument("--mix-cdi", required=True)
    a1.add_argument("--stock-arc", required=True, help="stock game_50.arc to inject into")
    a1.add_argument("--out", help="output game_50.arc")
    a1.add_argument("--blob-out", help="write the raw mvsc2 blob")
    a1.add_argument("--files-out", help="write changed named files to a folder")
    a1.add_argument("--music-out", help="transcode changed music to .sngw into this dir")
    a2 = sub.add_parser("steam2dc")
    a2.add_argument("--mix-arc", required=True)
    a2.add_argument("--stock-cdi", required=True, help="stock DC .cdi to build the disc from")
    a2.add_argument("--out", required=True)
    a2.add_argument("--music-dir", help="Steam sound\\bgm\\mvc2\\wav to port music from")
    a = ap.parse_args()
    if a.cmd == "dc2steam":
        dc_to_steam(a.mix_cdi, a.stock_arc, a.out, a.blob_out, a.files_out, a.music_out)
    else:
        steam_to_dc(a.mix_arc, a.stock_cdi, a.out, music_dir=a.music_dir)
