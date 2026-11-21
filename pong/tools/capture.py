#!/usr/bin/env python3
"""Runs pong.sg headlessly: sanity checks the game and writes the screenshots.

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

from sg1000 import (SG1000, load_rom, P1_UP, P1_DOWN, P1_B1,
                    P2_UP, P2_DOWN)

# RAM map (keep in sync with pong.asm)
RAM = 0xC000
R_STATE, R_MODE, R_SCORE1, R_SCORE2 = 0, 1, 3, 4
R_P1Y, R_P2Y, R_BX, R_BY, R_BDX, R_BDY, R_SERVE = 6, 7, 8, 9, 10, 11, 12

TITLE, PLAY, OVER = 0, 1, 2
signed = lambda v: v - 256 if v > 127 else v


def hold(emu, frames, p1=0, p2=0):
    emu.set_pads(p1=p1, p2=p2)
    for _ in range(frames):
        emu.run_frame()


def follow(paddle_y, target_y, up_bit, down_bit, dead=2):
    centre = paddle_y + 12
    target = target_y + 2
    if centre < target - dead:
        return down_bit
    if centre > target + dead:
        return up_bit
    return 0


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


def select(emu, players):
    """Pick '1 PLAYER' or '2 PLAYERS' on the title screen and start."""
    if players == 2:
        hold(emu, 4, p1=P1_DOWN)
        hold(emu, 4)
    hold(emu, 4, p1=P1_B1)
    hold(emu, 8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rom", default=os.path.join(HERE, "..", "pong.sg"))
    ap.add_argument("--out", default=os.path.join(HERE, "..", "screenshots"))
    args = ap.parse_args()

    rom = load_rom(args.rom)
    os.makedirs(args.out, exist_ok=True)
    chk = Checks()

    print("boot")
    emu = boot(rom)
    chk.ok(emu.ram(R_STATE) == TITLE, "boots to the title screen")
    emu.screenshot().save(os.path.join(args.out, "title.png"))

    print("two player match")
    select(emu, 2)
    chk.ok(emu.ram(R_STATE) == PLAY, "button 1 starts a match")
    chk.ok(emu.ram(R_MODE) == 2, "menu selects two players")
    chk.ok(emu.ram(R_SCORE1) == 0 and emu.ram(R_SCORE2) == 0, "scores start at 0")

    # ---- a rally with both paddles on autopilot, recorded for the GIF
    frames = []
    hits = {}
    last_freq = None
    bounces = 0
    last_bdx = emu.ram(R_BDX)
    max_speed = 0
    points = 0
    last_score = (emu.ram(R_SCORE1), emu.ram(R_SCORE2))
    dozing = True                                  # player 1 misses a ball
    for f in range(480):
        target = emu.ram(R_BY)
        if dozing and f > 100 and signed(emu.ram(R_BDX)) < 0 and emu.ram(R_BX) < 150:
            target += 70
        p1 = follow(emu.ram(R_P1Y), target, P1_UP, P1_DOWN)
        p2 = follow(emu.ram(R_P2Y), emu.ram(R_BY), P2_UP, P2_DOWN)
        emu.set_pads(p1=p1, p2=p2)
        emu.run_frame()

        if emu.ram(R_BDX) != last_bdx:
            bounces += 1
            last_bdx = emu.ram(R_BDX)
        max_speed = max(max_speed, abs(signed(emu.ram(R_BDX))))
        score = (emu.ram(R_SCORE1), emu.ram(R_SCORE2))
        if score != last_score:
            points += 1
            last_score = score
            dozing = False
        if emu.psg.vol[0] < 15:
            freq = int(round(emu.psg.tone_hz(0)))
            if freq != last_freq:
                hits[freq] = hits.get(freq, 0) + 1
                last_freq = freq
        else:
            last_freq = None
        if f % 2 == 0:
            frames.append(emu.screenshot())

    chk.ok(bounces >= 5, "paddles return the ball (%d direction changes)" % bounces)
    chk.ok(max_speed == 4, "ball speeds up to the cap (%d px/frame)" % max_speed)
    chk.ok(hits.get(491), "paddle hit blip at %s Hz" % 491)
    chk.ok(hits.get(226), "wall bounce blip at %s Hz" % 226)
    chk.ok(points >= 1, "points are scored and served again (%d)" % points)

    # ---- score digits really are in the name table
    def digit_tiles(col, row=1):
        base = 0x1800 + row * 32 + col
        return [emu.vdp.vram[base + i] + 0 for i in range(2)]

    score = emu.ram(R_SCORE1)
    if score:
        tiles = digit_tiles(10)
        expect = [67 + (score % 10) * 6, 67 + (score % 10) * 6 + 1]
        chk.ok(tiles == expect, "left score digit tile %s is the right glyph" % tiles)

    # a good frame for the still
    best = None
    for i, img in enumerate(frames):
        px = img.load()
        if px[128, 96][0] == 0 and px[60, 96][0] == 255:
            best = img
    (best or frames[len(frames) // 2]).save(os.path.join(args.out, "gameplay.png"))
    frames[0].save(os.path.join(args.out, "gameplay.gif"), save_all=True,
                   append_images=frames[1:], duration=50, loop=0, optimize=True)

    # ---- game over: hand out eleven points to player 1
    for _ in range(11):
        emu.mem[RAM + R_BX] = 239
        emu.mem[RAM + R_BY] = 20
        emu.mem[RAM + R_BDX] = 3
        emu.mem[RAM + R_SERVE] = 0
        for _ in range(8):
            emu.set_pads()
            emu.run_frame()
    chk.ok(emu.ram(R_SCORE1) == 11, "eleven points end the match")
    chk.ok(emu.ram(R_STATE) == OVER, "game over screen is shown")
    emu.screenshot().save(os.path.join(args.out, "gameover.png"))

    print("back to the title")
    hold(emu, 4, p1=P1_B1)
    hold(emu, 6)
    chk.ok(emu.ram(R_STATE) == TITLE, "button 1 returns to the title screen")

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
