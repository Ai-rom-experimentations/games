# The vendored emulator bits

`web/` needs an MSX to run the cartridge in, and it carries one: a copy of the
**blueMSX libretro core** compiled to WebAssembly, plus the open-source
**C-BIOS** MSX1 machine it boots with. Nothing here is fetched from the
network at run time, so the page works offline (and from any static server).

| file | what it is |
|---|---|
| `bluemsx_libretro.wasm` | the blueMSX libretro core, built by [romdev](https://github.com/monteslu/romdev) (`packages/romdev-core-bluemsx@0.9.2`, MIT/BSD-3-Clause package metadata) |
| `bluemsx_libretro.js` | its Emscripten glue; `emulator.js` flips its `ENVIRONMENT_IS_NODE` flag in memory before importing it, because it was built for Node |
| `bios/Machines/MSX - C-BIOS/` | the C-BIOS MSX1 BIOS (main + logo ROMs), `config.ini` and the C-BIOS licence text |

## Licences, because they matter

* **blueMSX** is permissively licensed (a zlib-style licence for the code the
  blueMSX team wrote; see `license.txt` in
  [libretro/blueMSX-libretro](https://github.com/libretro/blueMSX-libretro)).
  Some upstream files come from other projects under their own terms,
  including GPL sound-chip code from openMSX and fMSX-SDL.
* **C-BIOS** is BSD (2-clause); its copyright and licence text ship beside the
  ROMs as `cbios.txt`, which its binary redistribution clause requires. Source
  and docs: <https://cbios.sourceforge.net>.

The cartridge (`../aliens.rom`) is this repository's own work.

## Rebuilding the core

Not needed to run the page, but for the record: `romdev-core-bluemsx` is built
from `libretro/blueMSX-libretro` by
`packages/romdevtools/scripts/build-bluemsx.sh` in the romdev repository, which
also applies two small patches. To move to a newer build, unpack
`npm pack romdev-core-bluemsx` and copy `wasm/bluemsx_libretro.{js,wasm}` and
`bios/Machines/` over the copies here, dropping `bios/Databases/` (2.4 MB of
game-database XML that a single-cartridge page never touches).
