/*
 * Headless check for the browser build.
 *
 * Runs the very same core the page uses, under Node, boots dino.rom on
 * C-BIOS, and proves three things: the core loaded the cartridge, it is
 * painting frames and making sound, and the game itself got as far as its
 * title screen and into a game when the joystick trigger is pressed.
 *
 *   node web/check.mjs            (from msx/dino, or anywhere)
 *
 * Writes screenshots/web-title.png and screenshots/web-play.png.
 */

import createCore from "./core/bluemsx_libretro.js";
import fs from "node:fs";
import path from "node:path";
import zlib from "node:zlib";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const GAME = path.join(HERE, "..");
const CORE_DIR = path.join(HERE, "core");
const MACHINE = "MSX - C-BIOS";
const SYSTEM_DIR = "/bios";
const ROM_PATH = "/cart/dino.rom";

const BIOS_FILES = [
  `Machines/${MACHINE}/config.ini`,
  `Machines/${MACHINE}/cbios_main_msx1.rom`,
  `Machines/${MACHINE}/cbios_logo_msx1.rom`,
  `Machines/${MACHINE}/cbios.txt`,
];

const checks = [];
const check = (cond, what) => checks.push([!!cond, what]);

/* ---------- tiny PNG writer (no dependencies) ---------- */

const crcTable = (() => {
  const table = new Int32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    table[n] = c;
  }
  return table;
})();

function crc32(buf) {
  let crc = 0xffffffff;
  for (let i = 0; i < buf.length; i++) crc = crcTable[(crc ^ buf[i]) & 0xff] ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}

function chunk(type, data) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length);
  const body = Buffer.concat([Buffer.from(type, "ascii"), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body));
  return Buffer.concat([len, body, crc]);
}

function writePng(file, width, height, rgb) {
  const stride = width * 3;
  const raw = Buffer.alloc((stride + 1) * height);
  for (let y = 0; y < height; y++) {
    rgb.copy(raw, y * (stride + 1) + 1, y * stride, (y + 1) * stride);
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8; ihdr[9] = 2;
  fs.writeFileSync(file, Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk("IHDR", ihdr),
    chunk("IDAT", zlib.deflateSync(raw, { level: 9 })),
    chunk("IEND", Buffer.alloc(0)),
  ]));
}

/* ---------- boot ---------- */

const mod = await createCore({
  locateFile: (name) => path.join(CORE_DIR, name),
  print: () => {},
  printErr: () => {},
});

for (const file of BIOS_FILES) {
  const dest = `${SYSTEM_DIR}/${file}`;
  let dir = "";
  for (const part of dest.split("/").filter(Boolean).slice(0, -1)) {
    dir += "/" + part;
    try { mod.FS.mkdir(dir); } catch (e) { /* exists */ }
  }
  mod.FS.writeFile(dest, fs.readFileSync(path.join(CORE_DIR, "bios", file)));
}
try { mod.FS.mkdir("/saves"); } catch (e) { /* exists */ }
const rom = fs.readFileSync(path.join(GAME, "dino.rom"));
mod.FS.mkdir("/cart");
mod.FS.writeFile(ROM_PATH, rom);

const strPtr = (s) => {
  const n = mod.lengthBytesUTF8(s) + 1;
  const p = mod._malloc(n);
  mod.stringToUTF8(s, p, n);
  return p;
};

let format = 0;
const vars = { bluemsx_msxtype: MACHINE };

mod._retro_set_environment(mod.addFunction((cmd, data) => {
  switch (cmd) {
    case 3: mod.HEAPU8[data] = 1; return true;
    case 9: mod.HEAPU32[data >> 2] = strPtr(SYSTEM_DIR); return true;
    case 31: mod.HEAPU32[data >> 2] = strPtr("/saves"); return true;
    case 10: format = mod.HEAPU32[data >> 2]; return true;
    case 15: {
      const key = mod.UTF8ToString(mod.HEAPU32[data >> 2]);
      if (vars[key] === undefined) return false;
      mod.HEAPU32[(data + 4) >> 2] = strPtr(vars[key]);
      return true;
    }
    case 16: return true;
    case 27: {
      mod.HEAPU32[data >> 2] = mod.addFunction(() => {}, "viii");
      return true;
    }
    case 39: mod.HEAPU32[data >> 2] = 0; return true;
    case 52: mod.HEAPU32[data >> 2] = 2; return true;
    case 65587: mod.HEAPU8[data] = 1; return true;
    default: return false;
  }
}, "iii"));
mod._retro_init();

let frame = { ptr: 0, width: 0, height: 0, pitch: 0 };
let videoFrames = 0;
mod._retro_set_video_refresh(mod.addFunction((data, w, h, pitch) => {
  videoFrames++;
  frame = { ptr: data, width: w, height: h, pitch };
}, "viiii"));
let audioFrames = 0;
mod._retro_set_audio_sample_batch(mod.addFunction((data, frames) => {
  audioFrames += frames;
  return frames;
}, "iii"));
mod._retro_set_audio_sample(mod.addFunction(() => {}, "vii"));
mod._retro_set_input_poll(mod.addFunction(() => {}, "v"));
let joy = 0;
mod._retro_set_input_state(mod.addFunction((port, device, index, id) => {
  if (port !== 0 || device !== 1) return 0;
  if (id === 256) return joy;                   // RETRO_DEVICE_ID_JOYPAD_MASK
  return id <= 15 ? (joy >> id) & 1 : 0;
}, "iiiii"));

