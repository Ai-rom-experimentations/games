/*
 * CHROME DINO in a browser.
 *
 * A very small libretro host: it loads the blueMSX libretro core (compiled to
 * WebAssembly), lays a C-BIOS MSX1 out on the core's in-memory filesystem,
 * drops dino.rom into a cartridge slot and then calls retro_run() sixty
 * times a second, painting the frames the core hands back and feeding its
 * audio to a ring buffer that an AudioContext drains.
 *
 * Nothing here depends on a network: the core, the C-BIOS files and the
 * cartridge are all files next to this script.
 */

const BASE = new URL("./", import.meta.url);

const CORE_DIR = "core/";
const CORE_JS = "bluemsx_libretro.js";
const CORE_WASM = "bluemsx_libretro.wasm";
const ROM_URL = "../dino.rom";

const MACHINE = "MSX - C-BIOS";       // the open-source BIOS, no proprietary ROMs
const SYSTEM_DIR = "/bios";              // where the core looks for Machines/...
const SAVE_DIR = "/saves";
const ROM_PATH = "/cart/dino.rom";
const BIOS_FILES = [
  "Machines/" + MACHINE + "/config.ini",
  "Machines/" + MACHINE + "/cbios_main_msx1.rom",
  "Machines/" + MACHINE + "/cbios_logo_msx1.rom",
  "Machines/" + MACHINE + "/cbios.txt",
];

// libretro joypad ids (what returns from input_state)
const J_B = 0, J_Y = 1, J_SELECT = 2, J_START = 3,
      J_UP = 4, J_DOWN = 5, J_LEFT = 6, J_RIGHT = 7,
      J_A = 8, J_X = 9, J_MASK = 256;

const $ = (sel) => document.querySelector(sel);
const errorBox = $("#error");
const overlay = $("#overlay");
const startButton = $("#start");
const canvas = $("#vdp");

function showError(what) {
  const text = what && what.stack ? what.stack : String(what);
  if (errorBox) {
    errorBox.hidden = false;
    errorBox.textContent = text;
  }
  console.error(what);
  if (overlay && overlay.parentElement) {
    overlay.hidden = false;
    overlay.classList.remove("busy");
    overlay.querySelector("h2").textContent = "OOPS";
    overlay.querySelector("p").textContent =
      "The emulator could not start. The details are under the picture.";
    if (startButton) startButton.hidden = true;
  }
}

window.addEventListener("error", (e) => showError(e.error || e.message));
window.addEventListener("unhandledrejection", (e) => showError(e.reason));

/* ------------------------------------------------------------------ *
 * the core
 * ------------------------------------------------------------------ */

async function loadCore() {
  // The published glue is a Node build: it hardcodes ENVIRONMENT_IS_NODE and
  // pulls in "module"/"fs".  The browser paths are all still in the file
  // behind that flag, so flip it and import the result as a module blob.
  const source = await fetch(new URL(CORE_DIR + CORE_JS, BASE)).then((r) => {
    if (!r.ok) throw new Error("cannot fetch the core: " + r.status);
    return r.text();
  });
  const flag = "var ENVIRONMENT_IS_NODE=true;";
  if (!source.includes(flag)) throw new Error("the core glue is not the build this page expects");
  const patched = source.replace(flag, "var ENVIRONMENT_IS_NODE=false;");
  const blob = URL.createObjectURL(new Blob([patched], { type: "text/javascript" }));
  try {
    const { default: createCore } = await import(blob);
    const wasmBinary = await fetch(new URL(CORE_DIR + CORE_WASM, BASE)).then((r) => {
      if (!r.ok) throw new Error("cannot fetch the core wasm: " + r.status);
      return r.arrayBuffer();
    });
    return await createCore({
      wasmBinary,
      locateFile: (name) => new URL(CORE_DIR + name, BASE).href,
      print: (...a) => console.log("[core]", ...a),
      printErr: (...a) => console.warn("[core]", ...a),
    });
  } finally {
    URL.revokeObjectURL(blob);
  }
}

function memfs(mod, path, bytes) {
  const parts = path.split("/").filter(Boolean);
  let dir = "";
  for (const part of parts.slice(0, -1)) {
    dir += "/" + part;
    try { mod.FS.mkdir(dir); } catch (e) { /* already there */ }
  }
  mod.FS.writeFile(path, bytes);
}

