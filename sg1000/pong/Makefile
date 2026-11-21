# sg1000 - homebrew titles for the Sega SG-1000
#
#   make          assemble pong.sg
#   make check    run the ROM in the bundled emulator (screenshots + checks)
#   make clean

SJASMPLUS ?= sjasmplus
PYTHON    ?= python3

all: pong.sg

gfx.asm: tools/gen_gfx.py
	$(PYTHON) tools/gen_gfx.py

pong.sg: pong.asm gfx.asm
	@command -v $(SJASMPLUS) >/dev/null 2>&1 || { \
	  echo ""; \
	  echo "sjasmplus was not found."; \
	  echo "Build it from https://github.com/z00m128/sjasmplus or run:"; \
	  echo "  make SJASMPLUS=/path/to/sjasmplus"; \
	  echo ""; exit 1; }
	$(SJASMPLUS) --raw=pong.sg pong.asm

check: pong.sg
	$(PYTHON) tools/capture.py

clean:
	rm -f pong.sg
	rm -rf tools/__pycache__

.PHONY: all check clean
