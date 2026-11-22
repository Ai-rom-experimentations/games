# aliens - ALIENS!, a Galaga style game for the MSX
#
#   make          assemble aliens.rom (the cartridge) and the stand-in BIOS
#   make check    run the ROM in the bundled emulator (screenshots + checks)
#   make preview  render the tiles and the title into /tmp, to look at the art
#   make mx1      the same ROM as aliens.mx1, for emulators that go by suffix
#   make clean

SJASMPLUS ?= sjasmplus
PYTHON    ?= python3

all: aliens.rom tools/bios.rom

gfx.asm: tools/gen_gfx.py
	$(PYTHON) tools/gen_gfx.py

aliens.rom: aliens.asm gfx.asm
	@command -v $(SJASMPLUS) >/dev/null 2>&1 || { \
	  echo ""; \
	  echo "sjasmplus was not found."; \
	  echo "Build it from https://github.com/z00m128/sjasmplus or run:"; \
	  echo "  make SJASMPLUS=/path/to/sjasmplus"; \
	  echo ""; exit 1; }
	$(SJASMPLUS) --raw=aliens.rom aliens.asm

# A cartridge ROM is enough on a real MSX, but the tests start the machine the
# way the BIOS would, so they need something in the BIOS slot that hands over
# to the cartridge and then stays out of the way.
tools/bios.rom: tools/bios.asm
	$(SJASMPLUS) --raw=tools/bios.rom tools/bios.asm

# Some emulators pick the console from the file extension, and .rom is also an
# Atari Jaguar extension.  `make mx1` writes the same 16 KB image under the
# MSX1 cartridge extension, which nothing else claims.
mx1: aliens.rom
	cp aliens.rom aliens.mx1

check: aliens.rom tools/bios.rom
	$(PYTHON) tools/capture.py

preview: gfx.asm
	$(PYTHON) tools/gen_gfx.py --preview

clean:
	rm -f aliens.rom aliens.mx1 tools/bios.rom
	rm -rf tools/__pycache__

.PHONY: all check preview mx1 clean