const fetchBytes = async (path) => new Uint8Array(await fetch(new URL(path, BASE)).then((r) => {
  if (!r.ok) throw new Error("cannot fetch " + path + ": " + r.status);
  return r.arrayBuffer();
}));

/* ------------------------------------------------------------------ *
 * audio: the core pushes 44.1 kHz stereo int16, a ring buffer and a
 * (deprecated but universal) ScriptProcessor drain it
 * ------------------------------------------------------------------ */

const RING_BITS = 17;
const RING_LEN = 1 << RING_BITS;        // in int16 samples, so 65536 stereo frames
const RING_MASK = RING_LEN - 1;

const audio = {
  ctx: null,
  node: null,
  gain: null,
  muted: false,
  ring: new Int16Array(RING_LEN),
  read: 0,
  count: 0,
};

function audioWrite(ptr, frames, mod) {
  const n = frames * 2;
  if (n <= 0) return;
  const heap = mod.HEAP16;
  const from = ptr >> 1;
  let room = RING_LEN - audio.count;
  if (n > room) {                        // overrun: drop the oldest
    const drop = n - room;
    audio.read = (audio.read + drop) & RING_MASK;
    audio.count -= drop;
    room = RING_LEN - audio.count;
  }
  let write = (audio.read + audio.count) & RING_MASK;
  const take = Math.min(n, room);
  for (let i = 0; i < take; i++) {
    audio.ring[write] = heap[from + i];
    write = (write + 1) & RING_MASK;
  }
  audio.count += take;
}

function audioSilence() {
  audio.read = 0;
  audio.count = 0;
}

function startAudio() {
  if (audio.ctx) return;
  const Ctx = window.AudioContext || window.webkitAudioContext;
  if (!Ctx) return;
  audio.ctx = new Ctx({ latencyHint: "interactive" });
  audio.gain = audio.ctx.createGain();
  audio.gain.gain.value = audio.muted ? 0 : 0.7;
  audio.gain.connect(audio.ctx.destination);

  const node = audio.ctx.createScriptProcessor(2048, 0, 2);
  node.onaudioprocess = (event) => {
    const out = event.outputBuffer;
    const left = out.getChannelData(0);
    const right = out.getChannelData(1);
    const ring = audio.ring;
    // keep the queue short, or the picture and the sound drift apart
    if (audio.count > RING_LEN * 0.75) {
      const drop = audio.count - (RING_LEN >> 3);
      audio.read = (audio.read + drop) & RING_MASK;
      audio.count -= drop;
    }
    for (let i = 0; i < left.length; i++) {
      if (audio.count >= 2) {
        left[i] = ring[audio.read] / 32768;
        right[i] = ring[(audio.read + 1) & RING_MASK] / 32768;
        audio.read = (audio.read + 2) & RING_MASK;
        audio.count -= 2;
      } else {
        left[i] = 0;
        right[i] = 0;
      }
    }
  };
  node.connect(audio.gain);
  audio.node = node;
}

/* ------------------------------------------------------------------ *
 * the video callback paints straight into the canvas
 * ------------------------------------------------------------------ */

function createPainter(ctx) {
  let format = 0;             // 0 = 0RGB1555, 1 = XRGB8888, 2 = RGB565
  let image = null;
  let pixels = null;
  let lut565 = null;
  let lut555 = null;

  const buildLut = (bits) => {
    const lut = new Uint32Array(1 << bits);
    for (let v = 0; v < lut.length; v++) {
      let r, g, b;
      if (bits === 16) {             // RGB565
        r = (v >> 11) & 0x1f; g = (v >> 5) & 0x3f; b = v & 0x1f;
        r = (r << 3) | (r >> 2); g = (g << 2) | (g >> 4); b = (b << 3) | (b >> 2);
      } else {                       // 0RGB1555
        r = (v >> 10) & 0x1f; g = (v >> 5) & 0x1f; b = v & 0x1f;
        r = (r << 3) | (r >> 2); g = (g << 3) | (g >> 2); b = (b << 3) | (b >> 2);
      }
      lut[v] = (255 << 24) | (b << 16) | (g << 8) | r;   // little endian RGBA
    }
    return lut;
  };

  return {
    setFormat(f) { format = f; },
    get format() { return format; },
    draw(mod, data, width, height, pitch) {
      if (!data || !width || !height) return;
      if (!image || image.width !== width || image.height !== height) {
        image = new ImageData(width, height);
        pixels = new Uint32Array(image.data.buffer);
        canvas.width = width;
        canvas.height = height;
      }
      const stride = (pitch >> 1) | 0;      // 16 bit pixels into a byte pitch
      if (format === 1) {
        const src = mod.HEAPU32;
        const base = data >> 2;
        const stride32 = (pitch >> 2) | 0;
        for (let y = 0; y < height; y++) {
          const row = base + y * stride32;
          const out = y * width;
          for (let x = 0; x < width; x++) {
            const v = src[row + x];
            pixels[out + x] = 0xff000000 | ((v & 0xff) << 16) | (v & 0xff00) | ((v >> 16) & 0xff);
          }
        }
      } else {
        const heap = mod.HEAPU16;
        const base = data >> 1;
        const lut = format === 2
          ? (lut565 || (lut565 = buildLut(16)))
          : (lut555 || (lut555 = buildLut(15)));
        for (let y = 0; y < height; y++) {
          const row = base + y * stride;
          const out = y * width;
          for (let x = 0; x < width; x++) pixels[out + x] = lut[heap[row + x]];
        }
      }
      ctx.putImageData(image, 0, 0);
    },
  };
}

