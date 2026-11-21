#!/usr/bin/env python3
"""Checks deltarune.sg against the real Gearsystem core, not just our emulator.

    python3 tools/crosscheck.py /path/to/gsrun      # build gsrun first, see README

The same pad script is fed to `tools/sg1000.py` and to gsrun, which wraps the
Gearsystem SG-1000 core (the one Manic Emu and most RetroArch users run).
Afterwards the framebuffer and all 16 KB of VRAM are compared byte for byte,
and the console HOLD button is pressed to prove that the pause NMI arrives on
real hardware timing.  Exit status is non zero if anything differs.

`gsrun <rom> <out.ppm> [frames] [script] [vram.bin]`, the script being one
character per frame:  n nothing, u/d/l/r the directions, b button 1,
q button 2, p console HOLD (sends an NMI), and the upper case letters
release the button again.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from sg1000 import (SG1000, load_rom, P1_UP, P1_DOWN, P1_LEFT, P1_RIGHT,
                    P1_B1, P1_B2)

ROM = os.path.join(HERE, "..", "deltarune.sg")
KEYS = {"n": 0, "u": P1_UP, "d": P1_DOWN, "l": P1_LEFT, "r": P1_RIGHT,
        "b": P1_B1, "q": P1_B2}

R_STATE, R_PX, R_PY, R_PAUSED = 0, 7, 8, 3
KNIGHT_BASE = 72
SAT = 0x1B00
CH = {P1_UP: "u", P1_DOWN: "d", P1_LEFT: "l", P1_RIGHT: "r"}


def pads(script):
    """The same pad state per frame that gsrun builds: a letter presses and
    stays pressed until an "n" lets go of everything."""
    out, p1 = [], 0
    for ch in script:
        if ch == "n":
            p1 = 0
        else:
            p1 |= KEYS.get(ch, 0)
        out.append(p1)
    return out


def secret_script():
    """Button 1 + button 2, then stand still.  The knight's laps depend only on
    the frame count, so he wins at the same frame on every core, and from then
    on everything (his line, the swoon) is driven by frame counters - which
    makes the secret mode safe to compare pixel for pixel too."""
    script = "n" * 45 + "q" + "b" + "n" * 6          # hold 2, press 1: the secret
    emu = SG1000(load_rom(ROM))
    for p1 in pads(script):
        emu.set_pads(p1=p1)
        emu.run_frame()
    for _ in range(2000):                            # he wins, and starts talking
        if emu.ram(R_STATE) == 4:
            break
        script += "n"
        emu.set_pads()
        emu.run_frame()
    else:
        raise SystemExit("the secret race never reached his losing screen")
    for _ in range(100):                             # the line has typed itself
        script += "n"
        emu.set_pads()
        emu.run_frame()
    line = script
    for _ in range(1200):                            # the swoon, car split open
        if emu.ram(35) == 2:
            break
        script += "n"
        emu.set_pads()
        emu.run_frame()
    else:
        raise SystemExit("the swoon never got going")
    return line, script + "n" * 4


def lose_script():
    """Wall to wall: every leg runs until a wall stops the square, so one
    frame of pad timing cannot change where the car ends up.  Susie's laps
    depend only on the frame count, so she wins at the same frame on every
    core - which makes the lose screen (portrait, box and all) safe to
    compare pixel for pixel.  The frames after that let the text type out.
    """
    leg = ("u" * 70 + "n" + "l" * 140 + "n" + "u" * 300 + "n" + "r" * 460
           + "n" + "d" * 300 + "n" + "l" * 460)
    head = "n" * 45 + "b" + "n" * 6
    return (head + leg * 3)[:1950] + "n" * 300


def run_ours(script):
    emu = SG1000(load_rom(ROM))
    for p1 in pads(script):
        emu.set_pads(p1=p1)
        emu.run_frame()
    return emu


def run_gs(gem, script, tag):
    ppm = "/tmp/xcheck-%s.ppm" % tag
    vram = "/tmp/xcheck-%s.bin" % tag
    subprocess.run([gem, ROM, ppm, str(len(script)), script, vram],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return open(ppm, "rb").read().split(b"\n", 3)[3], open(vram, "rb").read()


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    gem = sys.argv[1]
    fails = []

    total = [0]

    def check(cond, text):
        total[0] += 1
        print(("  ok   " if cond else "  FAIL ") + text)
        if not cond:
            fails.append(text)

    def n_checks():
        return total[0]

    # ---- the same pictures and the same VRAM, frame for frame
    print("the real core draws what our emulator draws")
    # (a letter keeps the previous direction pressed in gsrun, so legs are
    #  separated by an "n" frame that lets go of everything)
    script = "n" * 40 + "b" * 3 + "n" * 5 + "u" * 40 + "n" + "l" * 40
    emu = run_ours(script)
    bmp, vram = run_gs(gem, script, "drive")
    ours = emu.screenshot().tobytes()
    check(ours == bmp, "every pixel of the frame is identical (%d bytes)" % len(ours))
    check(bytes(emu.vdp.vram) == vram, "all 16 KB of VRAM are identical")
    sprite = list(vram[SAT:SAT + 4])
    check(sprite == [emu.ram(R_PY) - 1, emu.ram(R_PX), 0, 0x0F],
          "the car's sprite is where the game put it %s" % sprite)
    check(emu.ram(R_STATE) == 1, "a race is running (%d)" % emu.ram(R_STATE))

    # ---- HOLD really is an NMI to $0066 on that core
    print("pause on the real core")
    base = "n" * 40 + "b" * 3 + "n" * 5 + "l" * 10
    free = list(run_gs(gem, base + "l" * 10, "free")[1][SAT:SAT + 4])
    hold = list(run_gs(gem, base + "p" * 10 + "l" * 10, "hold")[1][SAT:SAT + 4])
    but2 = list(run_gs(gem, base + "q" * 10 + "l" * 10, "but2")[1][SAT:SAT + 4])
    check(free[1] == 60, "without a pause the car drives on (x=%d)" % free[1])
    check(hold == free[:1] + [100, 0, 0x0F],
          "HOLD freezes it mid-straight (x=%d)" % hold[1])
    check(but2 == free[:1] + [100, 0, 0x0F],
          "joypad button 2 freezes it as well (x=%d)" % but2[1])

    # ---- the end screen, portrait and all, on the real core
    print("the dialogue box on the real core")
    script = lose_script()
    emu = run_ours(script)
    bmp, vram = run_gs(gem, script, "lose")
    check(emu.ram(0) == 3, "the script loses the race (%d frames)" % len(script))
    check(emu.screenshot().tobytes() == bmp,
          "the lose screen is identical pixel for pixel")
    check(bytes(emu.vdp.vram) == vram, "and so is VRAM, portrait patterns included")
    own = list(vram[SAT:SAT + 8])
    check(own[0:4] == [143, 24, 52, 0x0D] and own[6] == 53,
          "Susie's portrait is on the left of the box %s" % own)
    lines = ["".join(chr(32 + vram[0x1800 + row * 32 + 8 + i] - 13) for i in range(n))
             for row, n in ((18, 21), (20, 15), (22, 22))]
    check(lines == ["SUSIE: MAN, IT'S LIKE", "YOU'RE NOT EVEN", "LOOKING AT THE SCREEN."],
          "and her three lines are typed out there %s" % lines)

    # ---- the secret mode: the knight's car, his screen and the swoon
    print("the secret mode on the real core")
    # his car on its own: outline pattern, grey ghosts, four sprites on a line
    drive = "n" * 45 + "q" + "b" + "n" * 2 + "l" * 12 + "n" * 3
    emu = run_ours(drive)
    bmp, vram = run_gs(gem, drive, "knight-drive")
    check(emu.ram(R_STATE) == 1, "and the race is on")
    check(emu.screenshot().tobytes() == bmp,
          "his outline car and its grey afterimages are identical pixel for pixel")
    check(bytes(emu.vdp.vram) == vram, "and so is VRAM")
    sprite = list(vram[SAT + 4:SAT + 8])
    check(sprite[2] == 1 and sprite[3] == 0x0F,
          "the knight is a hollow white square %s" % sprite)
    ghosts = [list(vram[SAT + i:SAT + i + 4]) for i in (8, 12)]
    check(all(g[3] == 0x0E and sprite[1] < g[1] <= sprite[1] + 8 for g in ghosts),
          "and his ghosts trail behind him %s" % [g[1] for g in ghosts])

    line, swoon = secret_script()
    emu = run_ours(line)
    bmp, vram = run_gs(gem, line, "knight")
    check(emu.ram(R_STATE) == 4, "1+2 starts the secret race and the knight wins it")
    check(emu.screenshot().tobytes() == bmp,
          "his winning screen is identical pixel for pixel")
    check(bytes(emu.vdp.vram) == vram, "and so is VRAM")
    own = list(vram[SAT:SAT + 4])
    check(own[2] == KNIGHT_BASE and own[3] == 0x0F,
          "with his smug visor on the left of the box (pattern %d)" % own[2])

    emu = run_ours(swoon)
    bmp, vram = run_gs(gem, swoon, "swoon")
    check(emu.ram(R_STATE) == 5, "then the swoon")
    check(emu.screenshot().tobytes() == bmp, "the swoon is identical pixel for pixel")
    check(bytes(emu.vdp.vram) == vram, "and so is VRAM, slash and all")
    check(emu.vdp.regs[1] & 1 and vram[0x2000 + 26] == 0x81,
          "doubled sprites, and SWOON in the red colour group")
    half = list(vram[SAT:SAT + 8])
    check(half[1] < 120 and half[5] > 128,
          "the car is in two pieces, sliding apart %s" % half)

    print("\n%d checks, %d failed" % (n_checks(), len(fails)))
    for f in fails:
        print("  -", f)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
