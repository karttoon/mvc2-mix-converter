"""Throwaway: prove the frozen path shim in a real PyInstaller binary.

Built as a console onefile, dropped into a staged release folder, and run. It
imports the SAME engine modules the GUI uses and reports where they resolve.
Not shipped."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
# when frozen, mixconv is on the bundled path; from source add it
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "mixconv"))
import config, manifest, music

print("frozen        :", getattr(sys, "frozen", False))
print("sys.executable:", sys.executable)
print("_MEIPASS      :", getattr(sys, "_MEIPASS", "(none)"))
print("app_dir()     :", config.app_dir())
print("ROOT          :", config.ROOT)
print("FFMPEG        :", config.FFMPEG, "| exists:", os.path.exists(config.FFMPEG))
print("manifest path :", manifest.DEFAULT, "| exists:", os.path.exists(manifest.DEFAULT))
try:
    m = manifest.Manifest()
    print("manifest load : OK,", len(m.entries), "entries")
except Exception as e:
    print("manifest load : FAIL", e)
print("find_ffmpeg   :", music.find_ffmpeg())
ok, probs = config.check()
print("config.check  :", ok, probs)