/* ------------------------------------------------------------------ *
 * boot
 * ------------------------------------------------------------------ */

const state = {
  mod: null,
  fps: 60,
  running: false,
  started: false,
  joy: 0,
  frames: 0,
};

function setOverlay(mode) {
  if (!overlay) return;
  if (mode === "hide") { overlay.hidden = true; return; }
  overlay.hidden = false;
  overlay.classList.toggle("busy", mode === "loading");
  overlay.querySelector("h2").textContent = mode === "loading" ? "LOADING" : "CHROME DINO";
  overlay.querySelector("p").textContent = mode === "loading"
    ? "Waking up an MSX1 with C-BIOS in it, and sliding the cartridge into slot 1."
    : "Tap to switch the machine on. Sound starts with your tap, because browsers like it that way.";
  startButton.hidden = mode === "loading";
}

async function boot() {
  const ctx = canvas.getContext("2d", { alpha: false });
  if (!ctx) throw new Error("this browser will not give me a 2D canvas");
  const painter = createPainter(ctx);

  const mod = await loadCore();
  state.mod = mod;

  // the BIOS and the cartridge, laid out where the core expects them
  for (const file of BIOS_FILES) {
    memfs(mod, SYSTEM_DIR + "/" + file, await fetchBytes(CORE_DIR + "bios/" + file));
  }
  const rom = await fetchBytes(ROM_URL);
  if (rom.length < 16 || rom[0] !== 0x41 || rom[1] !== 0x42) {
    throw new Error("that does not look like an MSX cartridge (no 'AB' header)");
  }
  memfs(mod, ROM_PATH, rom);
  try { mod.FS.mkdir(SAVE_DIR); } catch (e) { /* fine */ }

  const vars = { bluemsx_msxtype: MACHINE };
  const strPtr = (s) => {
    const bytes = mod.lengthBytesUTF8(s) + 1;
    const ptr = mod._malloc(bytes);
    mod.stringToUTF8(s, ptr, bytes);
    return ptr;
  };

  const envCb = (cmd, data) => {
    switch (cmd) {
      case 3:                                    // GET_CAN_DUPE
        mod.HEAPU8[data] = 1;
        return true;
      case 9:                                    // GET_SYSTEM_DIRECTORY
        mod.HEAPU32[data >> 2] = strPtr(SYSTEM_DIR);
        return true;
      case 31:                                   // GET_SAVE_DIRECTORY
        mod.HEAPU32[data >> 2] = strPtr(SAVE_DIR);
        return true;
      case 10:                                   // SET_PIXEL_FORMAT
        painter.setFormat(mod.HEAPU32[data >> 2]);
        return true;
      case 15: {                                 // GET_VARIABLE
        const key = mod.UTF8ToString(mod.HEAPU32[data >> 2]);
        if (vars[key] === undefined) return false;
        mod.HEAPU32[(data + 4) >> 2] = strPtr(vars[key]);
        return true;
      }
      case 16:                                   // SET_VARIABLES
        return true;
      case 27: {                                 // GET_LOG_INTERFACE
        const fn = mod.addFunction((level, message) => {
          const text = mod.UTF8ToString(message);
          if (level >= 2) console.warn("[blueMSX]", text); else console.log("[blueMSX]", text);
        }, "viii");
        mod.HEAPU32[data >> 2] = fn;
        return true;
      }
      case 39:                                   // GET_LANGUAGE -> english
        mod.HEAPU32[data >> 2] = 0;
        return true;
      case 52:                                   // GET_CORE_OPTIONS_VERSION
        mod.HEAPU32[data >> 2] = 2;
        return true;
      case 65587:                                // GET_INPUT_BITMASKS (experimental)
        if (data) mod.HEAPU8[data] = 1;           // asked with a null pointer
        return true;
      default:
        return false;
    }
  };

  mod._retro_set_environment(mod.addFunction(envCb, "iii"));
  mod._retro_init();

  mod._retro_set_video_refresh(mod.addFunction((data, width, height, pitch) => {
    state.frames++;
    painter.draw(mod, data, width, height, pitch);
  }, "viiii"));
  mod._retro_set_audio_sample_batch(mod.addFunction((data, frames) => {
    audioWrite(data, frames, mod);
    return frames;
  }, "iii"));
  mod._retro_set_audio_sample(mod.addFunction(() => {}, "vii"));
  mod._retro_set_input_poll(mod.addFunction(() => {}, "v"));
  mod._retro_set_input_state(mod.addFunction((port, device, index, id) => {
    if (port !== 0 || device !== 1) return 0;       // one joystick, in port 1
    if (id === J_MASK) return state.joy;
    return id <= 15 ? (state.joy >> id) & 1 : 0;
  }, "iiiii"));

  const romPtr = mod._malloc(rom.length);
  mod.HEAPU8.set(rom, romPtr);
  const info = mod._malloc(16);
  mod.HEAPU32[info >> 2] = strPtr(ROM_PATH);
  mod.HEAPU32[(info + 4) >> 2] = romPtr;
  mod.HEAPU32[(info + 8) >> 2] = rom.length;
  mod.HEAPU32[(info + 12) >> 2] = 0;
  if (!mod._retro_load_game(info)) throw new Error("the core refused to load dino.rom");

  const av = mod._malloc(64);
  mod._retro_get_system_av_info(av);
  const view = new DataView(mod.HEAPU8.buffer);
  const fps = view.getFloat64(av + 24, true);
  state.fps = fps > 1 && fps < 1000 ? fps : 60;

  // skip the C-BIOS banner so the page opens on the game's title screen
  for (let i = 0; i < 240; i++) mod._retro_run();
  audioSilence();
  state.frames = 0;

  setOverlay("ready");
}

