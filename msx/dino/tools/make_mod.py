#!/usr/bin/env python3
"""Writes tools/dino.mod: a small four channel ProTracker module written for
this port.  Two patterns, a bass line against a running melody in A minor,
slow enough to read on an MSX and fast enough to sound like a chase.

    python3 tools/make_mod.py

The module is the source of the music - tools/mod2msx.py turns it into the
PSG script the game plays, and fairlight, OpenMPT or MilkyTracker can open the
file to hear what it was meant to sound like.  Writing it here rather than
downloading a tune keeps the licence simple: it is this repository's own.
"""
import struct

MOD_PERIODS = [  # C-1 .. B-3, the ProTracker table
    856, 808, 762, 720, 678, 640, 604, 570, 538, 508, 480, 453,
    428, 404, 381, 360, 339, 320, 302, 285, 269, 254, 240, 226,
    214, 202, 190, 180, 170, 160, 151, 143, 135, 127, 120, 113,
    107, 101, 95, 90, 85, 80, 76, 71, 67, 64, 60, 57,
    54, 51, 48, 45, 43, 40, 38, 36, 34, 32, 30, 28,
]
NAMES = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6,
         "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}


def note(name):
    """'A3' -> the ProTracker note number (C-1 is 0), '---' -> None."""
    if name == "---":
        return None
    if name == "...":
        return "hold"
    return (int(name[-1]) - 1) * 12 + NAMES[name[:-1]]


# the melody: eight bars, eighth notes, A minor with the seventh flattened
MELODY = """
A3 A3 C4 E4 A4 E4 C4 E4  G3 G3 B3 D4 G4 D4 B3 D4
F3 F3 A3 C4 F4 C4 A3 C4  E3 E3 G#3 B3 E4 B3 G#3 B3
A3 A3 C4 E4 A4 E4 C4 E4  G3 G3 B3 D4 G4 D4 B3 D4
F3 F3 A3 C4 F4 C4 A3 C4  E3 E4 G#3 E4 B3 E4 G#3 B3
"""
BASS = """
A2 ... A2 ... A2 ... E2 ...  G2 ... G2 ... G2 ... D2 ...
F2 ... F2 ... F2 ... C2 ...  E2 ... E2 ... B2 ... E2 ...
A2 ... A2 ... A2 ... E2 ...  G2 ... G2 ... G2 ... D2 ...
F2 ... F2 ... F2 ... C2 ...  E2 ... B2 ... E2 ... G#2 ...
"""


def rows(text):
    out = []
    for tok in text.split():
        out.append(tok)
    return out


def pattern_cell(n):
    """A note, with the sample's volume left to the instrument."""
    if n is None:
        return 0, 0, 0
    if n == "hold":
        return 0, 0, 0
    return MOD_PERIODS[n], 1, 0


def sample_block(name, volume, length):
    b = name.encode()[:22].ljust(22, b"\0")
    b += struct.pack(">HBBHH", length // 2, 0, volume, 0, length // 2)
    return b


def main():
    mel = rows(MELODY)
    bass = rows(BASS)
    assert len(mel) == 64 and len(bass) == 64, (len(mel), len(bass))

    out = b"chrome dino - run".ljust(20, b"\0")
    # four samples: a square lead, a square bass, a soft lead, silence
    out += sample_block("square lead", 48, 64)
    out += sample_block("square bass", 56, 64)
    out += sample_block("soft lead", 32, 64)
    for _ in range(28):
        out += sample_block("", 0, 2)
    out += bytes([2, 0])                 # two orders, restart at 0
    order = [0, 1] + [0] * 126
    out += bytes(order)
    out += b"M.K."

    for pat in range(2):
        for r in range(64):
            for ch in range(4):
                if ch == 0:
                    n = note(mel[r])
                elif ch == 1:
                    n = note(bass[r])
                else:
                    out += bytes([0, 0, 0, 0])
                    continue
                if n in (None, "hold"):
                    out += bytes([0, 0, 0, 0])
                    continue
                period, ins, _ = pattern_cell(n)
                out += bytes([(ins & 0xF0) | (period >> 8), period & 0xFF,
                              ((ins & 0x0F) << 4) | 0, 0])

    for s in range(2):
        for i in range(64):
            out += bytes([0x00 if i % 2 else 0x40])
    out += bytes(2 * (64 - 64))
    open("tools/dino.mod", "wb").write(out)
    print("wrote tools/dino.mod (%d bytes)" % len(out))


if __name__ == "__main__":
    main()
