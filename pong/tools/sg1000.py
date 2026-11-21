"""A small SG-1000 emulator, just big enough to run and check pong.sg.

    Z80 (pypi 'z80' package, cycle counted)
    TMS9918A in Graphics I mode, including sprites
    SN76489 register model (for logging / WAV rendering)
    1 KB of RAM mirrored over $C000-$FFFF, cart ROM write protection

Requires: pip install z80 pillow
"""

CLOCK = 3579545
TICKS_PER_FRAME = CLOCK // 60          # 59659

# TMS9918A palette (well known RGB approximations)
PALETTE = [
    (0, 0, 0),        # 0 transparent
    (0, 0, 0),        # 1 black
    (33, 200, 66),    # 2 medium green
    (94, 220, 120),   # 3 light green
    (84, 85, 237),    # 4 dark blue
    (125, 118, 252),  # 5 light blue
    (212, 82, 77),    # 6 dark red
    (66, 235, 245),   # 7 cyan
    (252, 85, 84),    # 8 medium red
    (255, 121, 120),  # 9 light red
    (212, 193, 84),   # 10 dark yellow
    (230, 206, 128),  # 11 light yellow
    (33, 176, 59),    # 12 dark green
    (201, 91, 186),   # 13 magenta
    (204, 204, 204),  # 14 grey
    (255, 255, 255),  # 15 white
]

# joypad bits as they appear on the ports (1 = not pressed on real hardware)
P1_UP, P1_DOWN, P1_LEFT, P1_RIGHT, P1_B1, P1_B2 = 0x01, 0x02, 0x04, 0x08, 0x10, 0x20
P2_UP, P2_DOWN = 0x40, 0x80                       # port $DC, bits 6-7
P2_LEFT, P2_RIGHT, P2_B1, P2_B2 = 0x01, 0x02, 0x04, 0x08   # port $DD


class TMS9918:
    def __init__(self):
        self.vram = bytearray(0x4000)
        self.regs = [0] * 8
        self.latch = None
        self.addr = 0
        self.status = 0
        self.read_buf = 0

    # ---- I/O -----------------------------------------------------------
    def write_data(self, v):
        self.vram[self.addr & 0x3FFF] = v
        self.addr = (self.addr + 1) & 0x3FFF
        self.read_buf = v

    def read_data(self):
        v = self.vram[self.addr & 0x3FFF]
        self.addr = (self.addr + 1) & 0x3FFF
        return v

    def write_ctrl(self, v):
        if self.latch is None:
            self.latch = v
            return
        if v & 0x80:
            self.regs[v & 0x07] = self.latch
        else:
            self.addr = ((v & 0x3F) << 8) | self.latch
            self.read_buf = self.vram[self.addr & 0x3FFF]
        self.latch = None

    def read_status(self):
        v = self.status
        self.status = 0                    # a read clears F, 5S and C
        self.latch = None
        return v

    # ---- tables --------------------------------------------------------
    @property
    def name_base(self):
        return (self.regs[2] & 0x0F) * 0x400

    @property
    def pattern_base(self):
        return (self.regs[3] & 0x07) * 0x800

    @property
    def color_base(self):
        return (self.regs[4] << 6) & 0x3FFF

    @property
    def sat_base(self):
        return (self.regs[5] & 0x7F) * 0x80

    @property
    def spr_base(self):
        return (self.regs[6] & 0x07) * 0x800

    @property
    def mode(self):
        m1 = 1 if self.regs[1] & 0x10 else 0
        m2 = 1 if self.regs[1] & 0x08 else 0
        m3 = 1 if self.regs[0] & 0x02 else 0
        return (m1 << 2) | (m2 << 1) | m3

    # ---- rendering -----------------------------------------------------
    def render(self):
        """256x192 list of rows of (r, g, b) tuples."""
        W, H = 256, 192
        px = [[PALETTE[self.regs[7] & 0x0F]] * W for _ in range(H)]
        if not (self.regs[1] & 0x40):
            return px                       # display blanked
        if self.mode != 0:
            raise NotImplementedError("only Graphics I is rendered")
        vram = self.vram
        nb, pb, cb = self.name_base, self.pattern_base, self.color_base
        for row in range(24):
            for col in range(32):
                name = vram[nb + row * 32 + col]
                colour = vram[cb + (name >> 3)]
                fg = PALETTE[colour >> 4]
                bg = PALETTE[colour & 0x0F]
                pat = pb + name * 8
                y0, x0 = row * 8, col * 8
                for r in range(8):
                    bits = vram[pat + r]
                    line = px[y0 + r]
                    for b in range(8):
                        line[x0 + b] = fg if bits & (0x80 >> b) else bg
        self._sprites(px)
        return px

    def _sprites(self, px):
        size16 = self.regs[1] & 0x02
        mag = self.regs[1] & 0x01
        vram = self.vram
        sat, spr = self.sat_base, self.spr_base
        H, W = 192, 256
        for i in range(32):
            base = sat + i * 4
            y = vram[base]
            if y == 0xD0:                   # end of the sprite list
                break
            sy = y + 1
            if sy >= 192:
                sy -= 256                   # sprites may hang over the top
            sx = vram[base + 1]
            pat = vram[base + 2]
            tag = vram[base + 3]
            colour = tag & 0x0F
            if colour == 0:                 # transparent sprite
                continue
            if tag & 0x80:                  # early clock
                sx -= 32
            col = PALETTE[colour]
            if size16:
                pat &= 0xFC
                height, width = 16, 16
            else:
                height, width = 8, 8
            for r in range(height):
                if size16:
                    left = vram[spr + pat * 8 + r]
                    right = vram[spr + pat * 8 + 16 + r]
                    bits = (left << 8) | right
                else:
                    bits = vram[spr + pat * 8 + r]
                for b in range(width):
                    if not (bits & (0x80 >> b)):
                        continue
                    for dy in range(2 if mag else 1):
                        for dx in range(2 if mag else 1):
                            xx = sx + b * (2 if mag else 1) + dx
                            yy = sy + r * (2 if mag else 1) + dy
                            if 0 <= xx < W and 0 <= yy < H:
                                px[yy][xx] = col