/* ------------------------------------------------------------------ *
 * the loop
 * ------------------------------------------------------------------ */

function pollGamepad() {
  if (!navigator.getGamepads) return 0;
  const pads = navigator.getGamepads();
  for (const pad of pads) {
    if (!pad) continue;
    let bits = 0;
    const pressed = (i) => !!(pad.buttons[i] && pad.buttons[i].pressed);
    const axis = (i) => pad.axes[i] || 0;
    if (pressed(12) || axis(1) < -0.5) bits |= 1 << J_UP;
    if (pressed(13) || axis(1) > 0.5) bits |= 1 << J_DOWN;
    if (pressed(14) || axis(0) < -0.5) bits |= 1 << J_LEFT;
    if (pressed(15) || axis(0) > 0.5) bits |= 1 << J_RIGHT;
    if (pressed(0) || pressed(1) || pressed(2)) bits |= 1 << J_A;
    if (pressed(3) || pressed(5)) bits |= 1 << J_B;
    if (pressed(9)) bits |= 1 << J_START;
    if (bits) return bits;
  }
  return 0;
}

function start() {
  if (state.started || !state.mod) return;
  state.started = true;
  state.running = true;
  startAudio();
  if (audio.ctx && audio.ctx.state === "suspended") audio.ctx.resume();
  setOverlay("hide");
  paintPauseButton();
  let last = performance.now();
  let lag = 0;
  const step = 1000 / state.fps;

  const tick = (now) => {
    requestAnimationFrame(tick);
    const delta = Math.min(now - last, 250);
    last = now;
    if (!state.running) return;
    lag += delta;
    // never try to catch up more than four frames; a slow tablet should
    // slow the game down, not spiral
    let budget = 4;
    while (lag >= step && budget-- > 0) {
      state.joy = pollGamepad() | state.keyJoy | state.touchJoy;
      state.mod._retro_run();
      lag -= step;
    }
    if (lag > step * 8) lag = 0;
  };
  requestAnimationFrame(tick);
}