const romPtr = mod._malloc(rom.length);
mod.HEAPU8.set(rom, romPtr);
const info = mod._malloc(16);
mod.HEAPU32[info >> 2] = strPtr(ROM_PATH);
mod.HEAPU32[(info + 4) >> 2] = romPtr;
mod.HEAPU32[(info + 8) >> 2] = rom.length;
mod.HEAPU32[(info + 12) >> 2] = 0;
check(mod._retro_load_game(info) === 1, "the core loads dino.rom on MSX - C-BIOS");

const av = mod._malloc(64);
mod._retro_get_system_av_info(av);
const view = new DataView(mod.HEAPU8.buffer);
const fps = view.getFloat64(av + 24, true);
check(mod.HEAPU32[av >> 2] === 272 && mod.HEAPU32[(av + 4) >> 2] === 240, "the core reports a 272x240 MSX1 screen");
check(fps > 50 && fps < 61, `the core runs at ${fps.toFixed(2)} Hz`);

/* ---------- helpers over the machine ---------- */

const RETRO_MEMORY_SYSTEM_RAM = 2;
const ramBase = mod._retro_get_memory_data(RETRO_MEMORY_SYSTEM_RAM) >> 0;
const ramSize = mod._retro_get_memory_size(RETRO_MEMORY_SYSTEM_RAM);
// the cartridge's RAM starts at $C000; the machine has 64 KB of it
const ram = (offset) => mod.HEAPU8[ramBase + 0xc000 + offset];

function run(frames) {
  for (let i = 0; i < frames; i++) mod._retro_run();
}

function shot(file) {
  const { ptr, width, height, pitch } = frame;
  const rgb = Buffer.alloc(width * height * 3);
  const stride = (pitch >> 1) | 0;
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      let r, g, b;
      if (format === 1) {
        const v = mod.HEAPU32[(ptr >> 2) + y * ((pitch >> 2) | 0) + x];
        r = v & 0xff; g = (v >> 8) & 0xff; b = (v >> 16) & 0xff;
      } else {
        const v = mod.HEAPU16[(ptr >> 1) + y * stride + x];
        if (format === 2) {
          r = ((v >> 11) & 0x1f); g = ((v >> 5) & 0x3f); b = v & 0x1f;
          r = (r << 3) | (r >> 2); g = (g << 2) | (g >> 4); b = (b << 3) | (b >> 2);
        } else {
          r = (v >> 10) & 0x1f; g = (v >> 5) & 0x1f; b = v & 0x1f;
          r = (r << 3) | (r >> 2); g = (g << 3) | (g >> 2); b = (b << 3) | (b >> 2);
        }
      }
      const o = (y * width + x) * 3;
      rgb[o] = r; rgb[o + 1] = g; rgb[o + 2] = b;
    }
  }
  const out = path.join(GAME, "screenshots", file);
  writePng(out, width, height, rgb);
  let lit = 0;
  for (let i = 0; i < rgb.length; i += 3) {
    if (rgb[i] | rgb[i + 1] | rgb[i + 2]) lit++;
  }
  return lit;
}

const press = (bits, frames) => {
  joy = bits;
  run(frames);
  joy = 0;
  run(4);
};

/* ---------- the title screen ---------- */

run(240);
check(videoFrames === 240, "the core paints every frame (240/240)");
check(audioFrames > 40000, `the core made ${audioFrames} stereo samples`);
check(ramSize >= 0x10000, "the machine has 64 KB of RAM");
check(ram(0) === 0, "the game is on its title screen (state 0)");
const bcd = (o) => (ram(o) >> 4) * 10000 + (ram(o) & 15) * 1000 +
                  (ram(o + 1) >> 4) * 100 + (ram(o + 1) & 15) * 10 + (ram(o + 2) & 15);
check(bcd(15) === 0, "the best score starts at zero");
const titleLit = shot("web-title.png");
check(titleLit > 400, `the title screen is not blank (${titleLit} lit pixels)`);

/* ---------- press fire, watch a game start ---------- */

press(1 << 8, 2);                                   // libretro A
check(ram(0) === 1, `the trigger starts a game (state ${ram(0)})`);
check(bcd(12) === 0, "the score starts at zero");
check(ram(91) === 152 - 23, `the dino stands on the ground (y ${ram(91)})`);

/* the dino jumps when the trigger is pressed */
const y0 = ram(37) | (ram(38) << 8);
press(1 << 8, 1);
const y1 = ram(37) | (ram(38) << 8);
check(ram(41) === 1, "the trigger jumps");
check(y1 < y0, `and the dino leaves the ground (${y0} -> ${y1})`);
run(40);
check(ram(41) === 0 || ram(0) !== 1, "and it comes back down again");

const playLit = shot("web-play.png");
press(1 << 6, 4);                    // jump away, then look again
run(20);
shot("web-play2.png");
check(playLit > 400, `the playfield is not blank (${playLit} lit pixels)`);

run(20);
check(bcd(12) > 0, `the score climbs as it runs (${bcd(12)})`);
check(ram(48) > 0, "cactuses are on their way");

/* ---------- and it keeps running ---------- */

const before = { frames: videoFrames, audio: audioFrames };
run(600);
check(videoFrames - before.frames === 600, "600 more frames, all painted");
check(audioFrames > before.audio, "sound keeps coming");
check(ram(0) <= 3, "the state machine is still sane after 600 frames");

/* ---------- report ---------- */

let failed = 0;
for (const [ok, what] of checks) {
  console.log((ok ? "ok   " : "FAIL ") + what);
  if (!ok) failed++;
}
console.log(`\n${checks.length - failed}/${checks.length} checks passed`);
process.exit(failed ? 1 : 0);
