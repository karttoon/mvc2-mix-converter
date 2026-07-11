========================================================================
  MARVEL VS. CAPCOM 2  -  MIX CONVERTER
========================================================================

Move mods between a Dreamcast disc (.cdi) and the Steam "Marvel vs.
Capcom Fighting Collection". No Python, no setup scripts.

------------------------------------------------------------------------
HOW TO START
------------------------------------------------------------------------
1. Unzip this whole folder somewhere (keep the files together).
2. Double-click  MixConverter.exe.

Windows SmartScreen may warn about an unknown publisher the first time
(the app isn't code-signed). Click "More info" -> "Run anyway".

------------------------------------------------------------------------
FIRST TIME: SET UP YOUR STOCK FILES  (tab "1. Setup")
------------------------------------------------------------------------
This tool ships with NO game data - you supply your own from the game
you already own.

  * In Steam, right-click the Fighting Collection -> Properties ->
    Installed Files -> "Verify integrity of game files" first, so your
    baseline is clean.
  * In MixConverter, click "Copy my stock files from Steam".

That's it for installing mixes into Steam.

To also BUILD a Dreamcast disc from your Steam changes, click
"Add a stock Dreamcast disc (.cdi)..." and point it at a stock MvC2
Dreamcast image (you provide this).

------------------------------------------------------------------------
WHAT IT DOES
------------------------------------------------------------------------
  2. Install into Steam  - take a Dreamcast mix (.cdi / .zip) and apply
     its stages, colors, HUD/effects and music to your Steam game. Your
     current files are backed up automatically first.

  3. Build a Disc        - take your Steam colors/HUD/effects/stages/
     music and write them into a Dreamcast .cdi you can load in Flycast
     or burn to DVD-R. You can patch onto a fresh stock disc or on top
     of an existing modded disc.

  4. Restore / Reset     - undo a mix (restore a backup) or wipe back to
     the clean stock baseline.

After installing or resetting, fully quit and relaunch Steam to play.

------------------------------------------------------------------------
FOLDERS
------------------------------------------------------------------------
  base\     your stock files land here (from Setup)
  mixes\    drop Dreamcast mixes here for quick access (optional)
  output\   built discs and automatic backups go here
  tools\    bundled ffmpeg (music conversion) - don't delete

Made by the MvC2 modding community.
