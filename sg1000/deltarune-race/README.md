# DELTARUNE Chapter 3 Hidden Racing Minigame

The racing game that is hidden inside **Deltarune Chapter 3**, rebuilt as a
real, playable SG-1000 cartridge image (Z80 + TMS9918A + SN76489).  You are a
white square on a black track with a white outline, there is a white outline
square in the middle, and you race Susie around it three times.

![title screen](screenshots/title.png)

![racing Susie](screenshots/gameplay.png)

## Why it is called that

In Chapter 3, in the Green Room of the TV studio, the left television has a
racing game on it and Susie challenges Kris to a race.  The camera is placed
behind Kris, so you never see the screen - you only see their hands working
the controller.  What makes it special is that the game **really is running**:
The Cutting Room Floor documents that it is a playable simulation behind the
camera, revealed by a script variable called `_debug_visible`, and it can be
played without any debug mode at all.

The minigame itself:

* a box on a square track which you steer with the movement keys; the whole
  game is *driving the box around the square*, clockwise,
* Kris' hands keep bobbing while you are making progress and stop dead with a
  bump sound effect when you hit a wall,
* you get **three attempts** - the attempt count lives in save flag `1034`,
  the win in flag `1035`, and once you have burned all three Susie refuses to
  play again,
* if you win, Ralsei congratulates Kris and **Susie sulks**.

The route the community settled on is *hold left until the bump, then up,
then right, then down* - one clockwise lap of the square that starts on the
bottom edge, right of the finish line.  This cartridge uses exactly that
layout, and shows you the scoreboard the real one hides behind Kris' back.

