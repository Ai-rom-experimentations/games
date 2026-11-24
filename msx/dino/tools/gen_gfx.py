#!/usr/bin/env python3
"""Generates dino/gfx.asm: the tiles, the sprites and the colours for CHROME
DINO.

    python3 tools/gen_gfx.py             # (re)write gfx.asm
    python3 tools/gen_gfx.py --preview   # also render previews to /tmp

The art is not redrawn: it is the real thing.  `tools/chrome-sprite.png` is
the sprite sheet out of Chromium (`components/neterror/resources/images/
default_100_percent/offline/100-offline-sprite.png`, BSD licence - see
LICENSE-chromium in this folder), and this script cuts the dino, the cacti,
the pterodactyls, the cloud, the moon, the stars, the digits and the ground
out of it, halves them, and turns them into patterns.

Halving is what makes a 600x150 strip fit a 256x192 screen: the dino is
44x47 in the browser and 22x24 here.  A pixel survives if any pixel of the
2x2 block it came from was set, which keeps the eye and the thin legs.

The screen is a TMS9918A in Graphics II: 768 cells with a pattern each and a
colour pair for every 8x1 strip.  That is what lets this port have colour -
green cacti with dark edges on a yellow desert, white digits on a blue sky,
a moon and stars at night - without any of it sharing a colour group.

Pattern budget (192 patterns is all a 16 KB VDP has room for):

      0..42    the 5x7 font (` !'-./:0-9 A-Z`), white on whatever it sits on
     43..50    sky bands - empty patterns; only the colour matters
     51..82    the ground, cut from the real horizon sprite: 16 phases x 2
               textures, so it scrolls a pixel at a time by changing nothing
               but the names in one cell row
     83..86    cloud, four cells wide, rewritten from CLOUD_PHASES as it moves
     87..92    moon, 2x3
     93..94    star: dot and plus
     95        sand, the floor under the line
     96..103   "HI", from the ofFline page's own digits
    104..143   the ten digits, 16x16 each
    144..187   big 2x2 letters: "CHROME DINO" for the title, "GAME OVER" for
               the end screen (both live here; the game copies the set it
               needs)
    188..191   spare

Sprite slots are 16x16 sprites, four patterns each (top left, top right,
bottom left, bottom right - the order the chip really uses).  A 16x16 sprite
has to start on a pattern that is a multiple of four, which is why the
sprites are numbered in whole slots:

      0..3     dino running 1          24..25   small cactus
      4..7     dino running 2          26..27   large cactus
      8..11    dino jumping            28..31   bird, wings up
     12..15    dino ducking 1          32..35   bird, wings down
     16..19    dino ducking 2          (the rest free)
     20..23    dino, crashed
"""

import os
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_ASM = os.path.join(HERE, "..", "gfx.asm")
SHEET = os.path.join(HERE, "chrome-sprite.png")
PREVIEW_DIR = "/tmp"

PATTERN_MAX = 192

