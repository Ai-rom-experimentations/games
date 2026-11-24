#!/bin/sh
# Builds the C-BIOS MSX2 ROMs the browser build boots, from C-BIOS source.
#
#   tools/build_cbios.sh /path/to/cbios-checkout
#
# C-BIOS ships sources and configs but no binaries in its git tree; its
# Makefile wants pasmo, and we already have sjasmplus for the game, which
# assembles every file clean.  The ROMs land in the machine folder the
# libretro core reads, and must be named exactly as that config.ini says.
set -eu

SRC=${1:-}
SJASMPLUS=${SJASMPLUS:-sjasmplus}
HERE=$(cd "$(dirname "$0")" && pwd)
DEST="$HERE/../web/core/bios/Machines/MSX2 - C-BIOS - V9958"

if [ -z "$SRC" ] || [ ! -d "$SRC/src" ]; then
    echo "usage: $0 /path/to/cbios-checkout" >&2
    exit 2
fi

mkdir -p "$SRC/derived/asm" "$DEST"
printf '  db "C-BIOS"\n' > "$SRC/derived/asm/version.asm"

for part in main_msx2 logo_msx2 sub music; do
    "$SJASMPLUS" -i"$SRC/src" -i"$SRC/derived/asm" \
        --raw="$DEST/cbios_$part.rom" "$SRC/src/$part.asm"
done

cp "$SRC/configs/blueMSX/MSX2 - C-BIOS/config.ini" "$DEST/config.ini"
# an MSX2 board with a V9958 fitted, which is what this game targets
sed -i 's/^version=.*/version=V9958/; s/^vram size=.*/vram size=128kB/' \
    "$DEST/config.ini"
sed -i 's/^Enable CMOS=1/Enable CMOS=0/; s/^Battery Backed=1/Battery Backed=0/' \
    "$DEST/config.ini"

[ -f "$DEST/cbios.txt" ] || cp "$HERE/../web/core/bios/Machines/MSX - C-BIOS/cbios.txt" "$DEST/cbios.txt"

ls -l "$DEST"
