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

There is also a second name table, `dialog_map`, which is the same track with
the bottom of the screen replaced by a Deltarune style dialogue box (rows
17..23) - that is what the end screens use.  Susie's portrait is drawn with
sprites, not tiles, because Graphics I gives a whole 8 scanline band a single
foreground colour and the portrait has to be purple while the text stays
white.  The portrait is 4x5 sprites (32x40 pixels) in two expressions.

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

# the dialogue box at the bottom of the end screens (rows 17..23)
BOX_L, BOX_R = OUT_L, OUT_R      # aligned with the track's outer wall
BOX_T, BOX_B = 17, 23
PORTRAIT_X, PORTRAIT_Y = 24, 144  # top left corner of the portrait
PORTRAIT_W, PORTRAIT_H = 32, 40   # 4 x 5 sprites
DLG_COL = 8                       # text starts right of the portrait
DLG_ROWS = (18, 20, 22)

# The dialogue is quoted verbatim from Deltarune Chapter 3 (Green Room, left
# TV): winning Kris gets "Kris, you won!" from Ralsei and Susie's
# "How the heck... alright, we're done."; losing three times gets
# "Man, it's like you're not even looking at the screen."
DLG_WIN = [
    "SUSIE: HOW THE HECK...",
    "ALRIGHT, WE'RE DONE.",
]
DLG_LOSE = [
    "SUSIE: MAN, IT'S LIKE",
    "YOU'RE NOT EVEN",
    "LOOKING AT THE SCREEN.",
]

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
# Susie's portrait: 32x40 pixels, drawn with sprites so it can be purple.
# Each 8x8 sprite carries one colour, so the art is split into 4x5 cells and
# every cell is declared magenta or white here.  Pixels of the other colour
# simply do not exist (they read as the black of the box).
# --------------------------------------------------------------------------
MAGE, WHITE = 1, 2               # 1 = magenta ($0D), 2 = white ($0F)

PORTRAIT_CELLS = [
    [MAGE, MAGE, MAGE, MAGE],    # hair
    [MAGE, MAGE, MAGE, MAGE],    # hair and the fringe
    [MAGE, WHITE, MAGE, MAGE],   # the one eye her hair does not cover
    [MAGE, MAGE, MAGE, MAGE],    # the grin (a hole in the magenta)
    [MAGE, MAGE, MAGE, MAGE],    # jaw, neck, shoulders
]
PORTRAIT_COLOUR = {MAGE: 0x0D, WHITE: 0x0F}


def _pv(x, y):
    return 0 <= x < PORTRAIT_W and 0 <= y < PORTRAIT_H


def prect(img, x0, y0, x1, y1, v):
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            if _pv(x, y):
                img[y][x] = v


def pellipse(img, cx, cy, rx, ry, v):
    for y in range(cy - ry, cy + ry + 1):
        for x in range(cx - rx, cx + rx + 1):
            dx = (x - cx) / float(rx)
            dy = (y - cy) / float(ry)
            if dx * dx + dy * dy <= 1.0 and _pv(x, y):
                img[y][x] = v


def ppoly(img, pts, v):
    ys = [pt[1] for pt in pts]
    for y in range(min(ys), max(ys) + 1):
        xs = []
        for i in range(len(pts)):
            x0, y0 = pts[i]
            x1, y1 = pts[(i + 1) % len(pts)]
            if y0 == y1:
                continue
            if min(y0, y1) <= y < max(y0, y1):
                xs.append(x0 + (y - y0) * (x1 - x0) / (y1 - y0))
        if len(xs) >= 2:
            prect(img, int(round(min(xs))), y, int(round(max(xs))), y, v)


def susie_portrait(expression):
    """0 = sulking (Kris won), 1 = taunting (Susie won).

    Two colours plus the black of the box, so the portrait is a solid magenta
    silhouette - a wide head with a zigzag of spikes, a neck and shoulders -
    with the face read out of the black holes and the one white cell: a big
    eye with a small pupil, and the mouth cut out of the silhouette.  Both
    expressions share the shapes and differ in the eyelid and the mouth,
    which is about all 32x40 pixels in two colours can carry.
    """
    img = [[0] * PORTRAIT_W for _ in range(PORTRAIT_H)]

    # ---- the head: a wide rounded block ...
    prect(img, 1, 8, 30, 34, MAGE)
    prect(img, 2, 6, 29, 8, MAGE)
    prect(img, 4, 5, 27, 6, MAGE)
    for x, y in ((2, 6), (29, 6), (1, 34), (30, 34)):
        img[y][x] = 0
    # ---- ... with a zigzag of hair spikes along the top
    peaks = (3, 11, 19, 27)
    for x in range(PORTRAIT_W):
        top = min(abs(x - px) for px in peaks) + 1       # 1 on a peak, 5 in a valley
        prect(img, x, top, x, 9, MAGE)

    # ---- the neck and a hint of her jacket
    prect(img, 12, 33, 20, 37, MAGE)
    prect(img, 1, 38, 30, 39, MAGE)

    # ---- the big eye.  It fills its cell (x 8..15, y 16..23) so that the
    #      black left over in the cell is just the corners of the eye.
    for y in range(16, 24):
        for x in range(8, 16):
            img[y][x] = 0
    if expression == 1:                                  # taunting: wide open
        prect(img, 9, 17, 14, 22, WHITE)
        for x, y in ((9, 17), (14, 17), (9, 22), (14, 22)):
            img[y][x] = 0
        prect(img, 11, 19, 12, 20, 0)                    # the pupil
    else:                                                # sulking: half lidded
        prect(img, 9, 19, 14, 22, WHITE)
        for x, y in ((9, 19), (14, 19), (9, 22), (14, 22)):
            img[y][x] = 0
        prect(img, 11, 20, 12, 21, 0)                    # the pupil, looking down

    # ---- the mouth, cut out of the silhouette (cells x 8..23, y 24..31)
    if expression == 1:                                  # taunting: open maw
        prect(img, 10, 27, 21, 30, 0)
        prect(img, 12, 26, 19, 26, 0)
    else:                                                # sulking: a tight frown
        prect(img, 12, 28, 19, 28, 0)
        prect(img, 11, 29, 12, 29, 0)
        prect(img, 19, 29, 20, 29, 0)

    return img


