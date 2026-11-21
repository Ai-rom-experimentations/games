#!/usr/bin/env python3
"""Generates deltarune-race/gfx.asm (tile patterns + the track map) for the
SG-1000 rebuild of the hidden racing minigame from Deltarune Chapter 3.

The art lives here so it can be edited and previewed without an emulator:

    python3 tools/gen_gfx.py             # (re)write gfx.asm
    python3 tools/gen_gfx.py --preview   # also render PNG previews

The previews need pillow and are written to a temporary directory, so the
repository stays clean.

The screen is the whole race track, in 8x8 tiles (32x24 = 256x192 pixels):

      cols/rows 1..30 / 1..22   white 2 pixel wall around the track
      cols/rows 8..23 / 7..16   white 2 pixel square in the middle
      column 15, rows 17..22    chequered finish line on the bottom straight

So the drivable lane is the ring between the outside wall and the middle
square: x 10..245, y 10..181, minus the middle block (x 64..191, y 56..135).

Tile map (TMS9918A "Graphics I" pattern table, 8x8 monochrome tiles):

      0        blank
      1        2px line along the top of the cell
      2        2px line along the bottom
      3        2px line down the left side
      4        2px line down the right side
      5..8     the four corners
      9, 10    chequer squares A/B (4x4 blocks)
      11, 12   chequer A/B with the outer wall along the bottom
      13..     the 5x7 text font, ASCII 32..95
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_ASM = os.path.join(HERE, "..", "gfx.asm")

# --------------------------------------------------------------------------
FONT = {
    " ": ("     ",) * 7,
    "!": (".#...", ".#...", ".#...", ".#...", ".#...", ".....", ".#..."),
    '"': (".#.#.", ".#.#.", ".....", ".....", ".....", ".....", "....."),
    "#": (".#.#.", ".#.#.", "#####", ".#.#.", "#####", ".#.#.", ".#.#."),
    "$": ("..#..", ".####", "#.#..", ".###.", "..#.#", "####.", "..#.."),
    "%": ("##...", "##..#", "...#.", "..#..", ".#...", "#..##", "...##"),
    "&": (".##..", "#..#.", "#.#..", ".#...", "#.#.#", "#..#.", ".##.#"),
    "'": (".#...", ".#...", ".....", ".....", ".....", ".....", "....."),
    "(": ("...#.", "..#..", ".#...", ".#...", ".#...", "..#..", "...#."),
    ")": (".#...", "..#..", "...#.", "...#.", "...#.", "..#..", ".#..."),
    "*": (".....", "#.#.#", ".###.", "#####", ".###.", "#.#.#", "....."),
    "+": (".....", "..#..", "..#..", "#####", "..#..", "..#..", "....."),
    ",": (".....", ".....", ".....", ".....", ".....", "..#..", ".#..."),
    "-": (".....", ".....", ".....", "#####", ".....", ".....", "....."),
    ".": (".....", ".....", ".....", ".....", ".....", ".##..", ".##.."),
    "/": ("....#", "....#", "...#.", "..#..", ".#...", "#....", "#...."),
    "0": (".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."),
    "1": ("..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."),
    "2": (".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"),
    "3": ("#####", "...#.", "..#..", "...#.", "....#", "#...#", ".###."),
    "4": ("...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."),
    "5": ("#####", "#....", "####.", "....#", "....#", "#...#", ".###."),
    "6": ("..##.", ".#...", "#....", "####.", "#...#", "#...#", ".###."),
    "7": ("#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."),
    "8": (".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."),
    "9": (".###.", "#...#", "#...#", ".####", "....#", "...#.", ".##.."),
    ":": (".....", ".##..", ".##..", ".....", ".##..", ".##..", "....."),
    ";": (".....", ".##..", ".##..", ".....", ".##..", "..#..", ".#..."),
    "<": ("...#.", "..#..", ".#...", "#....", ".#...", "..#..", "...#."),
    "=": (".....", ".....", "#####", ".....", "#####", ".....", "....."),
    ">": (".#...", "..#..", "...#.", "....#", "...#.", "..#..", ".#..."),
    "?": (".###.", "#...#", "....#", "...#.", "..#..", ".....", "..#.."),
    "@": (".###.", "#...#", "#.###", "#.#.#", "#.###", "#....", ".###."),
    "A": (".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "B": ("####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."),
    "C": (".###.", "#...#", "#....", "#....", "#....", "#...#", ".###."),
    "D": ("####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."),
    "E": ("#####", "#....", "#....", "####.", "#....", "#....", "#####"),
    "F": ("#####", "#....", "#....", "####.", "#....", "#....", "#...."),
    "G": (".###.", "#...#", "#....", "#.###", "#...#", "#...#", ".###."),
    "H": ("#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "I": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "#####"),
    "J": ("..###", "...#.", "...#.", "...#.", "...#.", "#..#.", ".##.."),
    "K": ("#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"),
    "L": ("#....", "#....", "#....", "#....", "#....", "#....", "#####"),
    "M": ("#...#", "##.##", "#.#.#", "#...#", "#...#", "#...#", "#...#"),
    "N": ("#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#", "#...#"),
    "O": (".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "P": ("####.", "#...#", "#...#", "####.", "#....", "#....", "#...."),
    "Q": (".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#"),
    "R": ("####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"),
    "S": (".####", "#....", "#....", ".###.", "....#", "....#", "####."),
    "T": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."),
    "U": ("#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "V": ("#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."),
    "W": ("#...#", "#...#", "#...#", "#.#.#", "#.#.#", "##.##", "#...#"),
    "X": ("#...#", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", "#...#"),
    "Y": ("#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."),
    "Z": ("#####", "....#", "...#.", "..#..", ".#...", "#....", "#####"),
    "[": (".###.", ".#...", ".#...", ".#...", ".#...", ".#...", ".###."),
    "\\": ("#....", "#....", ".#...", "..#..", "...#.", "....#", "....#"),
    "]": (".###.", "...#.", "...#.", "...#.", "...#.", "...#.", ".###."),
    "^": ("..#..", ".#.#.", "#...#", ".....", ".....", ".....", "....."),
    "_": (".....", ".....", ".....", ".....", ".....", ".....", "#####"),
}

FONT_CHARS = [chr(c) for c in range(32, 96)]


def font_glyph(ch):
    """8x8 bitmap (list of 8 rows of 8 bits, MSB = leftmost pixel)."""
    rows = FONT.get(ch, (".....",) * 7)
    out = []
    for y in range(8):
        bits = 0
        if y < 7:
            for x in range(5):
                if rows[y][x] == "#":
                    bits |= 0x80 >> x
        out.append(bits)
    return out


# --------------------------------------------------------------------------
# track layout, in tile cells
# --------------------------------------------------------------------------
OUT_L, OUT_R = 1, 30            # outer wall columns  -> x 8..247
OUT_T, OUT_B = 1, 22            # outer wall rows     -> y 8..183
IN_L, IN_R = 8, 23              # middle square       -> x 64..191
IN_T, IN_B = 7, 16              #                       y 56..135
FINISH_COL = 15                 # chequered line, two columns wide
FINISH_COLS = (15, 16)          #                     -> x 120..135
FINISH_ROW = 17                 # first row under the middle square

# text inside the middle square (columns 9..22, rows 8..15)
HUD1_COL, HUD1_ROW = 12, 9      # "LAP n/3"
HUD2_COL, HUD2_ROW = 11, 12     # "SUSIE n/3"

# title screen, drawn over the same track
TITLE_LINES = [
    (11, 8, "DELTARUNE"),
    (11, 9, "CHAPTER 3"),
    (10, 11, "HIDDEN RACING"),
    (12, 12, "MINIGAME"),
    (13, 14, "3 LAPS"),
    (10, 15, "PRESS 1: RACE"),
]


# --------------------------------------------------------------------------
# name table helper
# --------------------------------------------------------------------------
class Screen:
    def __init__(self):
        self.cells = [[0] * 32 for _ in range(24)]

    def put(self, col, row, tile):
        self.cells[row][col] = tile

    def text(self, col, row, s, tile_for):
        for i, ch in enumerate(s):
            self.put(col + i, row, tile_for(ch))

    def bytes(self):
        out = []
        for row in self.cells:
            out.extend(row)
        return out


def build():
    tiles = []

    def add(t):
        tiles.append(t)
        return len(tiles) - 1

    T_BLANK = add([0] * 8)
    T_HT = add([0xFF, 0xFF, 0, 0, 0, 0, 0, 0])          # line along the top
    T_HB = add([0, 0, 0, 0, 0, 0, 0xFF, 0xFF])          # line along the bottom
    T_VL = add([0xC0] * 8)                              # line down the left
    T_VR = add([0x03] * 8)                              # line down the right
    T_TL = add([0xFF, 0xFF] + [0xC0] * 6)
    T_TR = add([0xFF, 0xFF] + [0x03] * 6)
    T_BL = add([0xC0] * 6 + [0xFF, 0xFF])
    T_BR = add([0x03] * 6 + [0xFF, 0xFF])
    T_CHK_A = add([0xF0] * 4 + [0x0F] * 4)
    T_CHK_B = add([0x0F] * 4 + [0xF0] * 4)
    T_CHK_A_WALL = add([0xF0] * 4 + [0x0F] * 2 + [0xFF, 0xFF])
    T_CHK_B_WALL = add([0x0F] * 4 + [0xF0] * 2 + [0xFF, 0xFF])

    T_FONT = len(tiles)
    for ch in FONT_CHARS:
        add(font_glyph(ch))

    def font_tile(ch):
        return T_FONT + FONT_CHARS.index(ch)

    # ---- the race track
    track = Screen()
    # outside wall
    for col in range(OUT_L, OUT_R + 1):
        track.put(col, OUT_T, T_HT)
        track.put(col, OUT_B, T_HB)
    for row in range(OUT_T, OUT_B + 1):
        track.put(OUT_L, row, T_VL)
        track.put(OUT_R, row, T_VR)
    track.put(OUT_L, OUT_T, T_TL)
    track.put(OUT_R, OUT_T, T_TR)
    track.put(OUT_L, OUT_B, T_BL)
    track.put(OUT_R, OUT_B, T_BR)
    # the square in the middle
    for col in range(IN_L, IN_R + 1):
        track.put(col, IN_T, T_HT)
        track.put(col, IN_B, T_HB)
    for row in range(IN_T, IN_B + 1):
        track.put(IN_L, row, T_VL)
        track.put(IN_R, row, T_VR)
    track.put(IN_L, IN_T, T_TL)
    track.put(IN_R, IN_T, T_TR)
    track.put(IN_L, IN_B, T_BL)
    track.put(IN_R, IN_B, T_BR)
    # chequered finish line, straight under the middle square
    for row in range(FINISH_ROW, OUT_B + 1):
        for i, col in enumerate(FINISH_COLS):
            a = (row + i) % 2 == 0
            if row == OUT_B:
                track.put(col, row, T_CHK_A_WALL if a else T_CHK_B_WALL)
            else:
                track.put(col, row, T_CHK_A if a else T_CHK_B)

    return {
        "tiles": tiles,
        "T_BLANK": T_BLANK,
        "T_FONT": T_FONT,
        "font_tile": font_tile,
        "track": track,
    }


def emit_asm(g):
    tiles = g["tiles"]
    L = []
    a = L.append
    a("; ----------------------------------------------------------------------")
    a("; gfx.asm - generated by tools/gen_gfx.py.  Do not edit by hand.")
    a("; ----------------------------------------------------------------------")
    a("")
    a("TILE_BLANK   equ %d" % g["T_BLANK"])
    a("TILE_FONT    equ %d          ; ASCII 32..95, one tile per character" % g["T_FONT"])
    a("PATTERN_COUNT equ %d" % len(tiles))
    a("")
    a("; race track, in tile cells (see tools/gen_gfx.py)")
    a("TRACK_OUT_L  equ %d" % OUT_L)
    a("TRACK_OUT_R  equ %d" % OUT_R)
    a("TRACK_OUT_T  equ %d" % OUT_T)
    a("TRACK_OUT_B  equ %d" % OUT_B)
    a("TRACK_IN_L   equ %d" % IN_L)
    a("TRACK_IN_R   equ %d" % IN_R)
    a("TRACK_IN_T   equ %d" % IN_T)
    a("TRACK_IN_B   equ %d" % IN_B)
    a("FINISH_COL   equ %d          ; first column of the chequered line" % FINISH_COL)
    a("FINISH_X     equ %d          ; its left edge in pixels" % (FINISH_COL * 8))
    a("FINISH_RIGHT equ %d          ; one pixel past its right edge" % ((FINISH_COL + len(FINISH_COLS)) * 8))
    a("HUD1_COL     equ %d" % HUD1_COL)
    a("HUD1_ROW     equ %d" % HUD1_ROW)
    a("HUD2_COL     equ %d" % HUD2_COL)
    a("HUD2_ROW     equ %d" % HUD2_ROW)
    a("")
    a("pattern_data:")
    for i, t in enumerate(tiles):
        a("        db %s   ; tile %d" % (",".join("0x%02X" % b for b in t), i))
    a("")
    a("; ---- sprite pattern: an 8x8 square, the colour comes from the SAT ----")
    a("sprite_patterns:")
    a("        db 0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF")
    a("")
    a("track_map:")
    tb = g["track"].bytes()
    for i in range(0, len(tb), 32):
        a("        db %s   ; row %d" % (",".join("%d" % b for b in tb[i:i + 32]), i // 32))
    a("")
    a("; ---- title text: col, row, zero terminated text, $FF marks the end ----")
    a("title_text:")
    for col, row, text in TITLE_LINES:
        a('        db %d, %d, "%s", 0' % (col, row, text))
    a("        db 0xFF")
    a("")
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------
# preview renderer (no emulator needed)
# --------------------------------------------------------------------------
def render(screen, tiles, out_path):
    from PIL import Image
    img = Image.new("RGB", (256, 192), (0, 0, 0))
    px = img.load()
    for row in range(24):
        for col in range(32):
            name = screen.cells[row][col]
            pat = tiles[name] if name < len(tiles) else [0] * 8
            for r in range(8):
                for b in range(8):
                    if pat[r] & (0x80 >> b):
                        px[col * 8 + b, row * 8 + r] = (255, 255, 255)
    img.save(out_path)
    return img


def preview(outdir):
    os.makedirs(outdir, exist_ok=True)
    g = build()
    tiles, font_tile = g["tiles"], g["font_tile"]

    title = Screen()
    for row in range(24):
        for col in range(32):
            title.cells[row][col] = g["track"].cells[row][col]
    for col, row, text in TITLE_LINES:
        title.text(col, row, text, font_tile)
    render(title, tiles, os.path.join(outdir, "title.png"))

    race = Screen()
    for row in range(24):
        for col in range(32):
            race.cells[row][col] = g["track"].cells[row][col]
    race.text(HUD1_COL, HUD1_ROW, "LAP 1/3", font_tile)
    race.text(HUD2_COL, HUD2_ROW, "SUSIE 0/3", font_tile)
    img = render(race, tiles, os.path.join(outdir, "race.png"))

    from PIL import ImageDraw
    dr = ImageDraw.Draw(img)
    dr.rectangle([140, 155, 147, 162], fill=(255, 255, 255))     # the player
    dr.rectangle([100, 155, 107, 162], fill=(255, 0, 255))       # Susie
    img.save(os.path.join(outdir, "race.png"))
    print("wrote previews to", outdir)


def main():
    g = build()
    with open(OUT_ASM, "w") as f:
        f.write(emit_asm(g))
    print("wrote %s (%d tiles)" % (os.path.normpath(OUT_ASM), len(g["tiles"])))
    if "--preview" in sys.argv[1:]:
        import tempfile
        preview(tempfile.mkdtemp(prefix="deltarune-art-"))


if __name__ == "__main__":
    main()
