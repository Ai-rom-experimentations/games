# homebrew

AI assisted, non-ported homebrew titles.

One folder per console, one folder per game inside it:

```
<console>/<title>/          e.g. sg1000/pong/
```

| console | folder | titles |
|---|---|---|
| **SG-1000** | [`sg1000/`](sg1000) | **Pong** - Atari's 1972 arcade game in Z80 assembly, 16 KB cartridge, one or two players ([folder](sg1000/pong), [screenshots](sg1000/pong/screenshots), [README](sg1000/pong/README.md))<br>**DELTARUNE Chapter 3 Hidden Racing Minigame** - the racing game hidden behind Kris' back in Deltarune Chapter 3, three laps against Susie, with sounds and a dialogue box with her portrait - and a secret opponent behind button 1+2 ([folder](sg1000/deltarune-race), [screenshots](sg1000/deltarune-race/screenshots), [README](sg1000/deltarune-race/README.md)) |
| **Master System** | [`sms/`](sms) | - |
| **MSX** | [`msx/`](msx) | **Aliens!** - a Galaga clone: a swaying formation of eighteen aliens over a scrolling starfield, divers, return fire, a high score and seven PSG sounds - and a WebAssembly MSX in the folder, so it plays in a browser with no plugins ([folder](msx/aliens), [browser build](msx/aliens/web), [screenshots](msx/aliens/screenshots), [README](msx/aliens/README.md))<br>**Chrome Dino** - the offline dinosaur from `chrome://dino`, cut out of Chromium's own sprite sheet: cactuses, pterodactyls, a day/dusk/night palette, the same three sounds, four modes and a high score ([folder](msx/dino), [screenshots](msx/dino/screenshots), [browser build](msx/dino/web), [README](msx/dino/README.md)) |
| **NES** | [`nes/`](nes) | - |

Every game folder is self contained: the sources and artwork, a `Makefile`
that assembles the ROM (`make`) and runs the headless test (`make check`),
the built image, and a README explaining the hardware details.  Where a game
also runs in a browser, the page lives in a `web/` folder inside it and
`make serve` is all it takes to open it.

The repository is called `sg1000` for historical reasons - it started with
the SG-1000 title above and now holds all of them.
