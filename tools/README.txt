Put ffmpeg.exe here.

Download a Windows build (e.g. https://www.gyan.dev/ffmpeg/builds/ - the
"essentials" build is enough) and extract ffmpeg.exe into this folder:

  tools\ffmpeg.exe

It is used to transcode music between Steam (.sngw / Ogg Vorbis) and Dreamcast
(CRI ADX). It is not bundled because it is ~100 MB.

(The Steam game_50.arc is unpacked/repacked in pure Python - no other tool needed.)
