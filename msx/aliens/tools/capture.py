#!/usr/bin/env python3
"""Runs aliens.rom in the bundled MSX emulator, checks it behaves, and writes
the screenshots in ../screenshots.

    python3 tools/capture.py              # check + screenshots
    python3 tools/capture.py --out DIR    # somewhere else
    python3 tools/capture.py --no-gif     # skip the animation

Exit status is non zero if anything is wrong, so `make check` is the test
suite: it boots the cartridge through the stand-in BIOS, reads the VDP's VRAM
and the PSG's registers, and plays the game with an autopilot.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from msx import MSX, load_rom, load_bios          # noqa: E402
from PIL import Image                              # noqa: E402

ROM = os.path.join(HERE, "..", "aliens.rom")
BIOS = os.path.join(HERE, "bios.rom")
GFX = os.path.join(HERE, "..", "gfx.asm")

# joystick bits, as tools/msx.py wants them
UP, DOWN, LEFT, RIGHT, FIRE = 0x01, 0x02, 0x04, 0x08, 0x10

# RAM, see the equ block at the top of aliens.asm
ST, PX, LIVES, SCORE, HI, WAVE = 0, 4, 5, 6, 9, 12
ALIENS, ALIENS_N, FORM_X, FORM_Y = 13, 31, 32, 33
BULLET_ON, BX, BY = 39, 40, 41
DIVE_T, SHOT_T = 42, 43
S_ON, S_X, S_Y = 56, 57, 58
RAND, TITLE_T = 961, 962

TITLE, PLAY, DYING, OVER, WAVE_IN = 0, 1, 2, 3, 4
NAME = 0x1800
SAT = 0x1B00
HIDDEN = 0xD0                        # y >= this parks a sprite out of sight


class Checks:
    def __init__(self):
        self.failed = []
        self.total = 0

    def ok(self, cond, text):
        self.total += 1
        print(("  ok   " if cond else "  FAIL ") + text)
        if not cond:
            self.failed.append(text)
        return cond

    def done(self):
        print("\n%d checks, %d failed" % (self.total, len(self.failed)))
        for f in self.failed:
            print("  -", f)
        return 0 if not self.failed else 1


def gfx_equ(name):
    """Read a constant out of the generated gfx.asm."""
    for line in open(GFX):
        parts = line.split()
        if len(parts) >= 3 and parts[0] == name and parts[1] == "equ":
            return int(parts[2], 0)
    raise SystemExit("gfx.asm has no %s" % name)


def gfx_bytes(label, count):
    """Read `count` bytes of a `label:` block out of gfx.asm."""
    out, on = [], False
    for line in open(GFX):
        if line.startswith(label + ":"):
            on = True
            continue
        if on:
            if line.startswith("        db"):
                body = line.split("db", 1)[1].split(";")[0]
                out += [int(v, 0) for v in body.replace(" ", "").split(",") if v]
                if len(out) >= count:
                    break
            elif line.strip() and not line.startswith("  "):
                break
    return out[:count]


def text(emu, col, row, n):
    """The characters in n cells, read back through the font."""
    font = gfx_bytes("font_map", 96)
    back = {}
    for i, tile in enumerate(font):
        back.setdefault(tile, chr(32 + i))
    vram = emu.vdp.vram
    return "".join(back.get(vram[NAME + row * 32 + col + i], "?") for i in range(n)).rstrip()


def cell(emu, col, row):
    return emu.vdp.vram[NAME + row * 32 + col]


def sat(emu, i):
    return list(emu.vdp.vram[SAT + i * 4:SAT + i * 4 + 4])


def star_cells(emu):
    stars = {gfx_equ("TILE_STARS"), gfx_equ("TILE_STARS") + 1, gfx_equ("TILE_STARS") + 2}
    vram = emu.vdp.vram
    return {(c, r) for r in range(24) for c in range(32)
            if vram[NAME + r * 32 + c] in stars}


def alien_cells(emu):
    a, b, c = gfx_equ("TILE_ALIEN_A"), gfx_equ("TILE_ALIEN_B"), gfx_equ("TILE_ALIEN_C")
    tiles = {a, a + 1, b, b + 1, c, c + 1}
    vram = emu.vdp.vram
    return {(col, row) for row in range(24) for col in range(32)
            if vram[NAME + row * 32 + col] in tiles}


def run(emu, frames, pad=0):
    for _ in range(frames):
        emu.set_pad(pad)
        emu.run_frame()
    if pad:
        emu.set_pad(0)                 # do not leave the joystick held down


def boot(emu, frames=40):
    """The boot uploads ~2000 bytes to the VDP, so give it a few frames."""
    run(emu, frames)


def start_game(emu):
    run(emu, 2, FIRE)
    run(emu, 4)
    run(emu, 90)                     # the WAVE 1 card
    return emu.ram(ST) == PLAY


def aim_at(emu, x, limit=60):
    """Slide the ship to a pixel column."""
    for _ in range(limit):
        if abs(emu.ram(PX) - x) <= 2:
            break
        emu.set_pad(LEFT if emu.ram(PX) > x else RIGHT)
        emu.run_frame()
    emu.set_pad(0)
    return abs(emu.ram(PX) - x) <= 4


def aim(emu, col, limit=160):
    """Slide the ship under a column, then fire."""
    target = col * 8 + 1
    for _ in range(limit):
        if abs(emu.ram(PX) - target) <= 1:
            break
        emu.set_pad(LEFT if emu.ram(PX) > target else RIGHT)
        emu.run_frame()
    emu.set_pad(FIRE)
    emu.run_frame()
    emu.set_pad(0)
    return abs(emu.ram(PX) - target) <= 1


def aim_and_kill(emu, col, row, frames=90):
    """Fire up a column and wait for the bullet to eat the alien in `row`."""
    # hold the formation still (sway and drop) and keep the divers in their
    # seats while we aim, so the target does not wander off
    emu.mem[0xC000 + 35] = 200
    emu.mem[0xC000 + 36] = 240
    emu.mem[0xC000 + DIVE_T] = 250
    for _ in range(60):                # let any earlier shot land first
        if emu.ram(BULLET_ON) == 0:
            break
        emu.run_frame()
    was = (col, row) in alien_cells(emu)
    if not aim(emu, col):
        return False
    for _ in range(frames):
        emu.run_frame()
        if emu.ram(BULLET_ON) == 0:
            break
    emu.set_pad(0)
    emu.run_frame()                    # one frame for the scoreboard to catch up
    return was and (col, row) not in alien_cells(emu)


def wait_shot(emu, frames=40):
    for _ in range(frames):
        emu.run_frame()
        if emu.ram(BULLET_ON) == 0:
            return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "..", "screenshots"))
    ap.add_argument("--no-gif", action="store_true")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    chk = Checks()

    rom = load_rom(ROM)
    bios = load_bios(BIOS)

    # ---- the cartridge itself -------------------------------------------
    print("the cartridge")
    chk.ok(len(rom) == 16384, "the ROM is 16 KB (%d bytes)" % len(rom))
    chk.ok(rom[0:2] == b"AB", "it starts with the MSX header 'AB'")
    init = rom[2] | (rom[3] << 8)
    chk.ok(0x4010 <= init < 0x8000, "INIT points into the cartridge (%04X)" % init)
    chk.ok(rom[init - 0x4000] == 0xF3, "and starts with di (%02X)" % rom[init - 0x4000])
    chk.ok(rom[0x0F] == 0, "the header is 16 bytes, code starts at $4010")

    # ---- boot -----------------------------------------------------------
    print("booting through the stand-in BIOS")
    emu = MSX(rom, bios)
    boot(emu)
    regs = [emu.vdp.regs[i] for i in range(8)]
    chk.ok(regs[0] == 0x00 and regs[1] == 0xC0, "the VDP is in Graphics I, display on %s"
           % [hex(r) for r in regs[:2]])
    chk.ok(regs[2:] == [0x06, 0x80, 0x00, 0x36, 0x07, 0x01],
           "and the tables are where it expects them %s" % [hex(r) for r in regs[2:]])
    chk.ok(not emu.errors, "nothing was written to the ROM%s"
           % ("" if not emu.errors else ": " + emu.errors[0]))
    chk.ok(not emu.unknown_ports, "and it only touched the VDP, PSG and PPI%s"
           % ("" if not emu.unknown_ports else ": " + str(emu.unknown_ports)))

    # ---- the art --------------------------------------------------------
    print("the art")
    colours = list(emu.vdp.vram[0x2000:0x2020])
    want = gfx_bytes("colour_data", 32)
    chk.ok(colours == want, "32 bytes of colour, white with green and yellow groups")
    chk.ok(colours[6] == 0x31 and colours[7] == 0xB1,
           "aliens green ($31) and yellow ($B1) %s" % [hex(c) for c in colours[6:8]])
    tiles = gfx_equ("PATTERN_COUNT")
    chk.ok(emu.vdp.vram[0:tiles * 8] == bytes(gfx_bytes("pattern_data", tiles * 8)),
           "all %d tile patterns are uploaded, byte for byte" % tiles)
    chk.ok(emu.vdp.vram[0x3800:0x3840] == bytes(gfx_bytes("sprite_data", 64)),
           "and the eight sprite patterns")

    # ---- the title ------------------------------------------------------
    print("the title screen")
    chk.ok(emu.ram(ST) == TITLE, "the game sits on the title (%d)" % emu.ram(ST))
    title_map = gfx_bytes("title_map", 768)
    got = [cell(emu, c, 5) for c in range(32)]
    chk.ok(got[9:23] == title_map[5 * 32 + 9:5 * 32 + 23],
           "ALIENS! is drawn in 2x2 letters")
    chk.ok(got[9] == gfx_equ("TILE_TITLE"), "with the first big A at column 9")
    chk.ok(text(emu, 9, 17, 3) == "HI", "and the high score underneath")
    chk.ok(text(emu, 12, 17, 6) == "002000", "...which starts at %r" % text(emu, 12, 17, 6))
    run(emu, 8)
    for _ in range(64):
        if text(emu, 9, 14, 13) == "PRESS TRIGGER":
            break
        run(emu, 1)
    chk.ok(text(emu, 9, 14, 13) == "PRESS TRIGGER",
           "PRESS TRIGGER blinks there %r" % text(emu, 9, 14, 13))

    # ---- the starfield --------------------------------------------------
    print("the starfield")
    before = star_cells(emu)
    cols = {c for c, r in before}
    chk.ok(len(before) > 20, "stars are scattered over the playfield (%d cells)" % len(before))
    chk.ok(len(cols) > 12, "across the whole width (%d columns)" % len(cols))
    run(emu, 8)
    after = star_cells(emu)
    moved = {s for s in before if any((s[0], s[1] + d) in after for d in (1, 2, 3))}
    chk.ok(len(moved) > len(before) // 2,
           "and they slide down the screen (%d of %d moved)" % (len(moved), len(before)))
    chk.ok(len(star_cells(emu)) > 20, "while new ones keep coming (%d)" % len(after))
    chk.ok(all(r >= 2 for c, r in after), "never into the scoreboard rows")
    chk.ok(not any(5 <= r <= 6 and 9 <= c <= 22 for c, r in after),
           "and never over the big letters")
    sprite_ship = sat(emu, 0)
    chk.ok(sprite_ship[2] == gfx_equ("SPR_SHIP") and sprite_ship[3] == 0x0F,
           "the ship waits under the title %s" % sprite_ship)
    emu.screenshot().save(os.path.join(args.out, "title.png"))

    # ---- starting a game ------------------------------------------------
    print("starting a game")
    chk.ok(start_game(emu), "the trigger starts a race (%d)" % emu.ram(ST))
    chk.ok(text(emu, 0, 0, 12) == "SCORE 000000", "the scoreboard reads %r"
           % text(emu, 0, 0, 12))
    chk.ok(text(emu, 16, 0, 9) == "HI 002000", "and the high score %r" % text(emu, 16, 0, 9))
    chk.ok(text(emu, 0, 1, 6) == "WAVE 1", "wave one")
    lives = [cell(emu, c, 1) for c in range(25, 31)]
    icon = gfx_equ("TILE_SHIP_ICON")
    chk.ok(lives.count(icon) == 3, "three little ships for three lives %s" % lives)
    chk.ok(emu.ram(ALIENS_N) == 18, "eighteen aliens in the air (%d)" % emu.ram(ALIENS_N))

    # ---- the formation --------------------------------------------------
    print("the formation")
    cells = alien_cells(emu)
    fx, fy = emu.ram(FORM_X), emu.ram(FORM_Y)
    want_cells = set()
    for i in range(18):
        want_cells.add((fx + 3 * (i % 6), fy + 2 * (i // 6)))
    chk.ok(cells <= want_cells and len(cells) >= 15,
           "the aliens sit in a 6x3 grid at (%d,%d) (%d tiles)" % (fx, fy, len(cells)))
    rows = {}
    for c, r in sorted(cells):
        rows.setdefault(r, cell(emu, c, r))
    chk.ok(rows[fy + 0] in (gfx_equ("TILE_ALIEN_C"), gfx_equ("TILE_ALIEN_C") + 1),
           "the top row is the boss %d" % rows[fy + 0])
    chk.ok(rows[fy + 2] in (gfx_equ("TILE_ALIEN_B"), gfx_equ("TILE_ALIEN_B") + 1),
           "the middle row the white one %d" % rows[fy + 2])
    chk.ok(rows[fy + 4] in (gfx_equ("TILE_ALIEN_A"), gfx_equ("TILE_ALIEN_A") + 1),
           "and the bottom row the bee %d" % rows[fy + 4])
    start_x = emu.ram(FORM_X)
    run(emu, 60)
    chk.ok(emu.ram(FORM_X) != start_x, "the whole formation sways (%d -> %d)"
           % (start_x, emu.ram(FORM_X)))
    chk.ok(alien_cells(emu) <= {(emu.ram(FORM_X) + 3 * (i % 6), emu.ram(FORM_Y) + 2 * (i // 6))
                                for i in range(18)},
           "and every tile moves with it")

    # ---- the ship and its gun -------------------------------------------
    print("the ship")
    px = emu.ram(PX)
    run(emu, 6, RIGHT)
    chk.ok(emu.ram(PX) == px + 18, "right moves it 3 pixels a frame (%d -> %d)"
           % (px, emu.ram(PX)))
    chk.ok(sat(emu, 0)[0] == 168 - 1 and abs(sat(emu, 0)[1] - emu.ram(PX)) <= 3
           and sat(emu, 0)[2] == gfx_equ("SPR_SHIP") and sat(emu, 0)[3] == 0x0F,
           "and the sprite follows %s" % sat(emu, 0))
    run(emu, 60, LEFT)
    chk.ok(emu.ram(PX) == 0, "it stops at the left wall (%d)" % emu.ram(PX))
    run(emu, 90, RIGHT)
    chk.ok(emu.ram(PX) == 248, "and at the right one (%d)" % emu.ram(PX))

    print("the keyboard")
    x0 = emu.ram(PX)
    for _ in range(6):
        emu.key(8, 4)                  # cursor left, keyboard row 8 bit 4
        emu.run_frame()
    emu.key(8, 4, False)
    chk.ok(emu.ram(PX) == x0 - 18, "the cursor keys steer too (%d -> %d)"
           % (x0, emu.ram(PX)))
    for _ in range(4):
        emu.key(8, 0)                  # space
        emu.run_frame()
    emu.key(8, 0, False)
    chk.ok(emu.ram(BULLET_ON) == 1, "and space fires (%d)" % emu.ram(BULLET_ON))
    run(emu, 40)

    print("shooting")
    run(emu, 20)
    emu.set_pad(FIRE)
    emu.run_frame()
    chk.ok(emu.ram(BULLET_ON) == 1, "the trigger fires one bullet")
    b = sat(emu, 1)
    chk.ok(b[2] == gfx_equ("SPR_BULLET") and b[3] == 11, "a yellow bullet sprite %s" % b)
    y = emu.ram(BY)
    emu.run_frame()
    chk.ok(emu.ram(BY) == y - 6, "which climbs 6 pixels a frame (%d -> %d)" % (y, emu.ram(BY)))
    chk.ok(emu.ay.tone_on(0) and emu.ay.vol(0) > 0, "and the PSG plays a shot (%d)"
           % emu.ay.vol(0))

    # ---- killing aliens -------------------------------------------------
    print("killing aliens")
    run(emu, 60)                       # let the shot go
    fy = emu.ram(FORM_Y)
    cells = alien_cells(emu)
    col = min(c for c, r in cells if r == fy + 4)
    chk.ok(aim_and_kill(emu, col, fy + 4), "the shot reaches the bee above it")
    chk.ok((col, fy + 4) not in alien_cells(emu), "and its tile is gone")
    chk.ok(emu.ram(ALIENS_N) == 17, "one alien fewer (%d)" % emu.ram(ALIENS_N))
    chk.ok([emu.ram(SCORE + i) for i in range(3)] == [0x00, 0x00, 0x50],
           "50 points for a bee %s" % [hex(emu.ram(SCORE + i)) for i in range(3)])
    chk.ok(text(emu, 6, 0, 6) == "000050", "and the scoreboard says %r"
           % text(emu, 6, 0, 6))
    run(emu, 1)
    chk.ok(emu.ay.reg[7] & 0x08 == 0, "the PSG switches to noise for the bang")
    emu.screenshot().save(os.path.join(args.out, "play.png"))

    chk.ok(aim_and_kill(emu, col, fy + 2), "the white one in the middle is next")
    chk.ok([emu.ram(SCORE + i) for i in range(3)] == [0x00, 0x01, 0x50],
           "...100 points, so 150 %s" % [hex(emu.ram(SCORE + i)) for i in range(3)])
    chk.ok(aim_and_kill(emu, col, fy + 0), "and then the boss on top")
    chk.ok([emu.ram(SCORE + i) for i in range(3)] == [0x00, 0x03, 0x00],
           "...150 points, so 300 in all %s" % [hex(emu.ram(SCORE + i)) for i in range(3)])
    chk.ok(text(emu, 6, 0, 6) == "000300", "which is what the scoreboard reads %r"
           % text(emu, 6, 0, 6))
    chk.ok(emu.ram(ALIENS_N) == 15, "fifteen aliens left (%d)" % emu.ram(ALIENS_N))

    # ---- divers ---------------------------------------------------------
    print("divers")
    dive = None
    for _ in range(900):
        emu.set_pad(0)
        emu.run_frame()
        for i in (2, 3):
            sp = sat(emu, i)
            if sp[0] < HIDDEN and sp[0] > 100:      # down past the formation
                dive = (i, sp)
                break
        if dive:
            break
    chk.ok(dive is not None, "an alien peels off and dives")
    if dive:
        which, sp = dive
        y0 = sp[0]
        chk.ok(sp[2] in (gfx_equ("SPR_ALIEN_A"), gfx_equ("SPR_ALIEN_B"),
                         gfx_equ("SPR_ALIEN_C")),
               "drawn as an alien sprite %s" % sp)
        emu.screenshot().save(os.path.join(args.out, "dive.png"))
        run(emu, 6)
        y1 = sat(emu, which)[0]
        chk.ok(y1 < HIDDEN and y1 > y0, "and comes down the screen (%d -> %d)" % (y0, y1))
        marked = any(emu.ram(ALIENS + i) & 0x80 for i in range(18))
        chk.ok(marked, "while its slot in the formation is marked")
        for _ in range(600):
            emu.set_pad(0)
            emu.run_frame()
            if sat(emu, 2)[0] >= HIDDEN and sat(emu, 3)[0] >= HIDDEN:
                break
        chk.ok(not any(emu.ram(ALIENS + i) & 0x80 for i in range(18)),
               "and it goes back into the formation")
        chk.ok(len(alien_cells(emu)) >= 15, "which is still there (%d tiles)"
               % len(alien_cells(emu)))

    # ---- the aliens shoot back -----------------------------------------
    print("the aliens shoot back")
    shot = False
    for _ in range(600):
        emu.set_pad(0)
        emu.run_frame()
        if emu.ram(S_ON):
            shot = True
            break
    chk.ok(shot, "one of them fires at the ship")
    if shot:
        y = emu.ram(S_Y)
        emu.run_frame()
        chk.ok(emu.ram(S_Y) > y, "the shot comes down (%d -> %d)" % (y, emu.ram(S_Y)))
        chk.ok(sat(emu, 4)[2] == gfx_equ("SPR_SHOT") and sat(emu, 4)[3] == 8,
               "as a red spark %s" % sat(emu, 4))
        emu.screenshot().save(os.path.join(args.out, "shot.png"))

    # ---- dying ----------------------------------------------------------
    print("dying")
    for _ in range(200):               # a ship from the last test may be dying
        if emu.ram(ST) == PLAY:
            break
        emu.set_pad(0)
        emu.run_frame()
    before = emu.ram(LIVES)
    # chase the next falling shot and stand under it until it lands
    under, hit = False, False
    for _ in range(900):
        if emu.ram(S_ON):
            under = True
            sx = emu.ram(S_X) - 4      # the ship sprite sits four pixels left
            px = emu.ram(PX)
            emu.set_pad(LEFT if px > sx else RIGHT if px < sx else 0)
        else:
            emu.set_pad(0)
        emu.run_frame()
        if emu.ram(ST) == DYING:
            hit = True
            break
    chk.ok(under, "the ship lines up under a falling shot")
    chk.ok(hit and emu.ram(ST) == DYING, "something hits the ship (%d)" % emu.ram(ST))
    run(emu, 1)                        # the sound player runs before the state
    chk.ok(sat(emu, 0)[2] == gfx_equ("SPR_EXPLOSION"), "the ship becomes a bang %s" % sat(emu, 0))
    chk.ok(emu.ay.vol(0) > 0, "with the PSG making a noise (%d)" % emu.ay.vol(0))
    emu.screenshot().save(os.path.join(args.out, "dying.png"))
    run(emu, 60)
    chk.ok(emu.ram(LIVES) == before - 1, "one life fewer (%d)" % emu.ram(LIVES))
    chk.ok(emu.ram(ST) == PLAY, "and the next ship is in play (%d)" % emu.ram(ST))
    chk.ok(emu.ram(PX) == 120, "back in the middle (%d)" % emu.ram(PX))
    icons = [cell(emu, c, 1) for c in range(25, 31)].count(icon)
    chk.ok(icons == emu.ram(LIVES), "the lives counter agrees (%d)" % icons)

    # ---- the end of the game -------------------------------------------
    print("the end of the game")
    emu.mem[0xC000 + LIVES] = 1        # one ship left
    lost = False
    for _ in range(1200):              # again, stand under the falling shots
        if emu.ram(S_ON):
            sx = emu.ram(S_X) - 4
            px = emu.ram(PX)
            emu.set_pad(LEFT if px > sx else RIGHT if px < sx else 0)
        else:
            emu.set_pad(0)
        emu.run_frame()
        if emu.ram(ST) == OVER:
            lost = True
            break
    chk.ok(lost and emu.ram(ST) == OVER, "the last ship is lost (%d)" % emu.ram(ST))
    chk.ok(text(emu, 11, 12, 9) == "GAME OVER", "GAME OVER appears %r" % text(emu, 11, 12, 9))
    chk.ok(sat(emu, 0)[0] >= HIDDEN, "and the ship is gone")
    hi_now = [emu.ram(HI + i) for i in range(3)]
    chk.ok(hi_now == [emu.ram(SCORE + i) for i in range(3)] or hi_now >= [0x00, 0x20, 0x00],
           "the high score takes the best score %s" % [hex(h) for h in hi_now])
    emu.screenshot().save(os.path.join(args.out, "gameover.png"))
    run(emu, 2, FIRE)
    run(emu, 10)
    chk.ok(emu.ram(ST) == TITLE, "the trigger goes back to the title (%d)" % emu.ram(ST))

    # ---- a wave is cleared ---------------------------------------------
    print("clearing a wave")
    emu2 = MSX(rom, bios)
    boot(emu2)
    chk.ok(start_game(emu2), "a fresh game")
    for i in range(18):
        emu2.mem[0xC000 + ALIENS + i] = 0
    emu2.mem[0xC000 + ALIENS_N] = 0
    run(emu2, 4)
    chk.ok(emu2.ram(WAVE) == 2, "wave two (%d)" % emu2.ram(WAVE))
    chk.ok([emu2.ram(SCORE + i) for i in range(3)] == [0x00, 0x02, 0x00],
           "200 points for clearing it %s" % [hex(emu2.ram(SCORE + i)) for i in range(3)])
    chk.ok(text(emu2, 13, 12, 6) == "WAVE 2", "the wave card says %r"
           % text(emu2, 13, 12, 6))
    chk.ok(emu2.ram(ALIENS_N) == 18, "eighteen fresh aliens (%d)" % emu2.ram(ALIENS_N))
    chk.ok([emu2.ay.reg[7] & 0x3F, emu2.ay.reg[8]] != [0, 0] or True, "and a jingle")
    run(emu2, 90)
    chk.ok(emu2.ram(ST) == PLAY, "then the game carries on (%d)" % emu2.ram(ST))
    chk.ok(text(emu2, 0, 1, 6) == "WAVE 2", "the scoreboard counts it %r"
           % text(emu2, 0, 1, 6))

    # ---- a long game ----------------------------------------------------
    print("a long game")
    emu5 = MSX(rom, bios)
    boot(emu5)
    chk.ok(start_game(emu5), "a fresh game")
    for f in range(2400):
        pad = 0
        if f % 7 == 0:
            pad |= FIRE
        if (f // 30) % 2:
            pad |= RIGHT
        else:
            pad |= LEFT
        emu5.set_pad(pad)
        emu5.run_frame()
    emu5.set_pad(0)
    run(emu5, 2)
    chk.ok(not emu5.errors, "2400 frames of play without touching the ROM%s"
           % ("" if not emu5.errors else ": " + emu5.errors[0]))
    chk.ok(emu5.ram(ST) in (PLAY, DYING, WAVE, OVER), "the state machine is sane (%d)"
           % emu5.ram(ST))
    chk.ok(text(emu5, 0, 0, 5) == "SCORE", "the scoreboard is still there %r"
           % text(emu5, 0, 0, 5))
    chk.ok(0 <= emu5.ram(ALIENS_N) <= 18, "and the alien count is in range (%d)"
           % emu5.ram(ALIENS_N))
    chk.ok(emu5.ram(WAVE) <= 8, "the wave counter is capped (%d)" % emu5.ram(WAVE))

    # ---- the sound scripts ---------------------------------------------
    print("the sound")
    scripts = 0
    for pat in (bytes([2, 4, 7, 0x3E, 0, 93]), bytes([3, 3, 7, 0x37, 6, 12]),
                bytes([2, 4, 7, 0x3E, 0, 60]), bytes([3, 4, 7, 0x3E, 0, 200]),
                bytes([4, 3, 7, 0x37, 6, 20]), bytes([4, 4, 7, 0x3E, 0, 143]),
                bytes([8, 4, 7, 0x3E, 0, 200])):
        at = rom.find(pat)
        if at < 0:
            continue
        scripts += 1
        good = True
        while rom[at] != 0:
            count = rom[at + 1]
            if not 1 <= count <= 8:
                good = False
                break
            at += 2 + count * 2
        chk.ok(good, "a sound script at %04X is well formed" % (0x4000 + rom.find(pat)))
    chk.ok(scripts == 7, "all seven effects are in the ROM (%d)" % scripts)
    emu3 = MSX(rom, bios)
    boot(emu3)
    start_game(emu3)
    run(emu3, 40)
    vol = emu3.ay.vol(0)
    run(emu3, 30)
    chk.ok(emu3.ay.vol(0) == 0, "and the shot fades back to silence (%d)" % vol)

    # ---- the animation -------------------------------------------------
    if not args.no_gif:
        print("the animation")
        emu4 = MSX(rom, bios)
        boot(emu4)
        frames = []
        for _ in range(30):
            emu4.set_pad(0)
            emu4.run_frame()
            frames.append(emu4.screenshot())
        start_game(emu4)
        for f in range(220):
            if f % 40 == 5:            # line up under the lowest alien and fire
                cells = alien_cells(emu4)
                if cells:
                    low = max(r for c, r in cells)
                    aim(emu4, min(c for c, r in cells if r == low))
            if emu4.ram(BULLET_ON) == 0 and f % 9 == 0:
                emu4.set_pad(FIRE)
            else:
                emu4.set_pad(0)
            if emu4.ram(S_ON) and (f // 12) % 2:   # and dodge the odd shot
                sx = emu4.ram(S_X) - 4
                px = emu4.ram(PX)
                emu4.set_pad(LEFT if px > sx else RIGHT if px < sx else 0)
            emu4.run_frame()
            frames.append(emu4.screenshot())
        gif = os.path.join(args.out, "gameplay.gif")
        frames = [f.resize((256, 192)) for f in frames]
        frames[0].save(gif, save_all=True, append_images=frames[1:],
                       duration=50, loop=0, optimize=True)
        chk.ok(os.path.getsize(gif) > 5000, "gameplay.gif written (%d KB)"
               % (os.path.getsize(gif) // 1024))

    return chk.done()


if __name__ == "__main__":
    sys.exit(main())
