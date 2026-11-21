#!/usr/bin/env python3
"""Generates pong/gfx.asm (tile patterns + name tables) for the SG-1000 Pong.

The art lives here so it can be edited and previewed without an emulator:

    python3 tools/gen_gfx.py             # (re)write gfx.asm
    python3 tools/gen_gfx.py --preview   # also render the art to PNG files

The preview images need pillow; they are written to a temporary directory so
the repository stays clean.

Tile map (TMS9918A "Graphics I" pattern table, 8x8 monochrome tiles):

    0        blank
    1        dashed border line (top/bottom of the court)
    2        dashed centre net
    3..66    5x7 text font, ASCII 32..95 (one tile per glyph)
    67..126  7-segment score digits at 2x, six tiles each (2 wide x 3 tall)
    127..142 "PONG" title letters at 2x, four tiles each (2 wide x 2 tall)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_ASM = os.path.join(HERE, "..", "gfx.asm")

# --------------------------------------------------------------------------
# 5x7 text font (classic LCD shapes), one entry per ASCII code 32..95
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


def scale2(bmp):
    """Scale a bitmap (list of row-ints, w bits each) by 2.  Returns
    (rows, width) with each row an int."""
    rows = []
    for v in bmp:
        wide = 0
        for b in range(8):
            wide |= ((v >> (7 - b)) & 1) << (15 - 2 * b)
            wide |= ((v >> (7 - b)) & 1) << (14 - 2 * b)
        rows.append(wide)
        rows.append(wide)
    return rows


# --------------------------------------------------------------------------
# chunky 7-segment score digits: 8x12 grid, 2px strokes, scaled 2x
# --------------------------------------------------------------------------
SEGMENTS = {
    "A": (1, 6, 0, 2),     # x0, x1(wrap), y0, y1(wrap)  -> rectangles below
}

# rectangles as (x0, x1, y0, y1) inclusive, on an 8x12 grid
SEG = {
    "a": (1, 5, 0, 1),
    "b": (5, 6, 1, 6),
    "c": (5, 6, 6, 11),
    "d": (1, 5, 10, 11),
    "e": (0, 1, 6, 11),
    "f": (0, 1, 1, 6),
    "g": (1, 5, 5, 6),
}

DIGIT_SEGMENTS = {
    0: "abcdef",
    1: "bc",
    2: "abged",
    3: "abgcd",
    4: "fgbc",
    5: "afgcd",
    6: "afgecd",
    7: "abc",
    8: "abcdefg",
    9: "abcdfg",
}


def digit_bitmap(d):
    grid = [[0] * 8 for _ in range(12)]
    for s in DIGIT_SEGMENTS[d]:
        x0, x1, y0, y1 = SEG[s]
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                grid[y][x] = 1
    rows = []
    for y in range(12):
        bits = 0
        for x in range(8):
            if grid[y][x]:
                bits |= 0x80 >> x
        rows.append(bits)
    return rows


def bitmap_to_tiles(rows, width):
    """Split a bitmap of rows (ints, MSB-first, `width` px wide) into 8x8
    tiles, ordered left-to-right then top-to-bottom."""
    tiles = []
    h = len(rows)
    for ty in range((h + 7) // 8):
        for tx in range((width + 7) // 8):
            data = []
            for r in range(8):
                y = ty * 8 + r
                v = rows[y] if y < h else 0
                v = (v >> (width - (tx + 1) * 8)) & 0xFF if width > 8 else v
                data.append(v)
            tiles.append(data)
    return tiles


# --------------------------------------------------------------------------
# name table helpers
# --------------------------------------------------------------------------
class Screen:
    def __init__(self):
        self.cells = [[0] * 32 for _ in range(24)]

    def put(self, col, row, tile):
        self.cells[row][col] = tile

    def text(self, col, row, s, tiles_for):
        for i, ch in enumerate(s):
            self.put(col + i, row, tiles_for(ch))

    def bytes(self):
        out = []
        for row in self.cells:
            out.extend(row)
        return out


def court(screen, dash, net):
    for col in range(32):
        screen.put(col, 0, dash)
        screen.put(col, 23, dash)
    for row in range(24):
        screen.put(15, row, net)


# --------------------------------------------------------------------------
# build everything
# --------------------------------------------------------------------------
def build():
    tiles = []

    def add(t):
        tiles.append(t)
        return len(tiles) - 1

    TILE_BLANK = add([0] * 8)
    # dashed border: 4 on / 4 off, 2px thick, sits in the middle of the cell
    TILE_DASH = add([0, 0, 0, 0, 0xF0, 0xF0, 0, 0])
    # centre net: 1px wide vertical dashes, 4 on / 4 off
    TILE_NET = add([0x80, 0x80, 0x80, 0x80, 0, 0, 0, 0])

    TILE_FONT = len(tiles)
    for ch in FONT_CHARS:
        add(font_glyph(ch))

    TILE_DIG2X = len(tiles)
    for d in range(10):
        rows = scale2(digit_bitmap(d))
        for t in bitmap_to_tiles(rows, 16):
            add(t)

    TILE_BIG = len(tiles)
    BIG_CHARS = "PONG"
    for ch in BIG_CHARS:
        rows = scale2(font_glyph(ch))
        for t in bitmap_to_tiles(rows, 16):
            add(t)

    def font_tile(ch):
        return TILE_FONT + FONT_CHARS.index(ch)

    # ---- gameplay court
    field = Screen()
    court(field, TILE_DASH, TILE_NET)

    # ---- title screen
    title = Screen()
    court(title, TILE_DASH, TILE_NET)
    # "PONG" is 2x text: each glyph is 2 tiles wide, 2 rows tall
    col = 12
    for i, ch in enumerate(BIG_CHARS):
        t = TILE_BIG + i * 4
        title.put(col, 3, t)
        title.put(col + 1, 3, t + 1)
        title.put(col, 4, t + 2)
        title.put(col + 1, 4, t + 3)
        col += 2
    title.text(12, 12, "1 PLAYER", font_tile)
    title.text(11, 14, "2 PLAYERS", font_tile)
    title.put(10, 12, font_tile(">"))
    title.text(8, 19, "PRESS 1 TO START", font_tile)

    return {
        "tiles": tiles,
        "TILE_BLANK": TILE_BLANK,
        "TILE_DASH": TILE_DASH,
        "TILE_NET": TILE_NET,
        "TILE_FONT": TILE_FONT,
        "TILE_DIG2X": TILE_DIG2X,
        "TILE_BIG": TILE_BIG,
        "field": field,
        "title": title,
        "font_tile": font_tile,
    }


def emit_asm(g):
    tiles = g["tiles"]
    L = []
    a = L.append
    a("; ----------------------------------------------------------------------")
    a("; gfx.asm - generated by tools/gen_gfx.py.  Do not edit by hand.")
    a("; ----------------------------------------------------------------------")
    a("")
    a("TILE_BLANK   equ %d" % g["TILE_BLANK"])
    a("TILE_DASH    equ %d" % g["TILE_DASH"])
    a("TILE_NET     equ %d" % g["TILE_NET"])
    a("TILE_FONT    equ %d          ; ASCII 32..95, one tile per char" % g["TILE_FONT"])
    a("TILE_DIG2X   equ %d          ; score digits 0-9, 6 tiles each" % g["TILE_DIG2X"])
    a("TILE_BIG     equ %d          ; 'P','O','N','G' at 2x, 4 tiles each" % g["TILE_BIG"])
    a("")
    a("PATTERN_COUNT equ %d" % len(tiles))
    a("")
    a("pattern_data:")
    for i, t in enumerate(tiles):
        a("        db %s   ; tile %d" % (",".join("0x%02X" % b for b in t), i))
    a("")
    a("; ---- sprite patterns (8x8, one bit per pixel)")
    a("SPR_PADDLE   equ 0")
    a("SPR_BALL     equ 1")
    a("sprite_patterns:")
    a("        db 0xF0,0xF0,0xF0,0xF0,0xF0,0xF0,0xF0,0xF0   ; paddle: 4px wide bar")
    a("        db 0xF0,0xF0,0xF0,0xF0,0x00,0x00,0x00,0x00   ; ball: 4x4 block")
    a("")
    a("; ---- name tables (32x24)")
    a("field_map:")
    fb = g["field"].bytes()
    for i in range(0, len(fb), 32):
        a("        db %s   ; row %d" % (",".join("%d" % b for b in fb[i:i + 32]), i // 32))
    a("title_map:")
    tb = g["title"].bytes()
    for i in range(0, len(tb), 32):
        a("        db %s   ; row %d" % (",".join("%d" % b for b in tb[i:i + 32]), i // 32))
    a("")
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------
# preview renderer (no emulator needed)
# --------------------------------------------------------------------------
def render(screen, tiles, digit_pairs=(), out_path=None):
    from PIL import Image, ImageDraw
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
    if out_path:
        img.save(out_path)
    return img


def preview(outdir):
    os.makedirs(outdir, exist_ok=True)
    g = build()
    tiles = g["tiles"]
    render(g["title"], tiles, out_path=os.path.join(outdir, "title.png"))

    # gameplay court with "4" and "1" on the board, plus paddles and ball
    field = Screen()
    for row in range(24):
        for col in range(32):
            field.cells[row][col] = g["field"].cells[row][col]
    d = g["TILE_DIG2X"]
    for (col0, digit) in ((10, 4), (20, 1)):
        t = d + digit * 6
        for r in range(3):
            for c in range(2):
                field.put(col0 + c, 1 + r, t + r * 2 + c)
    court_img = render(field, tiles, out_path=os.path.join(outdir, "court.png"))
    from PIL import ImageDraw
    dr = ImageDraw.Draw(court_img)
    dr.rectangle([20, 84, 23, 99], fill=(255, 255, 255))
    dr.rectangle([232, 74, 235, 89], fill=(255, 255, 255))
    dr.rectangle([150, 120, 153, 123], fill=(255, 255, 255))
    court_img.save(os.path.join(outdir, "court.png"))

    # a font/digit sheet for eyeballing the art
    sheet = Screen()
    for i, ch in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"):
        sheet.put((i % 26), 1 + (i // 26) * 2, g["font_tile"](ch))
    row = 4
    for dgt in range(10):
        t = d + dgt * 6
        for r in range(3):
            for c in range(2):
                sheet.put(2 + dgt * 3 + c, row + r, t + r * 2 + c)
    render(sheet, tiles, out_path=os.path.join(outdir, "tiles.png"))
    print("wrote previews to", outdir)


def main():
    g = build()
    with open(OUT_ASM, "w") as f:
        f.write(emit_asm(g))
    print("wrote %s (%d tiles)" % (os.path.normpath(OUT_ASM), len(g["tiles"])))
    if "--preview" in sys.argv[1:]:
        import tempfile
        preview(tempfile.mkdtemp(prefix="pong-art-"))


if __name__ == "__main__":
    main()
