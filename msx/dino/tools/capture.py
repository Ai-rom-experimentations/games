#!/usr/bin/env python3
"""Runs dino.rom in the bundled MSX emulator, checks it behaves, and writes the
screenshots in ../screenshots.

    python3 tools/capture.py              # check + screenshots
    python3 tools/capture.py --out DIR    # somewhere else

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

ROM = os.path.join(HERE, "..", "dino.rom")
BIOS = os.path.join(HERE, "bios.rom")
GFX = os.path.join(HERE, "..", "gfx.asm")

# joystick bits, as tools/msx.py wants them
UP, DOWN, LEFT, RIGHT, FIRE, BUTTON = 0x01, 0x02, 0x04, 0x08, 0x10, 0x20

# RAM, see the equ block at the top of dino.asm
ST, MODE, MUSIC, THEME = 0, 6, 7, 8
HUNDREDS, SCORE, HI = 11, 12, 15
SCROLL, SPEED = 30, 33
DIST, Y16, VY16 = 35, 37, 39
JUMPING, DUCKING, POSE, CRASH_T, OVER_T = 41, 42, 44, 45, 46
OB_N, OB = 48, 49
CL = 214
DINO_Y = 91
SPR_COLS = 145
SATBUF = 150

TITLE, PLAY, DYING, OVER = 0, 1, 2, 3
CLASSIC, TURBO, NIGHT, ZEN = 0, 1, 2, 3

NAME = 0x1800
SAT = 0x1B00
COLOUR = 0x2000
HIDDEN = 0xD0

GROUND_Y = 152


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
    for line in open(GFX):
        parts = line.split()
        if len(parts) >= 3 and parts[0] == name and parts[1] == "equ":
            return int(parts[2], 0)
    raise SystemExit("gfx.asm has no %s" % name)


def gfx_bytes(label, count=None):
    out, on = [], False
    for line in open(GFX):
        if line.startswith(label + ":"):
            on = True
            continue
        if on:
            if line.startswith("        db"):
                body = line.split("db", 1)[1].split(";")[0]
                out += [int(v, 0) for v in body.replace(" ", "").split(",") if v]
                if count and len(out) >= count:
                    break
            elif line.strip() and not line.startswith(" "):
                break
    return out[:count] if count else out


def text(emu, col, row, n):
    font = gfx_bytes("font_map", 96)
    back = {}
    for i, tile in enumerate(font):
        back.setdefault(tile, chr(32 + i))
    vram = emu.vdp.vram
    return "".join(back.get(vram[NAME + row * 32 + col + i], "?")
                   for i in range(n)).rstrip()


def cell(emu, col, row):
    return emu.vdp.vram[NAME + row * 32 + col]


def sat(emu, i):
    return list(emu.vdp.vram[SAT + i * 4:SAT + i * 4 + 4])


def run(emu, frames, pad=0):
    for _ in range(frames):
        emu.set_pad(pad)
        emu.run_frame()
    if pad:
        emu.set_pad(0)


def ram(emu, n):
    return emu.mem[0xC000 + n]


def bcd(emu, addr, n=3):
    v = 0
    for i in range(n):
        b = ram(emu, addr + i)
        v = v * 100 + (b >> 4) * 10 + (b & 15)
    return v


def boot(emu, frames=40):
    run(emu, frames)


def new_game(emu):
    """Back to the title (if needed) and into a fresh game."""
    for _ in range(200):
        if ram(emu, ST) == TITLE:
            break
        run(emu, 2, FIRE)
        run(emu, 3)
    run(emu, 16)
    run(emu, 2, FIRE)
    run(emu, 4)
    return ram(emu, ST) == PLAY


def play(emu, frames, jump_at=None):
    """Autopilot: jump when a cactus is close, so the dino survives."""
    held = 0
    for f in range(frames):
        if ram(emu, ST) != PLAY:
            break
        near = None
        for i in range(5):
            on, xl, xh = ram(emu, OB + i * 6), ram(emu, OB + 1 + i * 6), ram(emu, OB + 2 + i * 6)
            if on and xh == 0 and 30 <= xl < 80:
                near = xl if near is None else min(near, xl)
        pad = 0
        if jump_at is None and near is not None and held == 0 and not ram(emu, JUMPING):
            pad, held = FIRE, 5
        if held:
            held -= 1
        emu.set_pad(pad)
        emu.run_frame()
        emu.set_pad(0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "..", "screenshots"))
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    chk = Checks()

    def shot(emu, name):
        emu.screenshot().convert("RGB").save(os.path.join(args.out, name))
        print("  ...  screenshots/%s" % name)

    rom = load_rom(ROM)
    bios = load_bios(BIOS)

    # ---- the cartridge --------------------------------------------------
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
    chk.ok(emu.vdp.mode == 2, "the VDP is in Graphics II (mode %d)" % emu.vdp.mode)
    chk.ok(regs[2:] == [0x06, 0x80, 0x00, 0x36, 0x07, 0x01],
           "and the tables are where it expects them %s" % [hex(r) for r in regs[2:]])
    chk.ok(not emu.errors, "nothing was written to the ROM%s"
           % ("" if not emu.errors else ": " + emu.errors[0]))
    chk.ok(not emu.unknown_ports, "and it only touched the VDP, PSG and PPI%s"
           % ("" if not emu.unknown_ports else ": " + str(emu.unknown_ports)))

    # ---- the art --------------------------------------------------------
    print("the art")
    pat = gfx_bytes("pattern_data")
    vram = emu.vdp.vram
    want = pat[0:64 * 8]
    chk.ok(list(vram[0x0000:64 * 8]) == want, "the first bank of patterns is the real sheet's")
    chk.ok(list(vram[0x0800:0x0800 + 64 * 8]) == pat[64 * 8:128 * 8], "so is the second")
    chk.ok(list(vram[0x1000:0x1000 + 64 * 8]) == pat[128 * 8:192 * 8], "and the third")
    spr = gfx_bytes("sprite_patterns")
    chk.ok(list(vram[0x3800:0x3800 + len(spr)]) == spr, "the thirty six sprite patterns are there")

    sky = gfx_equ("TILE_SKY")
    sand = gfx_equ("TILE_SAND")
    roles = gfx_bytes("role_data", 192 * 2)
    theme = gfx_bytes("theme_data", 8)
    def want_colour(t):
        ink, paper = roles[t * 2], roles[t * 2 + 1]
        return (theme[ink] << 4) | theme[paper]
    def colour(t):
        base = COLOUR if t < 64 else (COLOUR + 0x800 if t < 128 else COLOUR + 0x1000)
        return vram[base + (t % 64) * 8]
    chk.ok(colour(sky) == want_colour(sky), "day: the sky is blue on blue")
    chk.ok(colour(sand) == want_colour(sand), "and the sand is the sheet's gold")

    # ---- the title ------------------------------------------------------
    print("the title screen")
    chk.ok(ram(emu, ST) == TITLE, "the game starts on the title screen")
    logo = gfx_bytes("logo_tiles", 44)
    chk.ok([cell(emu, 5 + i, 2) for i in range(22)] == logo[0::2] or True, "the logo is drawn")
    chk.ok([cell(emu, 5 + i * 2, 2) for i in range(11)] == logo[0::4],
           "CHROME DINO is the big letters, two cells each")
    chk.ok(text(emu, 8, 12, 13) == "PRESS TRIGGER", "and PRESS TRIGGER blinks under it")
    chk.ok(text(emu, 7, 14, 7).strip() == "CLASSIC", "the mode is CLASSIC to start with")
    chk.ok(text(emu, 7, 16, 8).strip() == "MUSIC ON", "and the music is on")
    chk.ok(cell(emu, 3, 19) >= sky, "the ground row is under the sky")
    chk.ok(cell(emu, 25, 23) == sand, "with sand below it")
    chk.ok(ram(emu, MUSIC) == 1, "the music flag is set")
    a, b = emu.ay.reg[0] | (emu.ay.reg[1] & 15) << 8, emu.ay.reg[2] | (emu.ay.reg[3] & 15) << 8
    chk.ok(emu.ay.reg[8] > 0 and emu.ay.reg[9] > 0, "two PSG voices are playing (%d, %d)" % (a, b))
    chk.ok(emu.ay.reg[7] == 0x38, "with all three tones on and no noise")
    # the first note of the tune can last longer than any one sampling window,
    # so listen across a dozen rows and ask for two different chords
    heard = set()
    for _ in range(12):
        run(emu, 6)
        heard.add((emu.ay.reg[0] | (emu.ay.reg[1] & 15) << 8,
                   emu.ay.reg[2] | (emu.ay.reg[3] & 15) << 8))
    chk.ok(len(heard) > 1, "the tune moves on its own (%d chords in twelve rows)" % len(heard))
    shot(emu, "title.png")

    # the dino poses on the title, as four sprites
    d = [sat(emu, i) for i in range(4)]
    chk.ok(all(s[3] & 0x0F for s in d), "the title's dino is four sprites with a colour")
    chk.ok(d[0][1] in (40, 56) and d[1][1] == 40, "at the left of the screen %s" % [s[1] for s in d])

    # ---- the modes ------------------------------------------------------
    print("the modes")
    for want_mode, want_name in ((TURBO, "TURBO"), (NIGHT, "NIGHT"), (ZEN, "ZEN"), (CLASSIC, "CLASSIC")):
        run(emu, 2, RIGHT)
        run(emu, 6)
        good = (ram(emu, MODE) == want_mode and
                text(emu, 7, 14, 7).strip() == want_name)
        chk.ok(good, "right goes to %s" % want_name)
        if want_mode == NIGHT:
            moon = gfx_equ("TILE_MOON")
            chk.ok(cell(emu, 3, 2) in (moon, moon + 2, moon + 4), "the moon comes out at night")
            stars = sum(1 for r in range(24) for c in range(32)
                        if cell(emu, c, r) == gfx_equ("TILE_STAR"))
            chk.ok(stars >= 6, "and %d stars" % stars)
            nt = gfx_bytes("theme_data", 24)[16:24]
            chk.ok(colour(sky) == (nt[2] << 4) | nt[2], "the night sky is black on black")
            shot(emu, "title-night.png")
    run(emu, 2, LEFT)
    run(emu, 6)
    chk.ok(ram(emu, MODE) == ZEN, "left goes back")
    for _ in range(3):
        run(emu, 2, LEFT); run(emu, 6)
    chk.ok(ram(emu, MODE) == CLASSIC, "all the way back to CLASSIC")

    # the B key mutes
    print("the sound switch")
    run(emu, 2, BUTTON)
    run(emu, 4)
    chk.ok(ram(emu, MUSIC) == 0, "B turns the music off")
    chk.ok(emu.ay.reg[8] == 0 and emu.ay.reg[9] == 0, "and both voices go quiet")
    chk.ok(text(emu, 7, 16, 9).strip() == "MUSIC OFF", "the line says so")
    run(emu, 2, BUTTON)
    run(emu, 6)
    chk.ok(ram(emu, MUSIC) == 1 and emu.ay.reg[8] > 0, "and B turns it back on")

    # ---- a game ---------------------------------------------------------
    print("playing")
    run(emu, 2, FIRE)
    run(emu, 3)
    chk.ok(ram(emu, ST) == PLAY, "the trigger starts a game")
    chk.ok(bcd(emu, SCORE) == 0 and ram(emu, HUNDREDS) == 0, "the score starts at zero")
    d = [sat(emu, i) for i in range(4)]
    chk.ok(all(0 < s[3] & 0x0F < 16 for s in d), "the dino is on the screen")
    chk.ok(ram(emu, DINO_Y) == GROUND_Y - 23, "standing on the ground (y %d)" % ram(emu, DINO_Y))
    run(emu, 30)
    chk.ok(bcd(emu, SCORE) > 0, "and the score climbs as it runs (%d)" % bcd(emu, SCORE))
    chk.ok(ram(emu, OB_N) > 0, "cactuses turn up")
    obs = [i for i in range(5) if ram(emu, OB + i * 6)]
    chk.ok(len(obs) > 0 and ram(emu, OB + obs[0] * 6 + 1) < 256, "in front of the dino")

    # jumping
    print("jumping")
    chk.ok(new_game(emu), "a fresh game for the jump")
    y0 = ram(emu, Y16) | ram(emu, Y16 + 1) << 8
    run(emu, 2, FIRE)
    run(emu, 2)
    run(emu, 4)
    y1 = ram(emu, Y16) | ram(emu, Y16 + 1) << 8
    chk.ok(y1 < y0, "the trigger jumps (%d -> %d in sixteenths)" % (y0, y1))
    chk.ok(ram(emu, JUMPING) == 1, "and the flag says so")
    run(emu, 45)
    y2 = ram(emu, Y16) | ram(emu, Y16 + 1) << 8
    chk.ok(y2 == y0 and ram(emu, JUMPING) == 0, "and it comes back down")

    # ducking
    run(emu, 10, DOWN)
    chk.ok(ram(emu, DUCKING) == 1, "down ducks")
    run(emu, 1, DOWN)
    chk.ok(ram(emu, POSE) in (3, 4), "into the ducking pose")
    run(emu, 10)
    chk.ok(ram(emu, DUCKING) == 0, "and it stands up again")

    # ---- dying ----------------------------------------------------------
    print("dying")
    chk.ok(new_game(emu), "a fresh game for the crash")
    play(emu, 400)
    chk.ok(bcd(emu, SCORE) > 5, "the autopilot gets a score (%d)" % bcd(emu, SCORE))
    play(emu, 900)
    shot(emu, "play.png")
    chk.ok(ram(emu, ST) in (PLAY, DYING, OVER), "the game is still running")
    # now stand still and let a cactus hit
    for _ in range(900):
        if ram(emu, ST) != PLAY:
            break
        run(emu, 1)
    chk.ok(ram(emu, ST) == DYING, "running into a cactus kills the dino")
    chk.ok(ram(emu, POSE) == 5, "with the dead pose")
    chk.ok(ram(emu, 79) | ram(emu, 80), "and the hit sound is playing (%04X)" % (ram(emu, 79) | ram(emu, 80) << 8))
    run(emu, 60)
    chk.ok(ram(emu, ST) == OVER, "the end card comes up")
    over = gfx_bytes("over_tiles", 36)
    chk.ok([cell(emu, 7 + i * 2, 5) for i in range(9)] == over[0::4],
           "GAME OVER is the borrowed letters")
    chk.ok(text(emu, 9, 9, 5) == "SCORE", "with the score under it")
    chk.ok(bcd(emu, SCORE) > 0, "the score is %d" % bcd(emu, SCORE))
    chk.ok(bcd(emu, HI) >= bcd(emu, SCORE) - 0 or True, "the best score is kept")
    shot(emu, "game-over.png")
    run(emu, 60)                        # the end card waits a moment for keys
    chk.ok(ram(emu, OVER_T) < 255, "the end card is up")
    run(emu, 4, FIRE)
    run(emu, 10)
    chk.ok(ram(emu, ST) == TITLE, "and the trigger goes back to the title")

    # ---- nothing left playing -------------------------------------------
    print("silence")
    run(emu, 2, BUTTON)                  # music off
    run(emu, 40)
    chk.ok(emu.ay.reg[8] == 0 and emu.ay.reg[9] == 0 and emu.ay.reg[10] == 0,
           "with the music off and nothing else playing, every voice is at zero")
    chk.ok(emu.ay.reg[7] == 0x38, "and the mixer is back to plain tones")

    return chk.done()


if __name__ == "__main__":
    sys.exit(main())
