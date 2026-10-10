#!/usr/bin/env bash
# Bundle Poppler's pdftotext + pdftoppm (layout + slide images) into vendor/mac with their dylibs,
# rewritten to @executable_path/libs so they run on Macs without Homebrew.
# Needs: brew install poppler dylibbundler
set -euo pipefail
cd "$(dirname "$0")/.."
V=vendor/mac
rm -rf "$V/libs" "$V/pdftotext" "$V/pdftoppm"
mkdir -p "$V/libs"
BREW=$(brew --prefix)
cp "$BREW/bin/pdftotext" "$BREW/bin/pdftoppm" "$V/"
chmod u+w "$V"/pdftotext "$V"/pdftoppm
# Explicit -s search paths: Homebrew arm64 uses @rpath and dylibbundler otherwise stops to ask.
dylibbundler -od -b -x "$V/pdftotext" -x "$V/pdftoppm" -d "$V/libs/" -p @executable_path/libs/ \
  -s "$BREW/lib/" -s "$BREW/opt/poppler/lib/" > /dev/null 2>&1
if otool -L "$V"/pdftotext "$V"/pdftoppm "$V"/libs/* | grep -E "^\s+($BREW|/usr/local)"; then
  echo "bundled tools still point at Homebrew" >&2; exit 1
fi
"$V/pdftotext" -v 2>&1 | head -1