/* ------------------------------------------------------------------ *
 * input
 * ------------------------------------------------------------------ */

state.keyJoy = 0;
state.touchJoy = 0;

const KEYMAP = {
  ArrowUp: J_UP, KeyW: J_UP,
  ArrowDown: J_DOWN, KeyS: J_DOWN,
  ArrowLeft: J_LEFT, KeyA: J_LEFT,
  ArrowRight: J_RIGHT, KeyD: J_RIGHT,
  Space: J_A, KeyZ: J_A, KeyJ: J_A,
  KeyX: J_B, KeyK: J_B,
  Enter: J_START,
};

window.addEventListener("keydown", (e) => {
  const bit = KEYMAP[e.code];
  if (bit === undefined) return;
  e.preventDefault();
  state.keyJoy |= 1 << bit;
  if (overlay && !overlay.hidden) start();
}, { passive: false });

window.addEventListener("keyup", (e) => {
  const bit = KEYMAP[e.code];
  if (bit === undefined) return;
  e.preventDefault();
  state.keyJoy &= ~(1 << bit);
}, { passive: false });

window.addEventListener("blur", () => { state.keyJoy = 0; state.touchJoy = 0; });

for (const button of document.querySelectorAll("#pad [data-btn]")) {
  const bit = 1 << Number(button.dataset.btn);
  const press = (e) => {
    e.preventDefault();
    button.classList.add("on");
    state.touchJoy |= bit;
    if (overlay && !overlay.hidden) start();
  };
  const release = (e) => {
    e.preventDefault();
    button.classList.remove("on");
    state.touchJoy &= ~bit;
  };
  button.addEventListener("pointerdown", press);
  button.addEventListener("pointerup", release);
  button.addEventListener("pointercancel", release);
  button.addEventListener("pointerleave", release);
  button.addEventListener("contextmenu", (e) => e.preventDefault());
}

/* tapping the picture is a fire press, like the trigger on a real pad */
canvas.addEventListener("pointerdown", (e) => {
  e.preventDefault();
  if (overlay && !overlay.hidden) { start(); return; }
  state.touchJoy |= 1 << J_A;
});
canvas.addEventListener("pointerup", () => { state.touchJoy &= ~(1 << J_A); });
canvas.addEventListener("pointercancel", () => { state.touchJoy &= ~(1 << J_A); });

/* ------------------------------------------------------------------ *
 * the buttons
 * ------------------------------------------------------------------ */

function paintPauseButton() {
  const button = $("#b-pause");
  if (!button) return;
  button.textContent = state.running ? "PAUSE" : "PLAY";
  button.setAttribute("aria-pressed", String(!state.running));
}

$("#b-pause").addEventListener("click", () => {
  if (!state.started) { start(); return; }
  state.running = !state.running;
  if (audio.ctx) {
    if (state.running) audio.ctx.resume(); else audio.ctx.suspend();
  }
  paintPauseButton();
});

$("#b-reset").addEventListener("click", () => {
  if (!state.mod) return;
  audioSilence();
  state.mod._retro_reset();
});

$("#b-sound").addEventListener("click", (e) => {
  audio.muted = !audio.muted;
  if (audio.gain) audio.gain.gain.value = audio.muted ? 0 : 0.7;
  e.currentTarget.setAttribute("aria-pressed", String(!audio.muted));
  e.currentTarget.textContent = audio.muted ? "MUTED" : "SOUND";
});

$("#b-full").addEventListener("click", () => {
  const root = document.documentElement;
  const active = document.fullscreenElement || document.webkitFullscreenElement;
  if (active) {
    (document.exitFullscreen || document.webkitExitFullscreen).call(document);
  } else if (root.requestFullscreen) {
    root.requestFullscreen().catch(() => document.body.classList.toggle("cinema"));
  } else if (root.webkitRequestFullscreen) {
    try { root.webkitRequestFullscreen(); } catch (e) { document.body.classList.toggle("cinema"); }
  } else {
    document.body.classList.toggle("cinema");
  }
});

startButton.addEventListener("click", () => start());

document.addEventListener("visibilitychange", () => {
  if (document.hidden && state.running) {
    state.running = false;
    if (audio.ctx) audio.ctx.suspend();
    paintPauseButton();
  }
});

if (window.matchMedia && window.matchMedia("(hover: none)").matches) {
  document.body.classList.add("touch");
}

boot().catch(showError);