Sources: [TCRF - Deltarune Chapter 3, "Racing Game Visuals"](https://tcrf.net/Deltarune/Chapter_3),
[Deltarune Wiki - Green Room](https://deltarune.wiki/w/Green_Room),
[Steam guide with the winning input sequence](https://steamcommunity.com/sharedfiles/filedetails/?id=3562945951).

## What it does

* A 256x192 track: a 2 pixel white wall around the outside and a 2 pixel
  white square in the middle, everything else black, with a two column
  **chequered finish line** running from the bottom of the middle square to
  the bottom wall.
* Your square starts on the **right of the finish line** in the bottom
  straight and drives clockwise.  It moves 2 pixels a frame in whichever of
  the four directions you hold, and walls (outer and middle) stop it dead
  with a bump - the same bump the real minigame plays when Kris' hands stop.
* **Susie** races you.  She is the magenta square, takes the outside lane at
  half your speed, drives the same clockwise lap and counts her laps at the
  same line.  Beat her over three laps and she sulks: the screen shows
  `YOU WIN`.  If she gets her three laps first, Kris loses and the screen
  shows `SUSIE WINS`.
* A lap only counts when it *is* a lap: the square has to pass a checkpoint
  in each of the other three straights before the finish line scores, so you
  cannot win by wiggling over the line.
* The middle square is the scoreboard - `LAP 1/3` and `SUSIE 1/3` are drawn
  inside it.  Same view as the hidden screen in the real game, just visible.
* Sounds on the SN76489, close to the ones in the real Green Room scene: a
  low **noise thud** when a wall stops the square (that is the sound Kris'
  hands stop to), a short blip per lap, and a little rising / falling tune for
  the win and the loss.
* Susie **talks to you** on the end screens.  A dialogue box is drawn along
  the bottom of the screen over the track, her **portrait** sits on the left
  of it, and her line from the game types itself out with a blip per letter.
  She has two faces: sulking when Kris wins, gloating when she wins.
* The console's HOLD button - labelled **HOLD** on the SG-1000, PAUSE on the
  SG-1000 II - freezes the game.  Joypad 1 **button 2** taps the same switch
  for emulators whose overlay does not give you the console button.

![you win](screenshots/win.png)

![Susie wins](screenshots/lose.png)

## Susie has something to say

Both end screens end with a line lifted from the scene itself - the Green
Room, after the race on the left TV:

| | |
|---|---|
| Kris wins | `SUSIE: HOW THE HECK...` / `ALRIGHT, WE'RE DONE.` |
| Susie wins | `SUSIE: MAN, IT'S LIKE` / `YOU'RE NOT EVEN` / `LOOKING AT THE SCREEN.` |

(From the Chapter 3 script dump of the Green Room, in the "Left TV" section -
the same exchange the wiki paraphrases as Susie giving up after three tries.
The SG-1000 font has no lower case, so the lines are in capitals.)

The box is 30 cells wide and 7 rows tall; it replaces the bottom straight and
the bottom wall, so the track map is redrawn from `dialog_map` instead of
`track_map`.  The portrait is 32x40 pixels - a 4x5 grid of character cells -
and it is drawn as **sprites**, not tiles, so the black of the box shows
through around her silhouette.  A sprite costs four bytes and a tile costs
two, but the palette makes up for it: an 8x8 cell can only have one colour, so
the face is one magenta shape (`$0D`) with the features cut out as black
holes, plus a single white cell (`$0F`) for the eye.  The two expressions are
two sets of twenty sprite patterns, so the switch is six bytes of sprite
attribute table.

The text is a typewriter: one letter every third frame, a 1.2 kHz blip on
channel 1 for each of them, and **button 1** finishes the line at once - press
it again to go back to the title.

## Controls

| | |
|---|---|
| **Race** | joypad 1 **up**/**down**/**left**/**right** drives the square |
| **Title** | **button 1** starts a race |
| **End screen** | **button 1** finishes Susie's line, then goes back to the title |
| **HOLD** | the console button (PAUSE on the SG-1000 II) freezes / unfreezes |
| **Pause** | joypad 1 **button 2** taps the same switch |

The HOLD button is an NMI on the Z80 (it vectors through `$0066`), which is
why the game can freeze at any moment, even mid-frame.  The pause toggle is
armed in both the NMI handler and on the button 2 edge in software, and both
lead to the same latch at `$C003`.

## Building

You need [sjasmplus](https://github.com/z00m128/sjasmplus):

```sh
git clone https://github.com/z00m128/sjasmplus
cd sjasmplus && make && sudo make install   # or just keep the binary around

cd sg1000/deltarune-race    # from the repository root
make                        # -> deltarune.sg  (16 KB)
make SJASMPLUS=/path/to/sjasmplus
```

`make` also regenerates `gfx.asm` if you touch `tools/gen_gfx.py`.

## Running

Any SG-1000 capable emulator will do, for example:

* **Manic Emu** (iOS, Gearsystem core) - pick the SG-1000 system for the ROM
* **Emulicious** (Windows/macOS/Linux, has a great SG-1000 mode)
* **MEKA** (Windows)
* **Genesis Plus GX** (RetroArch core `genesis_plus_gx`) - load
  `deltarune.sg` and it switches to SG-1000 hardware
* **SMS Plus GX**, **BlueMSX**, **MAME** (`mame sg1000 -cart deltarune.sg`)

On real hardware: burn `deltarune.sg` to a 16 KB (or larger, e.g. 27C256)
EPROM cartridge; the image starts at `$0000` and needs no header.  The D-pad
is joypad 1, whose directions are on port `$DC` bits 0-3 (active low).

## How it is put together

| area | | |
|---|---|---|
| VDP mode | Graphics I (R0 `$00`, R1 `$A0` while the tables are loaded, then R1 `$E0`) |
| pattern table | `$0000` (R4 `$00`) - 77 tiles: blank, wall pieces, chequers, 5x7 text font |
| colour table | `$2000` (R3 `$80`) - 32 bytes of `$F1`, every tile white on black |
| name table | `$1800` (R2 `$06`) - 32x24 cells, the whole track is redrawn per screen |
| sprite attributes | `$1B00` (R5 `$36`) - 2 sprites while racing, 20 on an end screen |
| sprite patterns | `$3800` (R6 `$07`) - one solid 8x8 block for the cars, then the 40 portrait patterns |
| RAM | `$C000-$C3EF` (the SG-1000 only has 1 KB; the stack lives at `$C3F0`) |
| frame sync | the VDP status read flag (bit 7) is polled; IRQs stay masked |
| sound | SN76489 - channel 0 tunes and the lap blip, channel 1 the letter blips, channel 3 the noise thud |

The game logic is one pass per video frame (60 Hz):

```
wait for vblank -> read pads -> service pause -> move the square (walls!)
                -> lap checkpoints -> move Susie -> update the sprites
                -> tick the sound (and the typewriter, on an end screen)
```

The sound is a frame counter per channel rather than anything clever: each
cue writes a divider and a length, and a tick routine counts it down and
mutes the channel.  The tunes are streams of `frames, divider low, divider
high`, three bytes a note, ending on a zero frame count.  The divider is
`3579545 / (32 * Hz)`, e.g. `143` for G5.

Both cars are 8x8 squares built from a single all-`$FF` sprite pattern; the
player's sprite attribute is `$0F` (white), Susie's is `$0D` (light magenta).
The tile map is generated, so the walls, the middle square and the chequered
line are just tiles 1-12 placed by `tools/gen_gfx.py`:

| | |
|---|---|
| outer wall | cells 1..30 across, 1..22 down (pixels x 8..247, y 8..183) |
| middle square | cells 8..23 across, 7..16 down (pixels x 64..191, y 56..135) |
| finish line | cells 15 and 16, from row 17 to the bottom wall (x 120..135) |
| lane width | 46 px above and below the middle square, 54 px to its left and right |
| car start | (140, 155) - right of the line, middle of the bottom straight |
| Susie start | (100, 155) - past the line, so she cannot count a lap at once |

Collision is a plain rectangle test against `x 57..191` / `y 49..135` (the
middle square grown by the car's 7 pixel extent) plus the outer limits
`x 10..238`, `y 10..174`.  Movement is 2 px/frame, so a corner bump can
never tunnel: the step is shorter than the wall.

### Files

```
deltarune.asm       the game (hardware init, screens, lap logic, sound)
gfx.asm             generated tile patterns, the track map and the title text
deltarune.sg        built cartridge image (16 KB)
tools/gen_gfx.py    the artwork: wall/chequer tiles, 5x7 font, track layout
tools/sg1000.py     tiny SG-1000 emulator (Z80 + TMS9918A + SN76489)
tools/capture.py    runs the ROM headless: 61 checks + screenshots/gif
tools/crosscheck.py the same ROM on the real Gearsystem core, byte for byte
tools/gsrun.cpp     cross-check harness: wraps the Gearsystem core
screenshots/        what the emulator captured
```

## Development notes

The artwork is generated, so the tiles and the layout can be edited without
touching assembly:

```sh
python3 tools/gen_gfx.py --preview    # also dumps PNG previews to /tmp
```

`tools/capture.py` boots the ROM in the bundled emulator, plays real laps on
autopilot and asserts what happened - 61 checks, including the exact title
text in the name table, the wall and middle square tiles, the chequers, the
sprite positions and colours, three laps to win, Susie winning if you idle,
the lap checkpoints refusing to score a wiggle over the line, both pause
buttons, and the whole of the dialogue box: its walls over the bottom
straight, the text it types, the force-finish on button 1, the twenty sprite
cells of the portrait, the one white eye cell, and that the winning and
losing portraits are different pictures:

```
$ make check
...
61 checks, 0 failed
screenshots in screenshots
```

The sound is checked in Hz: the wall thud has to be white noise on channel 3
and be over in a few frames, the letter blips have to land on channel 1
around 1.2 kHz, and the win tune has to climb note by note - `<Hz>` values
taken straight out of the emulated PSG registers, not from a log.

### Cross-checking against Gearsystem

Our own emulator is convenient but it is not the thing the ROM has to run on.
`tools/gsrun.cpp` wraps the **real Gearsystem core** (the one Manic Emu and
most RetroArch users run) in a headless runner and dumps both a PPM frame and
the 16 KB of VRAM:

```sh
GS=../gearsystem   # a Gearsystem checkout
g++ -std=c++14 -O2 -w -I$GS/src -I$GS/platforms/shared/dependencies/miniz \
    $GS/src/*.cpp $GS/src/audio/*.cpp $GS/src/audio/emu2413/emu2413.c \
    $GS/platforms/shared/dependencies/miniz/miniz.c tools/gsrun.cpp -o gsrun

python3 tools/crosscheck.py ./gsrun     # or: make crosscheck EMU=./gsrun
```

`crosscheck.py` feeds the identical pad script to both emulators and compares
the frame and **all of VRAM** byte for byte, then presses console HOLD
(`Key_Start` on the harness, which is the NMI button) and button 2 to prove
that the pause works on the real core.  It is the kind of check that caught
the swapped VDP colour-table register while Pong was being written, so it is
worth running before believing anything:

```
the real core draws what our emulator draws
  ok   every pixel of the frame is identical (147456 bytes)
  ok   all 16 KB of VRAM are identical
  ok   the car's sprite is where the game put it [136, 60, 0, 15]
  ok   a race is running (1)
pause on the real core
  ok   without a pause the car drives on (x=60)
  ok   HOLD freezes it mid-straight (x=100)
  ok   joypad button 2 freezes it as well (x=100)
the dialogue box on the real core
  ok   the script loses the race (2250 frames)
  ok   the lose screen is identical pixel for pixel
  ok   and so is VRAM, portrait patterns included
  ok   Susie's portrait is on the left of the box [143, 24, 52, 13, ...]
  ok   and her three lines are typed out there [...]
```

The end screen check is driven wall to wall - every leg of the script runs
until the square is stopped by a wall - so it does not depend on a frame of
pad-injection timing, and Susie's laps depend only on the frame count.  The
portrait has to come out of the real core's sprite renderer byte for byte the
same as out of ours, which is the whole point of the exercise.

### What is different from the real minigame

The real one runs behind Kris' back on a TV screen you never see, and its
only feedback is the bump and whether the hands keep moving.  This version
shows the track, adds a visible scoreboard, and gives you an opponent in the
outside lane so that "three attempts" becomes "three laps against Susie":
beating her is the win, losing is the sulk.  Susie drives the outside lane
on rails; she is not a simulation of the real scripted race, which - like the
hidden original - you win by simply completing the laps.
