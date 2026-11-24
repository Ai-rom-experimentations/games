# dino - CHROME DINO, a endless runner for the MSX
#
#   make          assemble dino.rom (the cartridge) and the stand-in BIOS
#   make check    run the ROM in the bundled emulator (screenshots + checks)
#   make preview  render the tiles and the title into /tmp, to look at the art
#   make mx1      the same ROM as dino.mx1, for emulators that go by suffix
#   make serve    host web/ on http://localhost:8000 (the browser build)
#   make web-check  run the browser build's core headless, under node
#   make clean

SJASMPLUS ?= sjasmplus
PYTHON    ?= python3
NODE      ?= node
PORT      ?= 8000

all: dino.rom tools/bios.rom

gfx.asm: tools/gen_gfx.py
	$(PYTHON) tools/gen_gfx.py

dino.rom: dino.asm gfx.asm
	@command -v $(SJASMPLUS) >/dev/null 2>&1 || { \
	  echo ""; \
	  echo "sjasmplus was not found."; \
	  echo "Build it from https://github.com/z00m128/sjasmplus or run:"; \
	  echo "  make SJASMPLUS=/path/to/sjasmplus"; \
	  echo ""; exit 1; }
	$(SJASMPLUS) --raw=dino.rom dino.asm

# A cartridge ROM is enough on a real MSX, but the tests start the machine the
# way the BIOS would, so they need something in the BIOS slot that hands over
# to the cartridge and then stays out of the way.
tools/bios.rom: tools/bios.asm
	$(SJASMPLUS) --raw=tools/bios.rom tools/bios.asm

# Some emulators pick the console from the file extension, and .rom is also an
# Atari Jaguar extension.  `make mx1` writes the same 16 KB image under the
# MSX1 cartridge extension, which nothing else claims.
mx1: dino.rom
	cp dino.rom dino.mx1

check: dino.rom tools/bios.rom
	$(PYTHON) tools/capture.py

preview: gfx.asm
	$(PYTHON) tools/gen_gfx.py --preview

# The browser build is a static page in web/ running the cartridge on a
# WebAssembly MSX (blueMSX + C-BIOS).  It has to be served over http: ES
# modules and fetch() do not work from file:// URLs.
serve:
	@echo "CHROME DINO on http://localhost:$(PORT)/web/  (ctrl-c to stop)"
	$(PYTHON) -m http.server $(PORT) --bind 0.0.0.0

# Boots web/core the same way the page does and checks the game runs: needs
# node, no npm install.
web-check:
	$(NODE) web/check.mjs

clean:
	rm -f dino.rom dino.mx1 tools/bios.rom
	rm -rf tools/__pycache__

.PHONY: all check preview mx1 serve web-check clean