def portrait_patterns(img):
    """20 patterns, row major, one per sprite cell."""
    out = []
    for r in range(PORTRAIT_H // 8):
        for c in range(PORTRAIT_W // 8):
            colour = PORTRAIT_CELLS[r][c]
            pat = []
            for y in range(8):
                bits = 0
                for x in range(8):
                    if img[r * 8 + y][c * 8 + x] == colour:
                        bits |= 0x80 >> x
                pat.append(bits)
            out.append(pat)
    return out


def portrait_sat(base_pattern):
    """The sprite attribute table entries: y, x, pattern, colour (20 then $D0)."""
    rows = []
    for r in range(PORTRAIT_H // 8):
        for c in range(PORTRAIT_W // 8):
            rows.append(PORTRAIT_Y + r * 8 - 1)
            rows.append(PORTRAIT_X + c * 8)
            rows.append(base_pattern + r * 4 + c)
            rows.append(PORTRAIT_COLOUR[PORTRAIT_CELLS[r][c]])
    rows.append(0xD0)
    return rows


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

    # ---- the same track with a dialogue box across the bottom
    dialog = Screen()
    for row in range(24):
        for col in range(32):
            dialog.cells[row][col] = track.cells[row][col]
    for row in range(BOX_T, BOX_B + 1):
        for col in range(BOX_L, BOX_R + 1):
            dialog.put(col, row, T_BLANK)
    for col in range(BOX_L, BOX_R + 1):
        dialog.put(col, BOX_T, T_HT)
        dialog.put(col, BOX_B, T_HB)
    for row in range(BOX_T, BOX_B + 1):
        dialog.put(BOX_L, row, T_VL)
        dialog.put(BOX_R, row, T_VR)
    dialog.put(BOX_L, BOX_T, T_TL)
    dialog.put(BOX_R, BOX_T, T_TR)
    dialog.put(BOX_L, BOX_B, T_BL)
    dialog.put(BOX_R, BOX_B, T_BR)

    return {
        "tiles": tiles,
        "T_BLANK": T_BLANK,
        "dialog": dialog,
        "portrait": (susie_portrait(0), susie_portrait(1)),
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
    a("dialog_map:")
    db = g["dialog"].bytes()
    for i in range(0, len(db), 32):
        a("        db %s   ; row %d" % (",".join("%d" % b for b in db[i:i + 32]), i // 32))
    a("")
    a("; ---- dialogue: col, row, zero terminated line, $FF ends the box ----")
    a("dlg_win:")
    for i, line in enumerate(DLG_WIN):
        a('        db %d, %d, "%s", 0' % (DLG_COL, DLG_ROWS[i], line))
    a("        db 0xFF")
    a("dlg_lose:")
    for i, line in enumerate(DLG_LOSE):
        a('        db %d, %d, "%s", 0' % (DLG_COL, DLG_ROWS[i], line))
    a("        db 0xFF")
    a("")
    a("; ---- Susie's portrait: 4x5 sprites per expression, magenta and white ----")
    a("PORTRAIT_BASE equ 32           ; sprite pattern index of the portrait")
    a("portrait_data:")
    for expr, name in ((0, "sulking"), (1, "taunting")):
        pats = portrait_patterns(susie_portrait(expr))
        a("        ; expression %d - Susie %s" % (expr, name))
        for i, t in enumerate(pats):
            a("        db %s   ; cell %d" % (",".join("0x%02X" % b for b in t), i))
    a("")
    a("; ready made sprite attribute tables for the two expressions")
    for expr, name in ((0, "sulking"), (1, "taunting")):
        a("portrait_sat_%d:                 ; %s" % (expr, name))
        sat = portrait_sat(32 + expr * 20)
        for i in range(0, len(sat), 4):
            a("        db %s" % ",".join("0x%02X" % b for b in sat[i:i + 4]))
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


def blit_portrait(img, art):
    """Draw a portrait image over a rendered screen, cell colour and all."""
    px = img.load()
    for r in range(PORTRAIT_H // 8):
        for c in range(PORTRAIT_W // 8):
            colour = PORTRAIT_COLOUR[PORTRAIT_CELLS[r][c]]
            rgb = (255, 255, 255) if colour == 0x0F else (255, 0, 255)
            for y in range(8):
                for x in range(8):
                    if art[r * 8 + y][c * 8 + x] == PORTRAIT_CELLS[r][c]:
                        px[PORTRAIT_X + c * 8 + x, PORTRAIT_Y + r * 8 + y] = rgb


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

    for expr, lines, result, name in ((0, DLG_WIN, "YOU WIN", "win"),
                                      (1, DLG_LOSE, "SUSIE WINS", "lose")):
        end = Screen()
        for row in range(24):
            for col in range(32):
                end.cells[row][col] = g["dialog"].cells[row][col]
        end.text(13 if len(result) < 10 else 12, 9, result, font_tile)
        end.text(13, 13, "PRESS 1", font_tile)
        for i, line in enumerate(lines):
            end.text(DLG_COL, DLG_ROWS[i], line, font_tile)
        im = render(end, tiles, os.path.join(outdir, "%s.png" % name))
        blit_portrait(im, g["portrait"][expr])
        im.save(os.path.join(outdir, "%s.png" % name))
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
