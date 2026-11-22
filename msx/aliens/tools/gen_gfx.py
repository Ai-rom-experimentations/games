#!/usr/bin/env python3
"""Generates aliens/gfx.asm: the tiles, colours and sprites for ALIENS!.

The art lives here so it can be edited without an emulator:

    python3 tools/gen_gfx.py             # (re)write gfx.asm
    python3 tools/gen_gfx.py --preview   # also render a PNG preview

Everything is 8x8, because an MSX1 VDP (TMS9918A) in Graphics I has no other
size: 256 tiles of 8x8 and 256 sprite patterns of 8x8.

Tile map (the first 64 patterns get one colour per group of eight, per third
of the screen - that is the Graphics I colour table; see the README):

      0..40    the 5x7 text font, white (space ! . - : 0-9 A-Z)
      41..42   alien B, two animation frames, white (the spare half of the
               font's colour group - the middle row is white, the way the
               middle row of a Galaga formation is the odd one out)
      43..47   spare
      48..55   alien A, two animation frames, and the little ship used for the
               lives counter, light green
      56..63   alien C (two frames), the three star types and the three
               explosion frames, light yellow
      64..91   ALIENS! in 2x2 big letters for the title screen, white
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_ASM = os.path.join(HERE, "..", "gfx.asm")

# --------------------------------------------------------------------------
# the 5x7 font, as used by the other games in this repository
FONT = {
    " ": ("     ",) * 7,
    "!": (".#...", ".#...", ".#...", ".#...", ".#...", ".....", ".#..."),
    ".": (".....", ".....", ".....", ".....", ".....", ".##..", ".##.."),
    "-": (".....", ".....", ".....", "#####", ".....", ".....", "....."),
    ":": (".....", ".##..", ".##..", ".....", ".##..", ".##..", "....."),
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
}
FONT_CHARS = " !.-:" + "0123456789" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# --------------------------------------------------------------------------
# the aliens, two frames each, in the Galaga order of value: the top row is
# the boss, the middle the butterfly, the bottom the bee
ALIEN_A = (                       # bee (bottom row, 50 points)
    ("........", "..X..X..", "...XX...", "..XXXX..",
     ".XXXXXX.", "X.XXXX.X", "X.X..X.X", "..X..X.."),
    ("........", "..X..X..", "...XX...", "..XXXX..",
     ".XXXXXX.", ".XXXXXX.", "X.X..X.X", ".X.XX.X."),
)
ALIEN_B = (                       # butterfly (middle row, 100 points)
    ("..X..X..", "...XX...", ".XXXXXX.", "XX.XX.XX",
     "XXXXXXXX", ".X.XX.X.", "X......X", ".X....X."),
    ("..X..X..", "X..XX..X", "XXXXXXXX", "XX.XX.XX",
     ".XXXXXX.", "..X..X..", ".X....X.", "X......X"),
)
ALIEN_C = (                       # boss (top row, 150 points)
    ("...XX...", ".XXXXXX.", "XX.XX.XX", "XXXXXXXX",
     "..XXXX..", ".X.XX.X.", "X..XX..X", "...XX..."),
    ("...XX...", "XXXXXX..", "XX.XX.XX", "XXXXXXXX",
     "..XXXX..", "..X..X..", ".X.XX.X.", "X......X"),
)
EXPLOSION = (
    ("........", "...X....", "..X.X...", ".X...X..",
     "..X.X...", "...X....", "........", "........"),
    ("...X....", ".X...X..", "..X.X...", "X..X..X.",
     "..X.X...", ".X...X..", "...X....", "........"),
    ("X..X..X.", ".X.X.X..", "..X.X...", "X.....X.",
     "..X.X...", ".X.X.X..", "X..X..X.", "........"),
)
STARS = (
    ("........", "........", "........", "...X....",
     "........", "........", "........", "........"),
    ("........", "...X....", "...X....", "XXXXXXX.",
     "...X....", "...X....", "........", "........"),
    ("........", "........", "........", "..XXX...",
     "........", "........", "........", "........"),
)
SHIP = ("...XX...", "...XX...", "..XXXX..", "..XXXX..",
        ".XXXXXX.", "XXXXXXXX", "XXX..XXX", ".X....X.")
SHIP_ICON = ("........", "...XX...", "..XXXX..", ".XXXXXX.",
             "XXXXXXXX", "XXX..XXX", ".X....X.", "........")
BULLET = ("...XX...", "...XX...", "...XX...", "...XX...",
          "...XX...", "........", "........", "........")
ALIEN_SHOT = ("........", "...X....", "..XXX...", ".XXXXX..",
              "..XXX...", "...X....", "........", "........")

# --------------------------------------------------------------------------
TILE_FONT = 0                     # 41 glyphs, tiles 0..40
TILE_ALIEN_A = 48
TILE_ALIEN_B = 41
TILE_ALIEN_C = 56
TILE_STARS = 58
TILE_EXPLOSION = 61
TILE_SHIP_ICON = 54               # the spare half of the green group
TILE_TITLE = 64
PATTERN_COUNT = 96

SPR_SHIP = 0
SPR_BULLET = 1
SPR_ALIEN_A = 2
SPR_ALIEN_B = 3
SPR_ALIEN_C = 4
SPR_SHOT = 5
SPR_EXPLOSION = 6

# Graphics I colours (TMS9918A): 3 light green, 11 light yellow, 15 white
GREEN, YELLOW, WHITE = 3, 11, 15


def rows(shape):
    """A shape as eight bytes, one per row, bit 7 leftmost."""
    out = []
    for line in shape:
        v = 0
        for i, ch in enumerate(line):
            if ch in "X#*":
                v |= 0x80 >> i
        out.append(v)
    return out


def blank():
    return [0] * 8


def glyph(ch):
    lines = FONT[ch]
    out = []
    for line in lines:
        v = 0
        for i, c in enumerate(line):
            if c in "X#*":
                v |= 1 << (4 - i)          # five pixels, left aligned
        out.append(v)
    out.append(0)
    return out


def big_glyph(ch):
    """A 5x7 glyph at double size in a 16x16 box, as four 8x8 tiles."""
    pixels = [[0] * 16 for _ in range(16)]
    for r, line in enumerate(FONT[ch]):
        for c, v in enumerate(line):
            if v in "X#*":
                for dy in range(2):
                    for dx in range(2):
                        pixels[1 + r * 2 + dy][3 + c * 2 + dx] = 1
    tiles = []
    for ty in (0, 1):
        for tx in (0, 1):
            tiles.append(rows("".join(
                "X" if pixels[ty * 8 + r][tx * 8 + c] else "."
                for c in range(8)) for r in range(8)))
    return tiles


def build():
    patterns = [blank() for _ in range(PATTERN_COUNT)]
    font_map = [0] * 96

    for i, ch in enumerate(FONT_CHARS):
        patterns[TILE_FONT + i] = glyph(ch)
        font_map[ord(ch) - 32] = TILE_FONT + i

    def put(tile, shape):
        patterns[tile] = rows(shape)

    put(TILE_ALIEN_A + 0, ALIEN_A[0])
    put(TILE_ALIEN_A + 1, ALIEN_A[1])
    put(TILE_ALIEN_B + 0, ALIEN_B[0])
    put(TILE_ALIEN_B + 1, ALIEN_B[1])
    put(TILE_ALIEN_C + 0, ALIEN_C[0])
    put(TILE_ALIEN_C + 1, ALIEN_C[1])
    for i in range(3):
        put(TILE_STARS + i, STARS[i])
        put(TILE_EXPLOSION + i, EXPLOSION[i])
    put(TILE_SHIP_ICON, SHIP_ICON)

    # the title screen: ALIENS! in 2x2 letters, one pair of tile rows
    title_col = (32 - len("ALIENS!") * 2) // 2
    title_row = 5
    title_map = [0] * (32 * 24)
    for i, ch in enumerate("ALIENS!"):
        tl, tr, bl, br = big_glyph(ch)
        for tile, (dx, dy) in zip((tl, tr, bl, br), ((0, 0), (1, 0), (0, 1), (1, 1))):
            patterns[TILE_TITLE + i * 4 + tile_index(dx, dy)] = tile
            title_map[(title_row + dy) * 32 + title_col + i * 2 + dx] = \
                TILE_TITLE + i * 4 + tile_index(dx, dy)

    sprites = [blank() for _ in range(8)]
    for i, shape in enumerate((SHIP, BULLET, ALIEN_A[0], ALIEN_B[0],
                               ALIEN_C[0], ALIEN_SHOT, EXPLOSION[0])):
        sprites[i] = rows(shape)

    # one colour table: eight groups, repeated, so the colour of a cell is the
    # same in every third of the screen (the TMS9918A picks the entry from the
    # pattern group and the screen third, so both readings agree)
    colours = [WHITE] * 6 + [GREEN, YELLOW]
    colour_table = [colours[i % 8] for i in range(32)]

    return patterns, colour_table, sprites, font_map, title_map


def tile_index(dx, dy):
    return dy * 2 + dx


def write_asm(path, patterns, colour_table, sprites, font_map, title_map):
    out = []
    a = out.append
    a("; generated by tools/gen_gfx.py - do not edit")
    a("")
    a("PATTERN_COUNT equ %d" % PATTERN_COUNT)
    a("TILE_BLANK    equ 0")
    a("TILE_FONT     equ %d     ; char c -> the tile in font_map" % TILE_FONT)
    a("TILE_ALIEN_A  equ %d     ; two animation frames, light green" % TILE_ALIEN_A)
    a("TILE_ALIEN_B  equ %d     ; two animation frames, white" % TILE_ALIEN_B)
    a("TILE_ALIEN_C  equ %d     ; light yellow" % TILE_ALIEN_C)
    a("TILE_STARS    equ %d     ; dot, cross, dash" % TILE_STARS)
    a("TILE_EXPLOSION equ %d    ; three frames" % TILE_EXPLOSION)
    a("TILE_SHIP_ICON equ %d    ; the lives counter, light green" % TILE_SHIP_ICON)
    a("TILE_TITLE    equ %d    ; ALIENS! in 2x2 letters" % TILE_TITLE)
    a("SPR_SHIP      equ %d" % SPR_SHIP)
    a("SPR_BULLET    equ %d" % SPR_BULLET)
    a("SPR_ALIEN_A   equ %d" % SPR_ALIEN_A)
    a("SPR_ALIEN_B   equ %d" % SPR_ALIEN_B)
    a("SPR_ALIEN_C   equ %d" % SPR_ALIEN_C)
    a("SPR_SHOT      equ %d" % SPR_SHOT)
    a("SPR_EXPLOSION equ %d" % SPR_EXPLOSION)
    a("")
    a("pattern_data:")
    for i, p in enumerate(patterns):
        a("        db %s   ; %d" % (",".join("0x%02X" % b for b in p), i))
    a("")
    a("colour_data:")
    for i in range(0, 32, 8):
        a("        db %s" % ",".join("0x%02X" % (b << 4 | 1)
                                     for b in colour_table[i:i + 8]))
    a("")
    a("sprite_data:")
    for i, p in enumerate(sprites):
        a("        db %s   ; %d" % (",".join("0x%02X" % b for b in p), i))
    a("")
    a("font_map:")
    for i in range(0, 96, 16):
        a("        db %s" % ",".join("%d" % b for b in font_map[i:i + 16]))
    a("")
    a("title_map:")
    for r in range(24):
        row = title_map[r * 32:(r + 1) * 32]
        a("        db %s" % ",".join("%d" % b for b in row))
    with open(path, "w") as f:
        f.write("\n".join(out) + "\n")


def preview(patterns, sprites, title_map):
    from PIL import Image
    img = Image.new("RGB", (16 * 8, 12 * 8), (0, 0, 0))
    for i, p in enumerate(patterns):
        ox, oy = (i % 16) * 8, (i // 16) * 8
        for r, bits in enumerate(p):
            for c in range(8):
                if bits & (0x80 >> c):
                    img.putpixel((ox + c, oy + r), (255, 255, 255))
    img = img.resize((img.width * 3, img.height * 3), Image.NEAREST)
    img.save("/tmp/aliens-tiles.png")
    title = Image.new("RGB", (256, 192), (0, 0, 0))
    for r in range(24):
        for c in range(32):
            t = title_map[r * 32 + c]
            for y, bits in enumerate(patterns[t]):
                for x in range(8):
                    if bits & (0x80 >> x):
                        title.putpixel((c * 8 + x, r * 8 + y), (255, 255, 255))
    title = title.resize((512, 384), Image.NEAREST)
    title.save("/tmp/aliens-title.png")
    print("previews: /tmp/aliens-tiles.png /tmp/aliens-title.png")


def main():
    patterns, colours, sprites, font_map, title_map = build()
    write_asm(OUT_ASM, patterns, colours, sprites, font_map, title_map)
    print("wrote %s: %d tiles, %d sprites" % (OUT_ASM, PATTERN_COUNT, len(sprites)))
    if "--preview" in sys.argv:
        preview(patterns, sprites, title_map)


if __name__ == "__main__":
    main()
