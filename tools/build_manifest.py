#!/usr/bin/env python3
"""build_manifest.py - Generate the canonical AFS-index <-> DC-filename manifest.

The Steam mvsc2 AFS blob stores files by index with no names. We recover names
by md5-anchoring each entry against known-stock references:
  * stock Steam md5s from the mod manager's mvcc_files.json
  * stock Dreamcast md5s walked from a stock .cdi

We also test whether the AFS index order equals the DC ISO9660 walk order; if so
we can name even user-modified slots positionally.

Output: data/afs_manifest.json
  { "count": N,
    "entries": [ {idx, name, size, dc_md5, steam_md5, portable}, ... ] }

`portable` = the stock DC file and stock Steam file are byte-identical, so this
slot can be ported 1:1 between platforms by filename.
"""
import json, hashlib, sys, os, argparse
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "mixconv"))
import disc as M
from mixconv.afs import AfsBlob

def md5(b): return hashlib.md5(b).hexdigest()

def load_steam_manifest(json_path):
    j = json.load(open(json_path))
    sep = "mvsc2\\"
    out = {}
    for k, v in j.items():
        if sep in k and not k.endswith("mvsc2.21D3D8A7"):
            out[k.split(sep, 1)[1].upper()] = (v["md5"], v["size"])
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blob", required=True, help="a stock game_50.arc OR an extracted mvsc2 blob")
    ap.add_argument("--cdi", required=True, help="stock DC .cdi")
    ap.add_argument("--steam-json", required=True, help="mvcc_files.json")
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "afs_manifest.json"))
    a = ap.parse_args()

    steam = load_steam_manifest(a.steam_json)            # name -> (md5,size)
    iso, sl = M.build_iso(a.cdi)
    dc_walk = M.walk_iso(iso, sl)
    dc = {n.upper(): iso[p*2048:p*2048+s] for n, p, s in dc_walk}
    dc_md5 = {n: md5(b) for n, b in dc.items()}

    # stock md5 -> name (prefer a unique name)
    md5_to_name = {}
    for n, (h, _) in steam.items():
        md5_to_name.setdefault(h, n)
    for n, h in dc_md5.items():
        md5_to_name.setdefault(h, n)

    raw = open(a.blob, "rb").read()
    if raw[:4] == b"ARC\x00":                    # accept a game_50.arc directly
        import steam as _S
        raw = _S.read_arc(a.blob)
    blob = AfsBlob.parse(raw)
    n = len(blob.entries)

    # positional alignment test vs DC walk order
    dc_names_order = [nm.upper() for nm, _, _ in dc_walk]
    best = (0, 0)
    for shift in range(-4, 5):
        agree = 0
        for i, e in enumerate(blob.entries):
            if not e:
                continue
            j = i + shift
            if 0 <= j < len(dc_names_order) and dc_names_order[j] in dc_md5 \
               and md5(e) == dc_md5[dc_names_order[j]]:
                agree += 1
        if agree > best[1]:
            best = (shift, agree)
    print(f"DC-walk-order positional best shift={best[0]} agree={best[1]}")

    entries = []
    named = anon = 0
    for i, e in enumerate(blob.entries):
        h = md5(e) if e else None
        name = md5_to_name.get(h)
        if name is None and e:
            anon += 1
        elif name:
            named += 1
        # steam_md5 = the ACTUAL stock-arc entry (the bytes we inject into), NOT
        # mvcc_files.json (which is a different build and mismarked e.g. DM*TEX).
        # portable = this file is byte-identical between stock DC and stock Steam,
        # so a mod's version of it can be copied whole-file across platforms.
        dmd5 = dc_md5.get(name) if name else None
        portable = bool(name and e and dmd5 and h == dmd5)
        entries.append({
            "idx": i,
            "name": name,
            "size": len(e),
            "dc_md5": dmd5,
            "steam_md5": h,
            "portable": portable,
        })
    out = {"count": n, "named": named, "anon": anon, "entries": entries}
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(out, open(a.out, "w"), indent=1)
    print(f"entries={n} named={named} anon(modified/unknown)={anon}")
    portable = sum(1 for x in entries if x["portable"])
    print(f"portable (stock DC==stock Steam): {portable}")
    print(f"written {a.out}")

if __name__ == "__main__":
    main()
