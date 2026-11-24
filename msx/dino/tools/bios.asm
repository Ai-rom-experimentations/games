; ==========================================================================
;  a 16 KB stand-in for the MSX BIOS, just for the bundled emulator
;
;  A real BIOS does a lot more, but a cartridge that never returns from
;  INIT - as every game does - only ever needs three things from it: a stack
;  pointer, the "AB" scan, and a jump to the INIT address in the header.
;
;  The emulator (tools/msx.py) loads this at $0000 and resets the CPU there,
;  which is what an MSX does when the cartridge is in slot 1.
; ==========================================================================
        org 0x0000

        di
        ld sp, 0xf380                 ; the MSX BIOS stack
        ld a, (0x4000)                ; is there a cartridge header?
        cp "A"
        jr nz, hang
        ld a, (0x4001)
        cp "B"
        jr nz, hang
        ld hl, (0x4002)               ; the INIT address
        jp (hl)                       ; from here on it is the game's machine
hang:   di
        halt
        jr hang

        defs 0x4000 - $, 0xff
