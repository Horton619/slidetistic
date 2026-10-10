#!/usr/bin/env bash
# A minimal, LGPL-only ffprobe: file protocol + every demuxer and parser, no codecs, no external libs.
# That's all the engine asks of it (length, container, codec names, size); a few MB instead of
# Homebrew's GPL build with 36 libraries. Output: vendor/<mac|win>/ffprobe[.exe]
# Mac: needs Xcode command line tools. Windows: run inside MSYS2 MINGW64 (make, gcc, nasm not needed).
set -euo pipefail
cd "$(dirname "$0")/.."
FFMPEG_TAG=${FFMPEG_TAG:-n7.1.2}
case "$(uname -s)" in
  Darwin) PLAT=mac; EXE=; LDFLAGS= ;;
  MINGW*|MSYS*) PLAT=win; EXE=.exe; LDFLAGS=-static ;;   # no MinGW runtime DLLs to ship
  *) echo "unsupported platform" >&2; exit 1 ;;
esac
SRC=${FFMPEG_SRC:-build/ffmpeg-$FFMPEG_TAG}
if [ ! -d "$SRC" ]; then
  git clone --depth 1 --branch "$FFMPEG_TAG" https://github.com/FFmpeg/FFmpeg.git "$SRC"
fi
cd "$SRC"
./configure --disable-everything --disable-autodetect --disable-network --disable-doc --disable-debug \
  --disable-programs --enable-ffprobe --enable-protocol=file --enable-demuxers --enable-parsers \
  --enable-static --disable-shared --disable-x86asm --disable-iconv ${LDFLAGS:+--extra-ldflags=$LDFLAGS} > /dev/null
make -j"$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)" ffprobe$EXE > /dev/null
cd - > /dev/null
mkdir -p "vendor/$PLAT"
cp "$SRC/ffprobe$EXE" "vendor/$PLAT/ffprobe$EXE"
strip "vendor/$PLAT/ffprobe$EXE" 2>/dev/null || true
"vendor/$PLAT/ffprobe$EXE" -version | head -1
