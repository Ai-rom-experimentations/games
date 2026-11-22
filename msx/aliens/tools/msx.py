"""A small MSX1 emulator, just big enough to run and check aliens.rom.

    Z80 (pypi 'z80' package, cycle counted)
    TMS9918A in Graphics I mode, including sprites (4 per line, as on the real
    chip, with the earliest sprite in the table winning an overlap)
    AY-3-8910 register model (for logging / checking notes)
    PPI at $A8-$AA (keyboard row select and matrix data)
    the joystick on the PSG's I/O port A, where the MSX really puts it
    a 16 KB stand-in for the BIOS, tools/bios.asm

The machine is an MSX1: cartridge in page 1 ($4000-$7FFF), 16 KB of RAM in
page 3 ($C000-$FFFF), nothing in page 2.  Interrupts are not modelled - the
game polls the VDP status flag, which is also the honest way to write a
cartridge that never wants to fall back into BASIC.

Requires: pip install z80 pillow
"""
CLOCK = 3579545
# NTSC TMS9918A timing: 262 lines x 342 dots at 5.369318 MHz, with the Z80
# running at 2/3 of the dot clock, so one frame is 59736 T-states (59.92 Hz);
# the vblank flag is raised after the 192 visible lines.
TICKS_PER_FRAME = 262 * 342 * 2 // 3   # 59736
VISIBLE_TICKS = 192 * 342 * 2 // 3     # 43776
VBLANK_TICKS = TICKS_PER_FRAME - VISIBLE_TICKS

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
    def color_base(self):
        # TMS9918A datasheet: R3 holds the colour table base in units of $40
        # ($2000 / $40 = $80, so bit 7 shifts out of the 16K range by itself).
        return (self.regs[3] * 0x40) & 0x3FFF

    @property
    def pattern_base(self):
        # R4 holds the pattern generator base in units of $800.
        return (self.regs[4] & 0x07) * 0x800

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
        # On a TMS9918A the earliest sprite in the table has the highest
        # priority, and only four sprites can show on any one scanline.
        size16 = self.regs[1] & 0x02
        mag = self.regs[1] & 0x01
        vram = self.vram
        sat, spr = self.sat_base, self.spr_base
        H, W = 192, 256
        covered = bytearray(W * H)
        per_line = [0] * H
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
            height *= 2 if mag else 1
            width *= 2 if mag else 1
            if any(per_line[yy] >= 4 for yy in range(sy, sy + height) if 0 <= yy < H):
                continue                    # the fifth sprite of a line is lost
            for yy in range(sy, sy + height):
                if 0 <= yy < H:
                    per_line[yy] += 1
            step = 2 if mag else 1
            scale = 2 if mag else 1
            for r in range(height // scale):
                if size16:
                    left = vram[spr + pat * 8 + r]
                    right = vram[spr + pat * 8 + 16 + r]
                    bits = (left << 8) | right
                else:
                    bits = vram[spr + pat * 8 + r]
                for b in range(width // scale):
                    if not (bits & (0x80 >> b)):
                        continue
                    for dy in range(step):
                        for dx in range(step):
                            xx = sx + b * step + dx
                            yy = sy + r * step + dy
                            if 0 <= xx < W and 0 <= yy < H and not covered[yy * W + xx]:
                                covered[yy * W + xx] = 1
                                px[yy][xx] = col



# --------------------------------------------------------------------------
#  the AY-3-8910, as the MSX wires it: register select on $A0, data on $A1
# --------------------------------------------------------------------------
class AY38910:
    """A register model of the PSG, enough to check notes and volumes."""

    def __init__(self, clock=1789772):
        self.clock = clock
        self.reg = [0] * 16
        self.sel = 0

    # ---- bus -----------------------------------------------------------
    def select(self, v):
        self.sel = v & 0x0F

    def write(self, v):
        self.reg[self.sel] = v & 0xFF

    # ---- what it is playing --------------------------------------------
    def period(self, ch):
        lo = self.reg[ch * 2]
        hi = self.reg[ch * 2 + 1] & 0x0F
        return (hi << 8) | lo

    def tone_hz(self, ch):
        p = self.period(ch)
        return self.clock / (16.0 * p) if p else 0.0

    def vol(self, ch):
        """The amplitude register, 0..15, whatever the mixer says."""
        return self.reg[8 + ch] & 0x0F

    def playing(self, ch):
        """True if the channel is audible: it has volume and a source."""
        return bool(self.vol(ch)) and (self.tone_on(ch) or self.noise_on(ch))

    def noise_hz(self):
        p = self.reg[6] & 0x1F
        return self.clock / (16.0 * p) if p else 0.0

    def noise_on(self, ch):
        return not (self.reg[7] & (1 << (3 + ch)))

    def tone_on(self, ch):
        return not (self.reg[7] & (1 << ch))


# --------------------------------------------------------------------------
#  the machine
# --------------------------------------------------------------------------
class MSX:
    """An MSX1 with a cartridge in slot 1 and 16 KB of RAM in slot 3.

    Page 0 is a tiny stand-in for the BIOS (tools/bios.asm): it checks the
    "AB" header and jumps to INIT, which is all a self contained cartridge
    ever uses the BIOS for.  There are no interrupts at all, which is fine
    because the game polls the VDP status flag - and it means the emulator
    does not have to model the IRQ line.
    """

    def __init__(self, rom, bios=b"\x00" * 0x4000):
        import z80

        self.m = z80.Z80Machine()
        mem = bytearray(0x10000)
        mem[0:0x4000] = (bios + b"\xff" * 0x4000)[:0x4000]
        mem[0x4000:0x8000] = (rom + b"\xff" * 0x4000)[:0x4000]
        mem[0x8000:0xc000] = b"\xff" * 0x4000      # no slot there
        self.m.set_memory_block(0, bytes(mem))
        self.mem = self.m.memory
        self.cpu = self.m
        self.vdp = TMS9918()
        self.ay = AY38910()
        self.joy = 0xFF                   # joystick 1, active low, bit 6 set
        self.kbd_row = 0                  # port $AA, the selected row
        self.keys = [0xFF] * 11           # port $A9, 1 = key up
        self.errors = []
        self.unknown_ports = set()
        self.rom_size = len(rom)

        # the BIOS, the cartridge and the empty page are read only
        self.m.mark_addrs(0, 0xC000, self.m.WRITE_MARK)
        self.m.set_write_callback(self._write_cb)
        self.m.set_input_callback(self._in)
        self.m.set_output_callback(self._out)
        self.m.sp = 0xF380                # where the BIOS puts the stack
        self.m.pc = 0

    # ---- memory --------------------------------------------------------
    def _write_cb(self, addr, value):
        self.errors.append("write %02X to ROM at %04X (pc=%04X)"
                           % (value, addr, self.m.pc))

    # ---- I/O -----------------------------------------------------------
    def _out(self, port, value):
        p = port & 0xFF
        if p == 0x98:
            self.vdp.write_data(value)
        elif p == 0x99:
            self.vdp.write_ctrl(value)
        elif p == 0xA0:
            self.ay.select(value)
        elif p == 0xA1:
            self.ay.write(value)
        elif p == 0xAA:
            self.kbd_row = value & 0x0F    # PPI port C: the keyboard row
        elif p == 0xAB:
            pass                          # PPI control: printer port, unused
        else:
            self.unknown_ports.add(p)

    def _in(self, port):
        p = port & 0xFF
        if p == 0x98:
            return self.vdp.read_data()
        if p == 0x99:
            return self.vdp.read_status()
        if p == 0xA2:
            # reading the PSG gives back the selected register; register 14 is
            # the joystick port (register 15 selects which one, $8F = port 1)
            if self.ay.sel == 14:
                return self.joy
            return 0xFF
        if p == 0xA8:
            return 0xFF                   # PPI port A is the RAM mapper, not a pad
        if p == 0xA9:
            row = self.kbd_row            # PPI port B: the selected row
            return self.keys[row] if row < len(self.keys) else 0xFF
        if p == 0xAA:
            return self.kbd_row | 0xF0    # port C reads back what it was given
        self.unknown_ports.add(p)
        return 0xFF

    # ---- the joystick and the keyboard ---------------------------------
    def set_pad(self, buttons):
        """buttons: bit mask, 1 = pressed (up, down, left, right, A, B)."""
        self.joy = (~buttons) & 0x3F | 0xC0

    def key(self, row, bit, down=True):
        """Press or release one key of the matrix.  Row 8 is the cursor keys
        and space: bit 7 right, 6 down, 5 up, 4 left, 0 space."""
        if down:
            self.keys[row] &= ~(1 << bit) & 0xFF
        else:
            self.keys[row] |= (1 << bit) & 0xFF

    # ---- running -------------------------------------------------------
    def run_ticks(self, ticks):
        self.cpu.ticks_to_stop = ticks
        guard = 0
        while self.cpu.ticks_to_stop > 0:
            self.cpu.run()
            guard += 1
            if guard > 200:
                break

    def run_frame(self):
        """One frame: the visible lines, then the VDP raises the flag."""
        self.run_ticks(VBLANK_TICKS)
        self.run_ticks(VISIBLE_TICKS)
        self.vdp.status |= 0x80
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


def load_bios(path):
    with open(path, "rb") as f:
        return f.read()
