# deltarune-race - the Deltarune Chapter 3 hidden racing minigame, SG-1000
#
#   make          assemble deltarune.sg
#   make check    run the ROM in the bundled emulator (screenshots + checks)
#   make clean

SJASMPLUS ?= sjasmplus
PYTHON    ?= python3

all: deltarune.sg

gfx.asm: tools/gen_gfx.py
	$(PYTHON) tools/gen_gfx.py

deltarune.sg: deltarune.asm gfx.asm
	@command -v $(SJASMPLUS) >/dev/null 2>&1 || { \
	  echo ""; \
	  echo "sjasmplus was not found."; \
	  echo "Build it from https://github.com/z00m128/sjasmplus or run:"; \
	  echo "  make SJASMPLUS=/path/to/sjasmplus"; \
	  echo ""; exit 1; }
	$(SJASMPLUS) --raw=deltarune.sg deltarune.asm

check: deltarune.sg
	$(PYTHON) tools/capture.py

# optional: the same ROM on the real Gearsystem core (build tools/gsrun.cpp
# against Gearsystem first, see README)
crosscheck: deltarune.sg
	$(PYTHON) tools/crosscheck.py $(EMU)

clean:
	rm -f deltarune.sg
	rm -rf tools/__pycache__

.PHONY: all check crosscheck clean