# --------------------------------------------------------------------------
# the 5x7 font, as used by the other games in this repository
FONT = {
    " ": ("     ",) * 7,
    "!": (".#...", ".#...", ".#...", ".#...", ".#...", ".....", ".#..."),
    "'": (".#...", ".#...", ".....", ".....", ".....", ".....", "....."),
    "-": (".....", ".....", ".....", "#####", ".....", ".....", "....."),
    ".": (".....", ".....", ".....", ".....", ".....", ".##..", ".##.."),
    "/": ("....#", "....#", "...#.", "..#..", ".#...", "#....", "#...."),
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
FONT_CHARS = " !'-./:0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# --------------------------------------------------------------------------
# colour roles: a pattern says which role its ink and its paper are, and a
# theme says what colour each role is.  Day/night is then three 8 byte tables
# and one pass over the colour table - which is also how the fade works.
R_INK, R_PAPER, R_SKY, R_SKY_DEEP, R_SAND, R_SAND_DARK, R_MOON, R_STAR = range(8)

# one colour per role: ink, paper, sky, sky deep, sand line, sand, moon, star
THEMES = [
    ("day",   (15, 5, 5, 4, 10, 11, 11, 15)),
    ("dusk",  (11, 6, 6, 4, 10, 8, 11, 11)),
    ("night", (14, 1, 1, 1, 14, 4, 11, 14)),
]
SPRITE_COLOURS = [
    ("day",   (2, 12, 3, 13, 6)),     # dino, cactus, cactus dark, bird, dead dino
    ("dusk",  (3, 12, 3, 13, 8)),
    ("night", (3, 4, 3, 10, 8)),
]

# --------------------------------------------------------------------------
# where things are in the Chromium sprite sheet.  The numbers come out of the
# game's own sprite definitions (dino_game/offline_sprite_definitions.ts and
# trex.ts), not out of a ruler:
#   tRex {x: 848, y: 2}, frames at +0 jumping, +44 idle, +88 and +132 running,
#   +220 crashed, +264 and +323 ducking, 44x47 (ducking 59x25) - the duck
#   sprites sit a little lower in the sheet, hence the y.
#   cactusSmall {x: 228, y: 2} 17x35, cactusLarge {x: 332, y: 2} 25x50,
#   pterodactyl {x: 134, y: 2} 46x40 two frames, cloud {x: 86, y: 2} 46x14,
#   moon {x: 484, y: 2}, star {x: 645, y: 2} 9x9, digits at x=655, y=2,
#   "HI" at x=755, horizon {x: 2, y: 54} 600x12.
RECTS = {
    "run1":     (848 + 88, 2, 44, 47),
    "run2":     (848 + 132, 2, 44, 47),
    "jump":     (848 + 0, 2, 44, 47),
    "dead":     (848 + 220, 2, 44, 47),
    "duck1":    (848 + 264, 18, 59, 30),
    "duck2":    (848 + 323, 18, 59, 30),
    "cactus_s": (228, 2, 17, 35),
    "cactus_l": (332, 2, 25, 50),
    "bird1":    (134, 2, 46, 40),
    "bird2":    (134 + 46, 2, 46, 40),
    "cloud":    (86, 2, 46, 14),
    "moon":     (484, 2, 20, 40),
    "star":     (645, 2, 9, 9),
    "horizon":  (2, 54, 600, 12),
    "digits":   (655, 2, 100, 13),      # 0..9, ten pixels apart
    "hi":       (755, 2, 20, 13),       # "HI"
    "restart":  (2, 68, 36, 32),
}

TILE_FONT = 0
FONT_COUNT = len(FONT_CHARS)
TILE_SKY = TILE_FONT + FONT_COUNT            # 43..50
SKY_BANDS = 2
TILE_GROUND = TILE_SKY + SKY_BANDS           # 51..82
GROUND_PHASES = 16
GROUND_TEXTURES = 2
TILE_CLOUD = TILE_GROUND + GROUND_PHASES * GROUND_TEXTURES     # two clouds
CLOUD_CELLS = 4
CLOUD_SETS = 2
TILE_MOON = TILE_CLOUD + CLOUD_CELLS * CLOUD_SETS
MOON_W, MOON_H = 2, 3
TILE_STAR = TILE_MOON + MOON_W * MOON_H      # 93..94
TILE_SAND = TILE_STAR + 2                    # 95
TILE_HI = TILE_SAND + 1                      # 96..103
TILE_DIGIT = TILE_HI + 8                     # 104..143
TILE_LOGO = TILE_DIGIT + 40                  # 144..187
LOGO_TEXT = "CHROME DINO"
OVER_TEXT = "GAME OVER"

SPR_DINO_RUN1 = 0
SPR_DINO_RUN2 = 4
SPR_DINO_JUMP = 8
SPR_DINO_DUCK1 = 12
SPR_DINO_DUCK2 = 16
SPR_DINO_DEAD = 20
SPR_CACTUS_S = 24
SPR_CACTUS_L = 26
SPR_BIRD_UP = 28
SPR_BIRD_DOWN = 32
SPRITE_SLOTS = 36


# --------------------------------------------------------------------------
# a very small PNG reader, so that `make` needs nothing but python3
# --------------------------------------------------------------------------
def read_png(path):
    """-> (width, height, rows of palette indices, transparent index set)."""
    data = open(path, "rb").read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise SystemExit("%s is not a PNG" % path)
    pos, idat, palette, trns = 8, b"", [], b""
    w = h = depth = ctype = 0
    while pos < len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        if kind == b"IHDR":
            w, h, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", body)
            if interlace:
                raise SystemExit("interlaced PNGs are not supported")
        elif kind == b"PLTE":
            palette = [tuple(body[i:i + 3]) for i in range(0, len(body), 3)]
        elif kind == b"tRNS":
            trns = body
        elif kind == b"IDAT":
            idat += body
        pos += 12 + length
    if ctype != 3:
        raise SystemExit("expected an indexed PNG, got colour type %d" % ctype)
    raw = zlib.decompress(idat)
    stride = (w * depth + 7) // 8
    rows, prev = [], bytearray(stride)
    pos = 0
    for _ in range(h):
        filt = raw[pos]
        line = bytearray(raw[pos + 1:pos + 1 + stride])
        pos += 1 + stride
        if filt == 1:
            for i in range(1, stride):
                line[i] = (line[i] + line[i - 1]) & 0xFF
        elif filt == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif filt == 3:
            for i in range(stride):
                left = line[i - 1] if i else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif filt == 4:
            for i in range(stride):
                a = line[i - 1] if i else 0
                b = prev[i]
                c = prev[i - 1] if i else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pred) & 0xFF
        elif filt != 0:
            raise SystemExit("bad PNG filter %d" % filt)
        rows.append(line)
        prev = line
    # unpack the palette indices
    out = []
    for line in rows:
        if depth == 8:
            idx = list(line)
        else:
            per = 8 // depth
            mask = (1 << depth) - 1
            idx = []
            for byte in line:
                for k in range(per):
                    idx.append((byte >> (8 - depth * (k + 1))) & mask)
        out.append(idx[:w])
    clear = set()
    for i, alpha in enumerate(trns):
        if alpha < 128:
            clear.add(i)
    return w, h, out, clear


