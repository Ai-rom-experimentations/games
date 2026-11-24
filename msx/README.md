# MSX

AI assisted, non-ported homebrew titles for the MSX
(Z80 + TMS9918A + AY-3-8910).

| title | folder | what it is |
|---|---|---|
| **Aliens!** | [`aliens/`](aliens) | a Galaga clone: a swaying 6x3 formation of eighteen aliens over a scrolling starfield, divers that peel off and weave down the screen, aliens that shoot back, three lives and a high score - Z80 assembly, 16 KB cartridge, seven AY-3-8910 sounds ([screenshots](aliens/screenshots), [README](aliens/README.md)) - and it runs in a browser: an MSX1 in WebAssembly, in [`aliens/web/`](aliens/web) |
| **Chrome Dino** | [`dino/`](dino) | the Chrome offline dinosaur, cut out of Chromium's own sprite sheet: cactuses and pterodactyls, a day/dusk/night palette swapped by rewriting the VDP colour table, the page's three sounds, four modes and a high score - Z80 assembly, 16 KB cartridge, 192 patterns and 36 sprite patterns ([screenshots](dino/screenshots), [README](dino/README.md)) - it also runs in a browser, in [`dino/web/`](dino/web), though that core paints Graphics II colours the Graphics I way |

Each title gets its own `<title>/` folder here, laid out like
[`../sg1000/pong/`](../sg1000/pong).
