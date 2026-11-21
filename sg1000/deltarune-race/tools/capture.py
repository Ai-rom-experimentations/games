#!/usr/bin/env python3
"""Runs deltarune.sg headlessly: sanity checks the minigame, writes screenshots.

    python3 tools/capture.py

Needs `pip install z80 pillow`.  Exit status is non zero if a check fails.
"""
import argparse
import os
import sys

try:
    import z80            # noqa: F401  (the Z80 core)
    from PIL import Image  # noqa: F401  (screenshots / gif)
except ImportError as exc:
    sys.exit("missing dependency '%s' - run: pip install z80 pillow" % exc.name)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from sg1000 import SG1000, load_rom, P1_UP, P1_DOWN, P1_LEFT, P1_RIGHT, P1_B1, P1_B2

# ---- RAM map (keep in sync with deltarune.asm) ---------------------------
R_STATE, R_PAD1, R_PAUSED = 0, 1, 3
R_PX, R_PY, R_RX, R_RY, R_SEG, R_CP, R_LAPS, R_RLAPS = 7, 8, 9, 10, 11, 12, 13, 14
R_DLG = 22                              # 0 off, 1 typing, 2 finished

TITLE, RACE, WON, LOST = 0, 1, 2, 3

# ---- screen layout (keep in sync with gfx.asm) ---------------------------
TILE_FONT = 13
T_BLANK = 0
T_TOP, T_BOTTOM, T_LEFT, T_RIGHT = 1, 2, 3, 4
T_TL, T_TR, T_BL, T_BR = 5, 6, 7, 8
T_CHK = (9, 10, 11, 12)                 # chequered line (also its wall row)
OUT_L, OUT_R, OUT_T, OUT_B = 1, 30, 1, 22
IN_L, IN_R, IN_T, IN_B = 8, 23, 7, 16
FINISH_COL = 15                          # two columns wide, 15 and 16
FINISH_X = FINISH_COL * 8
FINISH_RIGHT = FINISH_X + 16
HUD1 = (12, 9)
HUD2 = (11, 12)
CAR = 8                                  # both squares are 8x8

# ---- the dialogue box and the portrait (keep in sync with gfx.asm) ------
DLG_T, DLG_B = 17, 23                    # the box overwrites rows 17..23
DLG_X, DLG_XR = OUT_L, OUT_R
DLG_TEXT = (8, 18, 20, 22)               # the three text rows
PORTRAIT_BASE = 32
PORTRAIT_SAT = 0x1B00
PORTRAIT_PATS = 0x3800 + PORTRAIT_BASE * 8
PORTRAIT_BYTES = 40 * 8
PORTRAIT_Y, PORTRAIT_X = 143, 24
DLG_WIN1 = "SUSIE: HOW THE HECK..."
DLG_WIN2 = "ALRIGHT, WE'RE DONE."
DLG_LOSE1 = "SUSIE: MAN, IT'S LIKE"
DLG_LOSE2 = "YOU'RE NOT EVEN"
DLG_LOSE3 = "LOOKING AT THE SCREEN."


def hold(emu, frames, p1=0, p2=0):
    emu.set_pads(p1=p1, p2=p2)
    for _ in range(frames):
        emu.run_frame()


def nmi(emu):
    """What the console HOLD button does: push PC, jump to $0066."""
    sp = (emu.cpu.sp - 2) & 0xFFFF
    emu.mem[sp] = emu.cpu.pc & 0xFF
    emu.mem[(sp + 1) & 0xFFFF] = (emu.cpu.pc >> 8) & 0xFF
    emu.cpu.sp = sp
    emu.cpu.pc = 0x0066


def steer(px, py):
    """A tidy clockwise lap: up the left straight, along the top, down the
    right straight and back along the bottom straight."""
    if py >= IN_B * 8 + 8:               # bottom straight
        return P1_UP if px <= 24 else P1_LEFT
    if px <= IN_L * 8 - 1:               # left straight
        return P1_RIGHT if py <= 24 else P1_UP
    if py <= IN_T * 8 - 1:               # top straight
        return P1_DOWN if px >= 231 else P1_RIGHT
    return P1_LEFT if py >= 166 else P1_DOWN