class SN76489:
    """Register model of the PSG: enough to check pitches and to render audio."""

    def __init__(self):
        self.tone = [0] * 4
        self.vol = [15] * 4
        self.latched_ch = 0
        self.latched_vol = False
        self.writes = 0

    def write(self, v):
        self.writes += 1
        if v & 0x80:
            self.latched_ch = (v >> 5) & 3
            self.latched_vol = bool(v & 0x10)
            low = v & 0x0F
        else:
            low = v & 0x3F
        ch = self.latched_ch
        if self.latched_vol:
            self.vol[ch] = low & 0x0F
        elif ch == 3:
            self.tone[3] = low & 0x07
        elif v & 0x80:
            self.tone[ch] = (self.tone[ch] & 0x3F0) | low
        else:
            self.tone[ch] = (self.tone[ch] & 0x00F) | (low << 4)

    def tone_hz(self, ch):
        return CLOCK / (32 * (self.tone[ch] or 1))

    def snapshot(self):
        return (tuple(self.tone), tuple(self.vol))


class SG1000:
    def __init__(self, rom):
        import z80

        self.m = z80.Z80Machine()
        mem = bytearray(0x10000)
        mem[0:len(rom)] = rom
        self.m.set_memory_block(0, bytes(mem))
        self.mem = self.m.memory
        self.cpu = self.m
        self.vdp = TMS9918()
        self.psg = SN76489()
        self.joy1 = 0xFF
        self.joy2 = 0xFF
        self.errors = []
        self.unknown_ports = set()
        self.rom_size = len(rom)

        rom_hi = min(len(rom), 0xC000)
        self.m.mark_addrs(0, rom_hi, self.m.WRITE_MARK)          # ROM writes
        if rom_hi < 0xC400:                                       # 1 KB RAM mirror
            self.m.mark_addrs(0xC400, 0x10000 - 0xC400,
                              self.m.READ_MARK | self.m.WRITE_MARK)
        self.m.set_read_callback(self._read_cb)
        self.m.set_write_callback(self._write_cb)
        self.m.set_input_callback(self._in)
        self.m.set_output_callback(self._out)
        self.m.sp = 0xDFFF
        self.m.pc = 0

    # ---- memory --------------------------------------------------------
    def _read_cb(self, addr):
        return self.mem[0xC000 + (addr & 0x3FF)]

    def _write_cb(self, addr, value):
        if addr < 0xC000:
            self.errors.append("write %02X to ROM at %04X (pc=%04X)"
                               % (value, addr, self.m.pc))
            return
        self.mem[0xC000 + (addr & 0x3FF)] = value

    # ---- I/O -----------------------------------------------------------
    def _out(self, port, value):
        p = port & 0xFF
        if p == 0xBE:
            self.vdp.write_data(value)
        elif p == 0xBF:
            self.vdp.write_ctrl(value)
        elif p == 0x7F:
            self.psg.write(value)
        else:
            self.unknown_ports.add(p)

    def _in(self, port):
        p = port & 0xFF
        if p == 0xBE:
            return self.vdp.read_data()
        if p == 0xBF:
            return self.vdp.read_status()
        if p == 0xDC:
            return self.joy1
        if p == 0xDD:
            return self.joy2
        self.unknown_ports.add(p)
        return 0xFF

    # ---- controllers ---------------------------------------------------
    def set_pads(self, p1=0, p2=0):
        """p1/p2 are bit masks of the buttons currently held down."""
        v = 0xFF
        if p1 & P1_UP:
            v &= ~P1_UP
        if p1 & P1_DOWN:
            v &= ~P1_DOWN
        if p1 & P1_LEFT:
            v &= ~P1_LEFT
        if p1 & P1_RIGHT:
            v &= ~P1_RIGHT
        if p1 & P1_B1:
            v &= ~P1_B1
        if p1 & P1_B2:
            v &= ~P1_B2
        if p2 & P2_UP:
            v &= ~P2_UP
        if p2 & P2_DOWN:
            v &= ~P2_DOWN
        self.joy1 = v
        v = 0xFF
        if p2 & P2_LEFT:
            v &= ~P2_LEFT
        if p2 & P2_RIGHT:
            v &= ~P2_RIGHT
        if p2 & P2_B1:
            v &= ~P2_B1
        if p2 & P2_B2:
            v &= ~P2_B2
        self.joy2 = v

    # ---- running -------------------------------------------------------
    def run_frame(self, ticks=TICKS_PER_FRAME):
        self.vdp.status |= 0x80             # vertical blank flag
        self.cpu.ticks_to_stop = ticks
        guard = 0
        while self.cpu.ticks_to_stop > 0:
            self.cpu.run()
            guard += 1
            if guard > 200:
                break
        return self.cpu.pc

    def screenshot(self):
        from PIL import Image
        img = Image.new("RGB", (256, 192))
        img.putdata([c for row in self.vdp.render() for c in row])
        return img

    def ram(self, offset):
        return self.mem[0xC000 + offset]


def load_rom(path):
    with open(path, "rb") as f:
        return f.read()