class Sheet:
    def __init__(self, path=SHEET):
        self.w, self.h, self.rows, self.clear = read_png(path)

    def crop(self, name):
        """A part of the sheet as a list of rows of True (ink)."""
        x, y, w, h = RECTS[name]
        return [[self.rows[y + r][x + c] not in self.clear if
                 x + c < self.w else False for c in range(w)]
                for r in range(h)]

    def ink(self, x, y):
        return self.rows[y][x] not in self.clear


def half(bitmap):
    """Halve a bitmap: a pixel survives if any pixel of its 2x2 block was set."""
    h, w = len(bitmap), len(bitmap[0])
    return [[any(bitmap[min(h - 1, r * 2 + dy)][min(w - 1, c * 2 + dx)]
                 for dy in (0, 1) for dx in (0, 1))
             for c in range(w // 2)] for r in range(h // 2)]


def windows(bitmap):
    return len(bitmap[0]), len(bitmap)


def rows_of(bits):
    return [0] * 8 if not bits else bits


def glyph(ch):
    shape = FONT[ch]
    out = []
    for r in range(8):
        line = "." + (shape[r] if r < len(shape) else "     ").replace(" ", ".") + ".."
        out.append(int(line.replace(".", "0").replace("#", "1"), 2))
    return out


def big_glyph(ch):
    """A 2x2-cell letter for the title and the end screen."""
    shape = FONT[ch]
    px = [[0] * 16 for _ in range(16)]
    for r, line in enumerate(shape):
        for c, v in enumerate(line):
            if v == "#":
                for dy in range(2):
                    for dx in range(2):
                        px[1 + r * 2 + dy][4 + c * 2 + dx] = 1
    out = []
    for (dy, dx) in ((0, 0), (0, 8), (8, 0), (8, 8)):
        out.append([int("".join("1" if px[dy + r][dx + c] else "0"
                                for c in range(8)), 2) for r in range(8)])
    return out


def tile_from(bitmap, x0, y0, fg=None):
    """One 8x8 tile out of a bitmap, transparent outside it."""
    h = len(bitmap)
    w = len(bitmap[0]) if h else 0
    out = []
    for r in range(8):
        bits = 0
        for c in range(8):
            y, x = y0 + r, x0 + c
            if 0 <= y < h and 0 <= x < w and bitmap[y][x]:
                bits |= 0x80 >> c
        out.append(bits)
    return out


def tiles_of(bitmap, cols, rows, fg=None):
    out = []
    for r in range(rows):
        for c in range(cols):
            out.append(tile_from(bitmap, c * 8, r * 8))
    return out


def sprite_slots(bitmap, want_cols=None, want_rows=None):
    """The patterns of a bitmap as 16x16 sprites, slot by slot, in the order
    the chip wants them: top left, bottom left, top right, bottom right -
    the four quadrants go into the table column by column, not row by row."""
    h = len(bitmap)
    w = len(bitmap[0]) if h else 0
    cols = want_cols or (w + 15) // 16
    rows = want_rows or (h + 15) // 16
    out = []
    for cy in range(rows):
        for cx in range(cols):
            quads = []
            for (dy, dx) in ((0, 0), (0, 8), (8, 0), (8, 8)):
                quads.append(tile_from(bitmap, cx * 16 + dx, cy * 16 + dy))
            # pattern order for a 16x16 sprite: TL, BL, TR, BR
            out += [quads[0], quads[2], quads[1], quads[3]]
    return out


def ground_phases(strip, offset, count=16):
    """16 patterns, one 16 pixel window of the real ground, cut at every
    offset.  Scrolling is then `name = TILE_GROUND + ((scroll + 8*col) & 15)`
    with the texture picked from the offset - no VRAM traffic at all."""
    phases = []
    for p in range(count):
        pat = []
        for r in range(8):
            bits = 0
            for c in range(8):
                x = offset + ((p + c) % 16)
                if 0 <= x < len(strip[0]) and r < len(strip) and strip[r][x]:
                    bits |= 0x80 >> c
            pat.append(bits)
        phases.append(pat)
    return phases


def cloud_phases(cloud):
    """The cloud at each of the 8 pixel offsets, as four cells each."""
    out = []
    for p in range(8):
        cells = []
        for cx in range(CLOUD_CELLS):
            pat = []
            for r in range(8):
                bits = 0
                for b in range(8):
                    x = cx * 8 + b - p
                    if 0 <= r < len(cloud) and 0 <= x < len(cloud[0]) and cloud[r][x]:
                        bits |= 0x80 >> b
                pat.append(bits)
            cells.append(pat)
        out.append(cells)
    return out


def build():
    sheet = Sheet()
    patterns = [[0] * 8 for _ in range(PATTERN_MAX)]
    roles = [[R_INK, R_PAPER] for _ in range(PATTERN_MAX)]
    bits = {}

    def put(index, tile, role):
        patterns[index] = tile
        roles[index] = list(role)

    font_map = [0] * 96
    for i, ch in enumerate(FONT_CHARS):
        put(TILE_FONT + i, glyph(ch), (R_INK, R_PAPER))
        font_map[ord(ch) - 32] = TILE_FONT + i

    put(TILE_SKY, [0] * 8, (R_SKY, R_SKY))
    put(TILE_SKY + 1, [0] * 8, (R_SKY_DEEP, R_SKY_DEEP))

    horizon = half(sheet.crop("horizon"))          # 300 x 6
    for t in range(GROUND_TEXTURES):
        off = 0 if t == 0 else 150
        for p, pat in enumerate(ground_phases(horizon, off)):
            put(TILE_GROUND + t * GROUND_PHASES + p, pat, (R_SAND_DARK, R_SAND))

    cloud = half(sheet.crop("cloud"))
    cloud_ph = cloud_phases(cloud)
    for set_ in range(CLOUD_SETS):
        for c in range(CLOUD_CELLS):
            put(TILE_CLOUD + set_ * CLOUD_CELLS + c, cloud_ph[0][c], (R_INK, R_SKY))

    moon = half(sheet.crop("moon"))                # 10 x 20
    for i, t in enumerate(tiles_of(moon, MOON_W, MOON_H)):
        put(TILE_MOON + i, t, (R_MOON, R_SKY_DEEP))

    star = sheet.crop("star")
    put(TILE_STAR, tile_from(half(star), 0, 0), (R_STAR, R_SKY_DEEP))
    put(TILE_STAR + 1, star_plus(), (R_STAR, R_SKY_DEEP))
    put(TILE_SAND, [0] * 8, (R_SAND_DARK, R_SAND))

    # the page's own digits, at full size: 10x12 in a 16x16 cell
    digits = sheet.crop("digits")
    for d in range(10):
        cell = [[False] * 16 for _ in range(16)]
        for r in range(13):
            for c in range(10):
                x, y = d * 10 + c, r
                if y < len(digits) and x < len(digits[0]) and digits[y][x]:
                    cell[r + 2][c + 3] = True
        for i, t in enumerate(tiles_of(cell, 2, 2)):
            put(TILE_DIGIT + d * 4 + i, t, (R_INK, R_PAPER))

    hi = sheet.crop("hi")
    for letter in range(2):
        cell = [[False] * 16 for _ in range(16)]
        for r in range(13):
            for c in range(10):
                x, y = letter * 10 + c, r
                if y < len(hi) and x < len(hi[0]) and hi[y][x]:
                    cell[r + 2][c + 3] = True
        for i, t in enumerate(tiles_of(cell, 2, 2)):
            put(TILE_HI + letter * 4 + i, t, (R_INK, R_PAPER))

    logo = []
    for ch in LOGO_TEXT:
        logo += big_glyph(ch)
    over = []
    for ch in OVER_TEXT:
        over += big_glyph(ch)
    for i, t in enumerate(logo):
        put(TILE_LOGO + i, t, (R_INK, R_PAPER))
    bits["logo_over"] = over

    # ---- sprites -------------------------------------------------------
    spr = [[0] * 8 for _ in range(SPRITE_SLOTS * 4)]
    layout = [
        (SPR_DINO_RUN1, "run1"), (SPR_DINO_RUN2, "run2"),
        (SPR_DINO_JUMP, "jump"), (SPR_DINO_DUCK1, "duck1"),
        (SPR_DINO_DUCK2, "duck2"), (SPR_DINO_DEAD, "dead"),
        (SPR_CACTUS_S, "cactus_s"), (SPR_CACTUS_L, "cactus_l"),
        (SPR_BIRD_UP, "bird1"), (SPR_BIRD_DOWN, "bird2"),
    ]
    sizes = {}
    for base, name in layout:
        bmp = half(sheet.crop(name))
        pats = sprite_slots(bmp)
        slots = len(pats) // 4
        sizes[name] = (len(bmp[0]), len(bmp), slots)
        for i, p in enumerate(pats):
            spr[base * 4 + i] = p

    return {
        "patterns": patterns,
        "roles": roles,
        "sprites": spr,
        "font_map": font_map,
        "logo": logo,
        "over": over,
        "clouds": cloud_ph,
        "sizes": sizes,
    }


def star_plus():
    return [int("".join(b), 2) for b in (
        "00000000", "00011000", "00011000", "01111110",
        "01111110", "00011000", "00011000", "00000000")]


def write_asm(path, art):
    out = []
    a = out.append
    a("; generated by tools/gen_gfx.py from tools/chrome-sprite.png - do not edit")
    a("")
    for name, value, note in (
            ("PATTERN_MAX", PATTERN_MAX, ""),
            ("TILE_FONT", TILE_FONT, ""),
            ("FONT_COUNT", FONT_COUNT, ""),
            ("TILE_SKY", TILE_SKY, "the eight sky bands"),
            ("SKY_BANDS", SKY_BANDS, ""),
            ("TILE_GROUND", TILE_GROUND, "16 phases x 2 textures"),
            ("GROUND_PHASES", GROUND_PHASES, ""),
            ("GROUND_TEXTURES", GROUND_TEXTURES, ""),
            ("TILE_CLOUD", TILE_CLOUD, "four cells, rewritten as it moves"),
            ("CLOUD_CELLS", CLOUD_CELLS, ""),
            ("TILE_MOON", TILE_MOON, "2x3"),
            ("TILE_STAR", TILE_STAR, "a dot and a plus"),
            ("TILE_SAND", TILE_SAND, "the floor under the line"),
            ("TILE_HI", TILE_HI, "\"HI\" in the page's own digits"),
            ("TILE_DIGIT", TILE_DIGIT, "0..9, four cells each"),
            ("TILE_LOGO", TILE_LOGO, "2x2 letters"),
            ("LOGO_LETTERS", len(LOGO_TEXT), ""),
            ("OVER_LETTERS", len(OVER_TEXT), ""),
            ("SPR_DINO_RUN1", SPR_DINO_RUN1, ""),
            ("SPR_DINO_RUN2", SPR_DINO_RUN2, ""),
            ("SPR_DINO_JUMP", SPR_DINO_JUMP, ""),
            ("SPR_DINO_DUCK1", SPR_DINO_DUCK1, ""),
            ("SPR_DINO_DUCK2", SPR_DINO_DUCK2, ""),
            ("SPR_DINO_DEAD", SPR_DINO_DEAD, ""),
            ("SPR_CACTUS_S", SPR_CACTUS_S, "two sprites, stacked"),
            ("SPR_CACTUS_L", SPR_CACTUS_L, "two sprites, stacked"),
            ("SPR_BIRD_UP", SPR_BIRD_UP, "2x2 sprites"),
            ("SPR_BIRD_DOWN", SPR_BIRD_DOWN, "2x2 sprites"),
            ("SPRITE_SLOTS", SPRITE_SLOTS, ""),
            ("THEME_COUNT", len(THEMES), "")):
        a("%-16s equ %d%s" % (name, value, ("   ; " + note) if note else ""))
    a("")
    a("; the size of each sprite, in pixels, and how many slots it takes.")
    a("; The cactuses are already in dino.asm, where the sprite layout needs them")
    for name, (w, h, slots) in art["sizes"].items():
        if name.startswith("cactus"):
            continue
        a("%-16s equ %d" % (name.upper() + "_W", w))
        a("%-16s equ %d" % (name.upper() + "_H", h))
    a("")
    a("; every pattern's ink and paper, as indices into a theme")
    a("role_data:")
    for i in range(0, PATTERN_MAX, 8):
        chunk = []
        for r in art["roles"][i:i + 8]:
            chunk += [str(r[0]), str(r[1])]
        a("        db " + ",".join(chunk))
    a("")
    a("theme_data:")
    for name, table in THEMES:
        a("        db " + ",".join("0x%02X" % c for c in table) + "   ; " + name)
    a("")
    a("; dino, cactus, cactus edge, bird, dead dino")
    a("sprite_colours:")
    for name, cols in SPRITE_COLOURS:
        a("        db " + ",".join("%d" % c for c in cols) + "   ; " + name)
    a("")
    a("pattern_data:")
    for i, p in enumerate(art["patterns"]):
        a("        db %s   ; %d" % (",".join("0x%02X" % b for b in p), i))
    a("")
    a("sprite_patterns:")
    for i, p in enumerate(art["sprites"]):
        a("        db %s   ; slot %d %s" % (",".join("0x%02X" % b for b in p),
                                           i // 4, "TL TR BL BR".split()[i % 4]))
    a("")
    a("font_map:")
    for i in range(0, 96, 16):
        a("        db " + ",".join("%d" % v for v in art["font_map"][i:i + 16]))
    a("")
    a("; which pattern goes in which cell of the big letters")
    a("logo_tiles:")
    for i in range(0, len(art["logo"]), 16):
        a("        db " + ",".join("%d" % (TILE_LOGO + j)
                                   for j in range(i, min(i + 16, len(art["logo"])))))
    a("")
    a("; the same block again, so the title can put it back after the end")
    a("; screen has borrowed those patterns")
    a("logo_data:")
    for i, p in enumerate(art["logo"]):
        a("        db " + ",".join("%d" % b for b in p))
    a("")
    a("; the same for GAME OVER, which the game copies into those patterns")
    a("over_data:")
    for i, p in enumerate(art["over"]):
        a("        db %s   ; %d" % (",".join("0x%02X" % b for b in p), i))
    a("")
    a("over_tiles:")
    for i in range(0, len(art["over"]), 16):
        a("        db " + ",".join("%d" % (TILE_LOGO + j)
                                   for j in range(i, min(i + 16, len(art["over"])))))
    a("")
    a("; the cloud at each pixel offset, four cells each")
    a("cloud_phases:")
    for p, cells in enumerate(art["clouds"]):
        for c in cells:
            a("        db " + ",".join("0x%02X" % b for b in c) + "   ; offset %d" % p)
    with open(path, "w") as f:
        f.write("\n".join(out) + "\n")


# --------------------------------------------------------------------------
def preview(art):
    """Draw what the game will show, from the same data the game gets."""
    from PIL import Image

    PALETTE = [
        (0, 0, 0), (0, 0, 0), (33, 200, 66), (94, 220, 120),
        (84, 85, 237), (125, 118, 252), (212, 82, 77), (66, 235, 245),
        (252, 85, 84), (255, 121, 120), (212, 193, 84), (230, 206, 128),
        (33, 176, 59), (201, 91, 186), (204, 204, 204), (255, 255, 255),
    ]
    pats = art["patterns"]
    roles = art["roles"]
    size = art["sizes"]
    DINO_H = size["run1"][1]
    CACTUS_S_H = size["cactus_s"][1]
    CACTUS_L_H = size["cactus_l"][1]

    def theme(name):
        for tname, table in THEMES:
            if tname == name:
                return table
        raise SystemExit("no theme " + name)

    class Canvas:
        def __init__(self, name):
            self.colours = theme(name)
            self.img = Image.new("RGB", (256, 192),
                                 PALETTE[self.colours[R_SKY]])

        def tile(self, index, x, y):
            fg = PALETTE[self.colours[roles[index][0]]]
            bg = PALETTE[self.colours[roles[index][1]]]
            for r in range(8):
                for c in range(8):
                    if 0 <= x + c < 256 and 0 <= y + r < 192:
                        self.img.putpixel((x + c, y + r),
                                          fg if pats[index][r] & (0x80 >> c) else bg)

        def cloud(self, x, y, phase, set_=0):
            for c, cell in enumerate(art["clouds"][phase]):
                self.tile(TILE_CLOUD + set_ * CLOUD_CELLS + c, x + c * 8, y)

        def ground(self, scroll):
            for col in range(32):
                self.tile(TILE_GROUND + ((scroll + col * 8) & 31), col * 8, 152)
            for row in range(20, 24):
                for col in range(32):
                    self.tile(TILE_SAND, col * 8, row * 8)

        def digit(self, d, x, y):
            for t in range(4):
                self.tile(TILE_DIGIT + d * 4 + t, x + (t % 2) * 8, y + (t // 2) * 8)

        def hi(self, x, y):
            for letter in range(2):
                for t in range(4):
                    self.tile(TILE_HI + letter * 4 + t,
                              x + letter * 16 + (t % 2) * 8, y + (t // 2) * 8)

        def logo(self, text, row):
            col = (32 - len(text) * 2) // 2
            for i in range(len(text)):
                for t in range(4):
                    self.tile(TILE_LOGO + i * 4 + t,
                              col * 8 + i * 16 + (t % 2) * 8, row * 8 + (t // 2) * 8)

        def sprite(self, base, slots, x, y, colour):
            col = PALETTE[colour]
            cols = 2 if slots > 2 else 1
            for e in range(slots):
                pats4 = art["sprites"][(base + e) * 4:(base + e) * 4 + 4]
                ex, ey = (e % cols) * 16, (e // cols) * 16
                for i, pat in enumerate(pats4):
                    dx, dy = (i // 2) * 8, (i % 2) * 8
                    for r in range(8):
                        for b in range(8):
                            if pat[r] & (0x80 >> b):
                                xx, yy = x + ex + dx + b, y + ey + dy + r
                                if 0 <= xx < 256 and 0 <= yy < 192:
                                    self.img.putpixel((xx, yy), col)

        def save(self, path, scale=2):
            self.img.resize((256 * scale, 192 * scale), Image.NEAREST).save(path)

    sky_deep_row = 15
    def sky(c):
        for row in range(19):
            index = TILE_SKY if row < sky_deep_row else TILE_SKY + 1
            for col in range(32):
                c.tile(index, col * 8, row * 8)

    # ---- one frame of the game, by day
    c = Canvas("day")
    sky(c)
    c.cloud(150, 40, 0, 0)
    c.cloud(56, 64, 3, 1)
    c.ground(5)
    c.sprite(SPR_CACTUS_L, 2, 120, 152 - CACTUS_L_H, 12)
    c.sprite(SPR_CACTUS_S, 2, 176, 152 - CACTUS_S_H, 12)
    c.sprite(SPR_BIRD_UP, 4, 200, 96, 13)
    c.sprite(SPR_DINO_RUN1, 4, 24, 152 - DINO_H, 2)
    c.hi(8, 0)
    for i, d in enumerate((0, 0, 1, 2, 0)):
        c.digit(d, 40 + i * 16, 0)
    for i, d in enumerate((0, 0, 4, 2, 0)):
        c.digit(d, 160 + i * 16, 0)
    c.save(os.path.join(PREVIEW_DIR, "dino-play.png"))

    # ---- the same frame at night
    n = Canvas("night")
    sky(n)
    n.cloud(150, 40, 0, 0)
    for i in range(6):
        n.tile(TILE_MOON + i, 200 + (i % 2) * 8, 24 + (i // 2) * 8)
    for (x, y) in ((40, 30), (90, 60), (150, 20), (220, 70), (30, 80), (120, 90)):
        n.tile(TILE_STAR, x, y)
    n.ground(2)
    n.sprite(SPR_CACTUS_L, 2, 120, 152 - CACTUS_L_H, 4)
    n.sprite(SPR_DINO_RUN2, 4, 24, 152 - DINO_H, 3)
    n.hi(8, 0)
    for i, d in enumerate((0, 0, 1, 2, 0)):
        n.digit(d, 40 + i * 16, 0)
    n.save(os.path.join(PREVIEW_DIR, "dino-night.png"))

    # ---- the title screen
    t = Canvas("day")
    sky(t)
    t.logo(LOGO_TEXT, 2)
    t.ground(0)
    t.sprite(SPR_DINO_RUN1, 4, 116, 96, 2)
    t.sprite(SPR_CACTUS_S, 2, 40, 152 - CACTUS_S_H, 12)
    t.sprite(SPR_CACTUS_L, 2, 180, 152 - CACTUS_L_H, 12)
    t.save(os.path.join(PREVIEW_DIR, "dino-title.png"))
    print("previews: /tmp/dino-play.png /tmp/dino-night.png /tmp/dino-title.png")


def main():
    art = build()
    write_asm(OUT_ASM, art)
    print("wrote %s: %d patterns, %d sprite slots"
          % (OUT_ASM, PATTERN_MAX, SPRITE_SLOTS))
    for name, (w, h, slots) in art["sizes"].items():
        print("   %-9s %2dx%-2d  %d sprite%s" % (name, w, h, slots,
                                                "" if slots == 1 else "s"))
    if "--preview" in sys.argv:
        preview(art)


if __name__ == "__main__":
    main()