def tile(emu, col, row):
    return emu.vdp.vram[0x1800 + row * 32 + col]


def text(emu, col, row, length):
    return "".join(chr(32 + tile(emu, col + i, row) - TILE_FONT) for i in range(length))


class Checks:
    def __init__(self):
        self.items = []

    def ok(self, cond, text):
        self.items.append((bool(cond), text))
        print(("  ok   " if cond else "  FAIL ") + text)
        return cond

    def failed(self):
        return [t for good, t in self.items if not good]


def boot(rom, frames=45):
    emu = SG1000(rom)
    for _ in range(frames):
        emu.run_frame()
    return emu


def start_race(emu):
    hold(emu, 4, p1=P1_B1)
    hold(emu, 4)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rom", default=os.path.join(HERE, "..", "deltarune.sg"))
    ap.add_argument("--out", default=os.path.join(HERE, "..", "screenshots"))
    args = ap.parse_args()

    rom = load_rom(args.rom)
    os.makedirs(args.out, exist_ok=True)
    chk = Checks()

    print("boot")
    emu = boot(rom)
    chk.ok(emu.ram(R_STATE) == TITLE, "boots to the title screen")
    chk.ok(text(emu, 11, 8, 9) == "DELTARUNE", "the title screen says DELTARUNE")
    chk.ok(text(emu, 11, 9, 9) == "CHAPTER 3", "and CHAPTER 3")
    chk.ok(text(emu, 10, 11, 13) == "HIDDEN RACING", "and HIDDEN RACING")
    chk.ok(text(emu, 12, 12, 8) == "MINIGAME", "and MINIGAME")
    chk.ok(text(emu, 13, 14, 6) == "3 LAPS" and text(emu, 10, 15, 13) == "PRESS 1: RACE",
           "and the 3 lap / PRESS 1 instructions")
    emu.screenshot().save(os.path.join(args.out, "title.png"))

    print("the track")
    lanes = [(OUT_L, OUT_T, T_TL), (OUT_R, OUT_T, T_TR),
             (OUT_L, OUT_B, T_BL), (OUT_R, OUT_B, T_BR),
             (IN_L, IN_T, T_TL), (IN_R, IN_T, T_TR),
             (IN_L, IN_B, T_BL), (IN_R, IN_B, T_BR),
             (5, OUT_T, T_TOP), (5, OUT_B, T_BOTTOM),
             (OUT_L, 10, T_LEFT), (OUT_R, 10, T_RIGHT),
             (IN_L, 10, T_LEFT), (IN_R, 10, T_RIGHT)]
    bad = [(c, r) for c, r, t in lanes if tile(emu, c, r) != t]
    chk.ok(not bad, "white outline around the track and around the middle square %s" % bad)
    chk.ok(all(tile(emu, c, r) in T_CHK for c in (FINISH_COL, FINISH_COL + 1)
               for r in (IN_B + 1, OUT_B)), "chequered finish line at the bottom")
    chk.ok(tile(emu, FINISH_COL, 10) not in T_CHK,
           "the line only runs along the bottom straight")
    chk.ok(tile(emu, 4, 10) == T_BLANK and tile(emu, 26, 10) == T_BLANK,
           "the track itself is black")

    print("the grid")
    px, py = emu.ram(R_PX), emu.ram(R_PY)
    chk.ok(px >= FINISH_RIGHT, "the car starts right of the finish line (x=%d)" % px)
    chk.ok(py >= IN_B * 8 + 8, "in the bottom straight (y=%d)" % py)
    chk.ok(emu.ram(R_RX) < FINISH_X, "Susie starts left of it (x=%d)" % emu.ram(R_RX))

    print("pause")
    mut = (emu.ram(R_PX), emu.ram(R_PY))
    hold(emu, 1, p1=P1_B2)
    chk.ok(emu.ram(R_PAUSED) == 1, "button 2 pauses")
    hold(emu, 1, p1=P1_B1)                          # cannot start while paused
    hold(emu, 8)
    chk.ok(emu.ram(R_STATE) == TITLE and (emu.ram(R_PX), emu.ram(R_PY)) == mut,
           "a paused game ignores the pad")
    hold(emu, 1, p1=P1_B2)
    chk.ok(emu.ram(R_PAUSED) == 0, "button 2 resumes")
    hold(emu, 2)
    nmi(emu)
    hold(emu, 2)
    chk.ok(emu.ram(R_PAUSED) == 1, "HOLD (the console button) pauses as well")
    nmi(emu)
    hold(emu, 2)
    chk.ok(emu.ram(R_PAUSED) == 0, "and unpauses")

    print("button 1 starts a race")
    start_race(emu)
    chk.ok(emu.ram(R_STATE) == RACE, "button 1 starts the race")
    chk.ok(emu.ram(R_LAPS) == 0 and emu.ram(R_RLAPS) == 0, "the lap counters start at 0")
    chk.ok(text(emu, HUD1[0], HUD1[1], 7) == "LAP 1/3", "the infield shows LAP 1/3")
    chk.ok(text(emu, HUD2[0], HUD2[1], 9) == "SUSIE 1/3", "and SUSIE 1/3")

    # ---- the sprites really are two 8x8 squares in those colours
    sat = emu.vdp.vram[0x1B00:0x1B08]
    chk.ok(list(sat[0:4]) == [emu.ram(R_PY) - 1, emu.ram(R_PX), 0, 0x0F],
           "sprite 0 is the white square at the car's position %s" % list(sat[0:4]))
    chk.ok(list(sat[4:8]) == [emu.ram(R_RY) - 1, emu.ram(R_RX), 0, 0x0D],
           "sprite 1 is Susie in magenta %s" % list(sat[4:8]))
    chk.ok(all(v == 0xFF for v in emu.vdp.vram[0x3800:0x3808]),
           "the sprite pattern is a solid 8x8 block")

    print("walls stop the square")
    thud = 0
    for _ in range(40):                              # straight into the middle
        emu.set_pads(p1=P1_UP)
        emu.run_frame()
        if emu.psg.vol[3] < 15:
            thud += 1
    chk.ok(emu.ram(R_PY) >= IN_B * 8 + 1 and emu.ram(R_PX) == px,
           "the middle square blocks a square driving up (y=%d)" % emu.ram(R_PY))
    chk.ok(thud > 0 and emu.psg.tone[3] & 0x04, "hitting it thuds (white noise on channel 3)")
    chk.ok(thud <= 4, "and the thud is short (%d frames)" % thud)
    hold(emu, 120, p1=P1_RIGHT)                      # and into the outer wall
    chk.ok(emu.ram(R_PX) == 238 and emu.ram(R_PY) >= IN_B * 8,
           "the outer wall stops the square too (x=%d)" % emu.ram(R_PX))

    print("a lap only counts when it is a lap")
    emu.mem[0xC000 + R_PX] = 140                     # back on the grid
    emu.mem[0xC000 + R_PY] = 155
    hold(emu, 40, p1=P1_LEFT)                        # over the line backwards
    hold(emu, 40, p1=P1_RIGHT)                       # and forwards again
    chk.ok(emu.ram(R_LAPS) == 0, "wiggling over the line does not score a lap")

    print("three laps")
    frames = []
    laps_seen = set()
    hud1 = None
    for f in range(1500):
        emu.set_pads(p1=steer(emu.ram(R_PX), emu.ram(R_PY)))
        emu.run_frame()
        laps_seen.add(emu.ram(R_LAPS))
        if emu.ram(R_LAPS) == 1 and hud1 is None:
            hud1 = text(emu, HUD1[0], HUD1[1], 7)
        if f % 2 == 0:
            frames.append(emu.screenshot())
        if emu.ram(R_STATE) != RACE:
            break
    chk.ok({0, 1, 2, 3} <= laps_seen, "three clockwise laps are counted %s" % sorted(laps_seen))
    chk.ok(hud1 == "LAP 2/3", "the infield counts the laps (%r)" % hud1)
    chk.ok(emu.ram(R_STATE) == WON, "the third lap wins the race")
    chk.ok(text(emu, 13, 9, 7) == "YOU WIN", "the win screen says YOU WIN")
    chk.ok(text(emu, 13, 13, 7) == "PRESS 1", "and offers another go")

    print("the dialogue box")
    chk.ok(tile(emu, 15, DLG_T) == T_TOP and tile(emu, 15, DLG_B) == T_BOTTOM,
           "a box covers the bottom of the screen (rows %d..%d)" % (DLG_T, DLG_B))
    chk.ok(tile(emu, DLG_X, 20) == T_LEFT and tile(emu, DLG_XR, 20) == T_RIGHT,
           "with a white outline down its sides")
    chk.ok(all(tile(emu, c, 20) == T_BLANK for c in range(3, 30)),
           "and black inside, over what was the bottom straight")
    chk.ok(emu.ram(R_DLG) == 1, "Susie's line starts typing itself out")
    typing = text(emu, DLG_TEXT[0], DLG_TEXT[1], 6)
    chk.ok(len(typing.strip()) > 0, "one letter at a time (%r)" % typing.strip())
    hold(emu, 2, p1=P1_B1)                           # hurry it up
    hold(emu, 2)
    chk.ok(emu.ram(R_DLG) == 2 and text(emu, DLG_TEXT[0], DLG_TEXT[1], 22) == DLG_WIN1,
           "button 1 finishes the line: %r" % text(emu, DLG_TEXT[0], DLG_TEXT[1], 22))
    chk.ok(text(emu, DLG_TEXT[0], DLG_TEXT[2], len(DLG_WIN2)) == DLG_WIN2,
           "and the next one: %r" % DLG_WIN2)
    sat_win = bytes(emu.vdp.vram[PORTRAIT_SAT:PORTRAIT_SAT + 81])
    pats_win = bytes(emu.vdp.vram[PORTRAIT_PATS:PORTRAIT_PATS + PORTRAIT_BYTES])
    chk.ok(list(sat_win[0:4]) == [PORTRAIT_Y, PORTRAIT_X, PORTRAIT_BASE, 0x0D],
           "Susie's portrait sits on the left of the box %s" % list(sat_win[0:4]))
    chk.ok(sat_win[80] == 0xD0, "and the sprite table ends after it")
    chk.ok(sum(1 for i in range(0, 80, 4) if sat_win[i] != 0xD0) == 20,
           "20 sprites: a 4x5 grid of cells")
    white = [i for i in range(0, 80, 4) if sat_win[i + 3] == 0x0F]
    eye = 9 * 4                            # row 2, column 1 of the 4x5 grid
    chk.ok(white == [eye] and sat_win[eye + 2] == PORTRAIT_BASE + 9,
           "the eye cell (%d) is the one white cell of the portrait %s" % (eye // 4, white))
    chk.ok(pats_win != bytes(PORTRAIT_BYTES), "the portrait patterns are uploaded to $3800+")
    glyphs = range(TILE_FONT, TILE_FONT + 40)
    outside = [(c, 10) for c in range(24, 31)] + [(c, 9) for c in range(20, 23)]
    chk.ok(not [1 for c, r in outside if tile(emu, c, r) in glyphs],
           "the infield text stays inside the middle square")
    emu.screenshot().save(os.path.join(args.out, "win.png"))

    print("the little tunes")
    emu2 = boot(rom)
    notes = []
    emu2.set_pads(p1=P1_B1)
    for _ in range(14):
        emu2.run_frame()
        if emu2.psg.vol[0] < 15:
            hz = round(emu2.psg.tone_hz(0))
            if not notes or notes[-1] != hz:
                notes.append(hz)
    emu2.set_pads()
    chk.ok(len(notes) >= 2 and notes[-1] > notes[0],
           "the race starts with a rising two note sting %s" % notes)
    emu3 = boot(rom)
    start_race(emu3)
    blips = 0
    for f in range(1500):
        emu3.set_pads(p1=steer(emu3.ram(R_PX), emu3.ram(R_PY)))
        emu3.run_frame()
        if emu3.ram(R_STATE) != RACE:
            break
    blip_hz = None
    win_notes = []
    for _ in range(220):
        emu3.run_frame()
        if emu3.psg.vol[1] < 15:
            blips += 1
            blip_hz = round(emu3.psg.tone_hz(1))
        if emu3.psg.vol[0] < 15:
            hz = round(emu3.psg.tone_hz(0))
            if not win_notes or win_notes[-1] != hz:
                win_notes.append(hz)
    chk.ok(blips > 20 and blip_hz and 1000 < blip_hz < 1400,
           "each letter blips on channel 1 (%d frames at %s Hz)" % (blips, blip_hz))
    chk.ok(len(win_notes) >= 4 and win_notes[-1] > win_notes[0],
           "winning plays a rising tune %s" % win_notes)
    frames[0].save(os.path.join(args.out, "gameplay.gif"), save_all=True,
                   append_images=frames[1:], duration=50, loop=0, optimize=True)

    # a frame from the middle of the race for the still
    best = frames[len(frames) // 2]
    for img in frames:
        p = img.load()
        if p[140, 158][0] > 200 and p[100, 158][0] > 200 and p[128, 150][0] > 200:
            best = img
    best.save(os.path.join(args.out, "gameplay.png"))

    print("back to the title")
    hold(emu, 4, p1=P1_B1)
    hold(emu, 4)
    chk.ok(emu.ram(R_STATE) == TITLE, "button 1 returns to the title screen")

    print("Susie wins if you sit still")
    start_race(emu)
    for f in range(2400):
        emu.set_pads()
        emu.run_frame()
        if emu.ram(R_STATE) != RACE:
            break
    chk.ok(emu.ram(R_RLAPS) == 3, "Susie gets her three laps (%d frames)" % f)
    chk.ok(emu.ram(R_STATE) == LOST, "and the race is lost")
    chk.ok(text(emu, 12, 9, 10) == "SUSIE WINS", "the screen says SUSIE WINS")
    hold(emu, 2, p1=P1_B1)                           # skip the typing
    hold(emu, 2)
    chk.ok(text(emu, DLG_TEXT[0], DLG_TEXT[1], len(DLG_LOSE1)) == DLG_LOSE1,
           "she says %r" % DLG_LOSE1)
    chk.ok(text(emu, DLG_TEXT[0], DLG_TEXT[2], len(DLG_LOSE2)) == DLG_LOSE2,
           "then %r" % DLG_LOSE2)
    chk.ok(text(emu, DLG_TEXT[0], DLG_TEXT[3], len(DLG_LOSE3)) == DLG_LOSE3,
           "then %r" % DLG_LOSE3)
    chk.ok(emu.vdp.vram[PORTRAIT_SAT + 2] == PORTRAIT_BASE + 20,
           "the losing portrait is a second expression (pattern %d)"
           % emu.vdp.vram[PORTRAIT_SAT + 2])
    emu.screenshot().save(os.path.join(args.out, "lose.png"))

    chk.ok(not emu.errors, "no stray writes to the cartridge ROM")
    chk.ok(not emu.unknown_ports, "only known I/O ports are touched")

    failed = chk.failed()
    print("\n%d checks, %d failed" % (len(chk.items), len(failed)))
    for f in failed:
        print("  -", f)
    print("screenshots in", os.path.normpath(args.out))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
