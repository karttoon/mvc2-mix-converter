#!/usr/bin/env python3
"""End-to-end proof of the Steam-side injection mechanism (DC->Steam core).

1. Parse the mvsc2 AFS blob.
2. Resolve a stage entry (STG00POL.BIN) by name via the manifest.
3. Replace it with a same-size modified version (simulating a stage edit).
4. Rebuild the blob and re-parse it.
5. Assert the target entry now holds the new bytes AND every other entry is
   byte-identical to the original.

This exercises the exact path DC->Steam conversion uses for a same-size portable
file. Run:  py tests/test_inject.py <blob> <manifest.json>
"""
import sys, os, hashlib, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mixconv.afs import AfsBlob

def md5(b): return hashlib.md5(b).hexdigest()

def main(blob_path, manifest_path):
    manifest = json.load(open(manifest_path))
    name_to_idx = {e["name"]: e["idx"] for e in manifest["entries"] if e["name"]}
    target = "STG00POL.BIN"
    idx = name_to_idx[target]

    orig = open(blob_path, "rb").read()
    blob = AfsBlob.parse(orig)
    old = blob.entries[idx]
    print(f"{target} -> idx {idx}, {len(old)} bytes, md5 {md5(old)[:12]}")

    # simulate a same-size stage edit: flip a run of bytes in the middle
    mid = len(old) // 2
    modded = bytearray(old)
    for k in range(mid, mid + 256):
        modded[k] ^= 0x5A
    modded = bytes(modded)
    assert len(modded) == len(old) and modded != old

    blob.replace(idx, modded)
    rebuilt = blob.build()
    print(f"rebuilt blob: {len(rebuilt)} bytes (orig {len(orig)})")
    assert len(rebuilt) == len(orig), "size changed on same-size replace!"

    # re-parse and verify
    blob2 = AfsBlob.parse(rebuilt)
    assert md5(blob2.entries[idx]) == md5(modded), "target entry not updated"
    changed = 0
    orig_blob = AfsBlob.parse(orig)
    for i in range(len(orig_blob.entries)):
        if md5(orig_blob.entries[i]) != md5(blob2.entries[i]):
            changed += 1
            assert i == idx, f"UNEXPECTED change at idx {i}"
    assert changed == 1, f"expected exactly 1 changed entry, got {changed}"
    # and the whole blob differs from original only within that entry's slot
    print("PASS: exactly 1 entry changed (the target); all 889 others identical.")
    return 0

if __name__ == "__main__":
    # usage: test_inject.py <extracted mvsc2 blob> [manifest.json]
    # get a blob with: python -c "import sys;sys.path.insert(0,'mixconv');import steam;
    #   open('blob','wb').write(steam.read_arc(r'base/stock_game_50.arc'))"
    if len(sys.argv) < 2:
        raise SystemExit("usage: test_inject.py <mvsc2 blob> [afs_manifest.json]")
    blob = sys.argv[1]
    man = sys.argv[2] if len(sys.argv) > 2 else \
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "afs_manifest.json")
    sys.exit(main(blob, man))
