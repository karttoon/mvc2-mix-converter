#!/usr/bin/env python3
"""manifest.py - load the canonical AFS index<->name map and classify files."""
import json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT = os.path.join(os.path.dirname(HERE), "data", "afs_manifest.json")

# Dispositions for how a changed file crosses platforms.
WHOLE_FILE = "whole_file"   # byte-identical stock format -> copy the whole file
PALETTE = "palette"         # PL??_DAT.BIN -> copy only the palette region
MUSIC = "music"             # ADX_*/SNGW -> transcode
REPORT = "report"           # not portable between platforms -> cannot convert, report it


class Manifest:
    def __init__(self, path=DEFAULT):
        m = json.load(open(path))
        self.entries = m["entries"]
        self.by_name = {e["name"]: e for e in self.entries if e["name"]}
        self.name_to_idx = {e["name"]: e["idx"] for e in self.entries if e["name"]}
        self.portable = {e["name"] for e in self.entries if e["portable"]}

    def classify(self, name: str) -> str:
        n = name.upper()
        if n in self.portable:
            return WHOLE_FILE
        if re.fullmatch(r"PL[0-9A-F]{2}_DAT\.BIN", n):
            return PALETTE
        if n.startswith("ADX_") or n.endswith(".SNGW"):
            return MUSIC
        return REPORT

    def idx(self, name):
        return self.name_to_idx.get(name.upper())
