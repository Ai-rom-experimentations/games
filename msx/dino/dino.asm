; ==========================================================================
;  CHROME DINO - the Chrome offline dinosaur, ported to the MSX1
;
;  Z80 + TMS9918A in Graphics II + AY-3-8910.  A 16 KB cartridge with the
;  header at $4000 and INIT at $4010: the BIOS starts it, the game takes the
;  machine over and never calls back.  Interrupts stay off and the frame tick
;  is the VDP's own status flag, which is how a cartridge that does not want
;  to be a BASIC program does it.
;
;  The sprites are the real ones.  tools/gen_gfx.py cuts the dino, the cacti,
;  the pterodactyls, the cloud, the moon, the stars and the digits out of
;  Chromium's own sprite sheet (tools/chrome-sprite.png, BSD licence, see
;  LICENSE-chromium), halves them and writes gfx.asm.  The three sounds are
;  the real ones too: tools/chrome-sounds/*.mp3, measured by
;  tools/analyse_sound.py and re-drawn for the PSG.  The music is a
;  ProTracker module turned into two PSG channels by tools/mod2msx.py.
;
;  Build:  make            (sjasmplus --raw=dino.rom dino.asm)
;  Check:  make check      (tools/capture.py, the bundled MSX emulator)
; ==========================================================================
        org 0x4000

; ---- MSX cartridge header ------------------------------------------------
        defb "AB"                     ; the BIOS looks for these two
        defw start                    ; INIT
        defw 0                        ; STATEMENT
        defw 0                        ; DEVICE
        defw 0                        ; TEXT
        defs 6                        ; reserved

; ---- I/O ports -----------------------------------------------------------
VDPDATA equ 0x98
VDPCTRL equ 0x99
PSGREG  equ 0xa0
PSGDATA equ 0xa1
PPIKEY  equ 0xa9
PPIROW  equ 0xaa

; ---- the pad -------------------------------------------------------------
J_UP    equ 0x01
J_DOWN  equ 0x02
J_LEFT  equ 0x04
J_RIGHT equ 0x08
J_FIRE  equ 0x10
J_B     equ 0x20

; ---- VDP tables ----------------------------------------------------------
NAME    equ 0x1800
SAT     equ 0x1b00
SPRPAT  equ 0x3800
COLOUR  equ 0x2000

; ---- the shape of the screen --------------------------------------------
GROUND_Y    equ 152                   ; the horizon line; feet stand here
GROUND_ROW  equ GROUND_Y / 8          ; 19
SAND_ROW    equ 20
HORIZON_ROW equ 15                    ; the sky goes deep from here down
DINO_X      equ 24
DINO_H      equ 23
DINO_DUCK_H equ 15
CACTUS_S_W  equ 8
CACTUS_S_H  equ 17
CACTUS_L_W  equ 12
CACTUS_L_H  equ 25
BIRD_W      equ 23
BIRD_H      equ 20
BIRD_LOW    equ 128                   ; jump over this one
BIRD_MID    equ 96                    ; jump it or duck under it
BIRD_HIGH   equ 64                    ; run under it
MAX_OB      equ 3
MAX_CLOUD   equ 2
OB_SIZE     equ 6
CL_SIZE     equ 6
OB_ON       equ 0
OB_XL       equ 1
OB_XH       equ 2
OB_Y        equ 3
OB_TYPE     equ 4
OB_FRAME    equ 5
CL_ON       equ 0
CL_XL       equ 1
CL_XH       equ 2
CL_Y        equ 3
CL_PH       equ 4
CL_SET      equ 5
CLOUD_SETS  equ 2

; ---- physics, in sixteenths of a pixel per frame -------------------------
GRAVITY     equ 4                     ; 0.25 px per frame, per frame
JUMP_V      equ -85                   ; -5.3 px per frame
SPEED_MIN   equ 48                    ; 3 px per frame
SPEED_MAX   equ 112                   ; 7 px per frame
SPEED_EVERY equ 16                    ; frames per speed bump
POINT_PX    equ 18                    ; one point per eighteen pixels run
DUCK_FALL   equ 3                     ; ducking in the air falls faster

ST_TITLE equ 0
ST_PLAY  equ 1
ST_DYING equ 2
ST_OVER  equ 3

MD_CLASSIC equ 0
MD_TURBO   equ 1
MD_NIGHT   equ 2
MD_ZEN     equ 3
MODE_COUNT equ 4

PO_RUN1  equ 0
PO_RUN2  equ 1
PO_JUMP  equ 2
PO_DUCK1 equ 3
PO_DUCK2 equ 4
PO_DEAD  equ 5

OB_CACTUS_S equ 0
OB_CACTUS_L equ 1
OB_BIRD     equ 2

MIX_BASE   equ 0x38                   ; tone A, B and C on, all noise off

; ---- RAM ($C000 upwards) -------------------------------------------------
ram          equ 0xc000
state        equ ram+0
pad          equ ram+1
prev         equ ram+2
frame        equ ram+3                ; two bytes, free running
blink_t      equ ram+5
mode         equ ram+6
music_on     equ ram+7
theme        equ ram+8                ; 0 day, 1 dusk, 2 night
theme_next   equ ram+9
flash_t      equ ram+10
hundreds     equ ram+11
score        equ ram+12               ; three BCD bytes: 0, 0000, 0000
hi           equ ram+15
hi_save      equ ram+18               ; four modes, three bytes each
scroll       equ ram+30               ; 0..31: the ground's pixel phase
move_acc     equ ram+31               ; two bytes of sub-pixel movement
speed        equ ram+33
speed_t      equ ram+34
dist         equ ram+35               ; two bytes
y16          equ ram+37               ; the dino's top, in sixteenths
vy16         equ ram+39               ; signed, sixteenths per frame
jumping      equ ram+41
ducking      equ ram+42
run_t        equ ram+43
pose         equ ram+44
crash_t      equ ram+45
over_t       equ ram+46
ob_wait      equ ram+47
ob_n         equ ram+48
ob           equ ram+49               ; 3 x 6
cl           equ ram+214              ; 2 x 6, clear of the obstacles
cl_acc       equ ram+77
cl_wait      equ ram+78
sfx_ptr      equ ram+79
sfx_wait     equ ram+81
rand         equ ram+89
px           equ ram+90               ; whole pixels this frame
dino_y       equ ram+91               ; the dino's top, rounded
t0           equ ram+92
t1           equ ram+93
t2           equ ram+94
t3           equ ram+95
t4           equ ram+96
t5           equ ram+97
t6           equ ram+98
t7           equ ram+99
t8           equ ram+100
t9           equ ram+101
t10          equ ram+102
t11          equ ram+103
theme_ix     equ ram+104
gnd_row      equ ram+105              ; 32 bytes: one cell row of ground
theme_now    equ ram+137              ; eight colours, by role
spr_cols     equ ram+145              ; five sprite colours
sat_buf      equ ram+150              ; 64 bytes: sixteen sprite entries
trk_a        equ ram+230              ; ptr lo, ptr hi, wait, loop lo, loop hi, channel
trk_b        equ ram+236
m_playing    equ ram+242
ram_top      equ 1024

; ==========================================================================
;  boot
; ==========================================================================
start:
        di                            ; we poll the VDP; interrupts stay off
        call vdp_setup
        call psg_init
        call init_ram
        call title_enter
main_loop:
        call wait_vblank
        call read_pad
        call music_tick
        call sfx_tick
        call dispatch
        jr main_loop

dispatch:
        ld a, (state)
        cp ST_PLAY
        jp z, tick_play
        cp ST_DYING
        jp z, tick_dying
        cp ST_OVER
        jp z, tick_over
        jp tick_title

; ---- one frame, defined by the VDP status flag --------------------------
wait_vblank:
        ld bc, 0
.wait:  in a, (VDPCTRL)
        and 0x80
        jr nz, .got
        dec bc
        ld a, b
        or c
        jr nz, .wait
.got:   ld hl, (frame)
        inc hl
        ld (frame), hl
        ret

; ---- the joystick, the keyboard, or both --------------------------------
; Joystick 1 hangs off the PSG's port A; the keyboard is the PPI matrix, and
; row 8 is the cursor keys and space (MSX Assembly Page).
read_pad:
        ld a, (pad)
        ld (prev), a
        ld a, 14
        out (PSGREG), a
        in a, (PSGDATA + 1)           ; $A2 reads the selected register
        cpl
        and 0x3f
        ld (pad), a
        ld a, 8
        out (PPIROW), a
        in a, (PPIKEY)
        cpl
        ld b, a                       ; bit 7 right, 6 down, 5 up, 4 left, 0 space
        xor a
        bit 5, b
        jr z, .noup
        or J_UP
.noup:  bit 6, b
        jr z, .nodown
        or J_DOWN
.nodown:
        bit 4, b
        jr z, .noleft
        or J_LEFT
.noleft:
        bit 7, b
        jr z, .noright
        or J_RIGHT
.noright:
        bit 0, b
        jr z, .nofire
        or J_FIRE
.nofire:
        ld b, a
        ld a, (pad)
        or b
        ld (pad), a
        xor a
        out (PPIROW), a
        ret

; A = a bit mask -> A = the mask if that bit went down this frame, else 0
pressed:
        ld b, a                       ; the bit we care about
        ld a, (prev)
        cpl
        and b                         ; it was not down a frame ago
        ld b, a
        ld a, (pad)
        and b                         ; and it is down now
        ret

; ==========================================================================
;  VDP
; ==========================================================================
vdp_setup:
        ld hl, vdp_regs
        ld c, 0
        ld b, 8
.regs:  ld a, (hl)
        out (VDPCTRL), a
        ld a, c
        or 0x80
        out (VDPCTRL), a
        inc hl
        inc c
        djnz .regs

        ld hl, 0x0000                 ; the whole 16 KB: a real VDP powers
        call vdp_setaddr              ; up with garbage in it, and the C-BIOS
        ld bc, 0x4000                 ; boot leaves its own behind
        xor a
.clr:   out (VDPDATA), a
        dec bc
        ld a, b
        or c
        ld a, 0                       ; and back to the byte we are filling with
        jr nz, .clr

        ld ix, pattern_data           ; the patterns, one 2 KB bank at a time
        ld de, 0x0000
        ld c, 3
.bank:  push bc
        push de
        push ix
        ld h, d
        ld l, e
        call vdp_setaddr
        pop ix
        ld bc, 64 * 8
.clr2:  ld a, (ix+0)
        out (VDPDATA), a
        inc ix
        dec bc
        ld a, b
        or c
        jr nz, .clr2
        pop de
        ld hl, 0x0800
        add hl, de
        ex de, hl
        pop bc
        dec c
        jr nz, .bank

        ld hl, sprite_patterns        ; and the sprites, once
        ld de, SPRPAT
        ld bc, SPRITE_SLOTS * 32
        call vram_copy
        ret

vdp_regs:
        db 0x00                       ; R0: Graphics II, 8x8 sprites
        db 0xca                       ; R1: display on, M2, 16x16 sprites
        db 0x06                       ; R2: name table $1800
        db 0x80                       ; R3: colour table $2000
        db 0x00                       ; R4: patterns $0000
        db 0x36                       ; R5: sprite attributes $1B00
        db 0x07                       ; R6: sprite patterns $3800
        db 0x01                       ; R7: black backdrop

; HL = VRAM address
vdp_setaddr:
        ld a, l
        out (VDPCTRL), a
        ld a, h
        or 0x40
        out (VDPCTRL), a
        ret

; HL = source, DE = VRAM, BC = count
vram_copy:
        push hl
        ld h, d
        ld l, e
        call vdp_setaddr
        pop hl
.next:  ld a, (hl)
        out (VDPDATA), a
        inc hl
        dec bc
        ld a, b
        or c
        jr nz, .next
        ret

; A = byte, HL = VRAM address
put_cell:
        push af
        call vdp_setaddr
        pop af
        out (VDPDATA), a
        ret

; A = row -> HL = NAME + row * 32
row_addr:
        ld l, a
        ld h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        ld de, NAME
        add hl, de
        ret

; ---- text ---------------------------------------------------------------
; A = ascii -> A = tile
char_tile:
        sub 32
        jr c, .blank
        cp 96
        jr nc, .blank
        ld e, a
        ld d, 0
        ld hl, font_map
        add hl, de
        ld a, (hl)
        ret
.blank: xor a
        ret

; HL = zero terminated string, B = column, C = row
print_at:
        push hl
        ld a, c
        call row_addr
        ld e, b
        ld d, 0
        add hl, de
        call vdp_setaddr
        pop hl
.next:  ld a, (hl)
        or a
        ret z
        push hl
        call char_tile
        out (VDPDATA), a
        pop hl
        inc hl
        jr .next

; A = digit, B = column, C = row.  The digits are the page's own 16x16 ones.
put_digit:
        push bc
        ld l, a
        ld h, 0
        add hl, hl
        add hl, hl
        ld de, TILE_DIGIT
        add hl, de
        ld a, l
        ld (t0), a                    ; the first of its four cells
        ld a, c
        call row_addr
        ld e, b
        ld d, 0
        add hl, de
        push hl
        call vdp_setaddr
        ld a, (t0)
        out (VDPDATA), a
        inc a
        out (VDPDATA), a
        pop hl
        ld de, 32                     ; one row down
        add hl, de
        call vdp_setaddr
        ld a, (t0)
        add a, 2
        out (VDPDATA), a
        inc a
        out (VDPDATA), a
        pop bc
        ret

; HL = three BCD bytes, B = column, C = row: five digits, two cells each
draw_bcd5:
        ld a, (hl)
        and 0x0f
        ld (t1), a                    ; ten thousands
        inc hl
        ld a, (hl)
        ld e, a
        and 0x0f
        ld (t2), a                    ; hundreds
        ld a, e
        rrca
        rrca
        rrca
        rrca
        and 0x0f
        ld (t3), a                    ; thousands
        inc hl
        ld a, (hl)
        ld e, a
        and 0x0f
        ld (t4), a                    ; units
        ld a, e
        rrca
        rrca
        rrca
        rrca
        and 0x0f
        ld (t5), a                    ; tens
        ld a, (t1)
        call put_digit
        ld a, b
        add a, 2
        ld b, a
        ld a, (t3)
        call put_digit
        ld a, b
        add a, 2
        ld b, a
        ld a, (t2)
        call put_digit
        ld a, b
        add a, 2
        ld b, a
        ld a, (t5)
        call put_digit
        ld a, b
        add a, 2
        ld b, a
        ld a, (t4)
        jp put_digit

; ==========================================================================
;  the PSG
; ==========================================================================
psg_set:                              ; A = register, E = value
        out (PSGREG), a
        ld a, e
        out (PSGDATA), a
        ret

psg_init:
        ld a, 15
        ld e, 0x8f                    ; port B, joystick 1: what the MSX uses
        call psg_set
        ld a, 7
        ld e, MIX_BASE
        call psg_set
        xor a
        ld e, a
        ld a, 8
        call psg_set
        ld a, 9
        call psg_set
        ld a, 10
        jp psg_set

; ==========================================================================
;  RAM
; ==========================================================================
init_ram:
        ld hl, ram
        ld de, ram + 1
        ld bc, ram_top - 1
        ld (hl), 0
        ldir
        ld a, 1
        ld (music_on), a
        ld a, SPEED_MIN
        ld (speed), a
        jp load_hi

; the high score of the current mode into `hi`
load_hi:
        call hi_ptr
        ld hl, hi
        ld bc, 3
        ldir
        ret

save_hi:
        call hi_ptr
        ex de, hl
        ld hl, hi
        ld bc, 3
        ldir
        ret

; HL = hi_save + mode * 3
hi_ptr:
        ld a, (mode)
        ld l, a
        ld h, 0
        ld e, a
        ld d, 0
        add hl, hl                    ; 2m
        add hl, de                    ; 3m
        ld de, hi_save
        add hl, de
        ret

; ---- a right shifting LFSR, period 255 ----------------------------------
random:
        ld a, (rand)
        or a
        jr nz, .ok
        ld a, 0x8d
.ok:    srl a
        jr nc, .done
        xor 0xb8
.done:  ld (rand), a
        ret

; A = 0..n-1
random_n:
        push bc
        ld c, a
        call random
        ld b, a
        xor a
.div:   cp c
        jr c, .done
        sub c
        jr .div
.done:  ld a, b                       ; keep the low nibble-ish spread
        and 0x07
        cp c
        jr c, .out
        xor a
.out:   pop bc
        ret

; ==========================================================================
;  colours and themes
; ==========================================================================
; A = 0 day, 1 dusk, 2 night.  Copies the theme's eight colours and the five
; sprite colours into RAM, then rewrites the colour table - 1536 bytes, one
; frame's work, which is why the change of day happens in a step and not a
; smooth fade.
set_theme:
        ld (theme), a
        ld l, a
        ld h, 0
        add hl, hl
        add hl, hl
        add hl, hl                    ; theme * 8
        ld de, theme_data
        add hl, de
        ld de, theme_now
        ld bc, 8
        ldir
        ld a, (theme)
        ld l, a
        ld h, 0
        ld e, a
        ld d, 0
        add hl, hl
        add hl, hl                    ; 4m
        add hl, de                    ; 5m
        ld de, sprite_colours
        add hl, de
        ld de, spr_cols
        ld bc, 5
        ldir
        call recolour
        ; the night sky: moon and stars, or the plain sky again
        ld a, (theme)
        cp 2
        jp z, draw_night
        jp clear_night

recolour:
        ld hl, COLOUR
        ld a, 3
        ld (t6), a
        ld de, role_data
.bank:  push hl
        call vdp_setaddr
        ld b, 64
.pat:   ld a, (de)                    ; the ink's role
        inc de
        push de
        ld l, a
        ld h, 0
        ld de, theme_now
        add hl, de
        ld a, (hl)
        add a, a
        add a, a
        add a, a
        add a, a
        ld (t0), a
        pop de
        ld a, (de)                    ; and the paper's
        inc de
        push de
        ld l, a
        ld h, 0
        ld de, theme_now
        add hl, de
        ld a, (hl)
        ld hl, t0
        or (hl)
        pop de
        ld c, 8                       ; Graphics II gives a pattern 8 colour
.row:   out (VDPDATA), a              ; bytes, one per pixel row
        dec c
        jr nz, .row
        djnz .pat
        pop hl
        ld bc, 0x0800
        add hl, bc
        ld a, (t6)
        dec a
        ld (t6), a
        jr nz, .bank
        ret

; rows 0..18 in the sky's colour, the bottom few in the deep one
draw_sky:
        ld b, 19
        ld c, 0
.row:   push bc
        ld a, c
        call row_addr
        call vdp_setaddr
        ld a, c
        cp HORIZON_ROW
        ld a, TILE_SKY
        jr c, .have
        ld a, TILE_SKY + 1
.have:  ld b, 32
.fill:  out (VDPDATA), a
        djnz .fill
        pop bc
        inc c
        djnz .row
        ret

; six tiles, two to a row: 85 86 / 87 88 / 89 90
draw_moon:
        ld b, 3                       ; column
        ld c, 2                       ; row
        ld a, TILE_MOON
        ld (t0), a
        ld a, c
        call row_addr
        ld a, b
        ld e, a
        ld d, 0
        add hl, de
        ld b, 3
.row:   push bc
        push hl
        call vdp_setaddr
        ld a, (t0)
        out (VDPDATA), a
        inc a
        out (VDPDATA), a
        inc a
        ld (t0), a
        pop hl
        ld de, 32
        add hl, de
        pop bc
        djnz .row
        ret

draw_night:
        call draw_moon
        ld hl, star_cells
        ld b, STAR_COUNT
.star:  push bc
        ld a, (hl)
        ld b, a
        inc hl
        ld a, (hl)
        ld c, a
        inc hl
        push hl
        ld a, TILE_STAR
        ld l, c
        ld a, c
        call row_addr
        ld a, b
        ld e, a
        ld d, 0
        add hl, de
        ld a, TILE_STAR
        call put_cell
        pop hl
        pop bc
        djnz .star
        ret

clear_night:
        ld a, TILE_SKY
        ld b, 3
        ld c, 2
        ld d, 2
        ld e, 3
        call draw_rect
        ld hl, star_cells
        ld b, STAR_COUNT
.star:  push bc
        ld a, (hl)
        ld b, a
        inc hl
        ld a, (hl)
        ld c, a
        inc hl
        push hl
        ld a, c
        call row_addr
        ld a, b
        ld e, a
        ld d, 0
        add hl, de
        ld a, TILE_SKY
        call put_cell
        pop hl
        pop bc
        djnz .star
        ret

; A = tile, B = column, C = row, D = width, E = height
draw_rect:
        ld (t0), a
        ld a, d
        ld (t1), a                    ; width
        ld a, e
        ld (t2), a                    ; height
        ld a, c                       ; row
        call row_addr
        ld a, b                       ; column
        ld e, a
        ld d, 0
        add hl, de
.rows:  push hl
        call vdp_setaddr
        ld a, (t1)
        ld b, a
        ld a, (t0)
.cols:  out (VDPDATA), a
        djnz .cols
        pop hl
        ld de, 32
        add hl, de
        ld a, (t2)
        dec a
        ld (t2), a
        jr nz, .rows
        ret

; ==========================================================================
;  the ground, and the sand under it
; ==========================================================================
; The ground is one cell row of 32 names.  Scrolling it a pixel is a matter
; of picking a different one of the sixteen phases for each cell, which is
; 32 name writes - affordable at sixty frames a second, and impossible to do
; by rewriting patterns.
draw_ground_row:
        ld hl, gnd_row
        ld a, (scroll)
        ld b, 32
.loop:  ld e, a
        add a, TILE_GROUND
        ld (hl), a
        inc hl
        ld a, e
        add a, 8
        and 15
        djnz .loop
        ld hl, NAME + GROUND_ROW * 32
        call vdp_setaddr
        ld hl, gnd_row
        ld bc, 32 * 256 + VDPDATA
        otir
        ret

fill_sand:
        ld c, SAND_ROW
.row:   ld a, c
        call row_addr
        call vdp_setaddr
        ld b, 32
        ld a, TILE_SAND
.fill:  out (VDPDATA), a
        djnz .fill
        inc c
        ld a, c
        cp 24
        jr nz, .row
        ret

; ==========================================================================
;  the scoreboard: HI and five digits, the page's own font
; ==========================================================================
clear_hud:
        xor a
        call row_addr
        call vdp_setaddr
        ld b, 64
.clr:   out (VDPDATA), a
        djnz .clr
        ret

draw_hud:
        ld hl, txt_hi
        ld b, 0
        ld c, 1
        call print_at
        ld hl, hi
        ld b, 3
        ld c, 0
        call draw_bcd5
        ld hl, score
        ld b, 21
        ld c, 0
        jp draw_bcd5

; the score alone, which is what changes
draw_score:
        ld hl, score
        ld b, 21
        ld c, 0
        jp draw_bcd5

; ==========================================================================
;  the title screen
; ==========================================================================
title_enter:
        xor a
        ld (state), a
        ld (blink_t), a
        ld a, 12
        ld (over_t), a
        call hide_sprites
        call clear_hud
        call draw_sky
        ; the title is the mode's own sky: night mode shows the night, and the
        ; moon and the stars go on after the sky or they get painted over
        ld a, (mode)
        cp MD_NIGHT
        ld a, 0
        jr nz, .day
        ld a, 2
.day:   call set_theme
        call draw_ground_row
        call fill_sand
        call draw_logo_title
        call draw_title_text
        call draw_hud
        call show_mode
        call show_music
        jp music_start

draw_logo_title:
        ld a, TILE_LOGO               ; the end screen borrows these patterns
        call pattern_vram
        ex de, hl
        ld hl, logo_data
        ld bc, LOGO_LETTERS * 4 * 8
        call vram_copy
        ld hl, logo_tiles
        ld a, 5                       ; column
        ld b, LOGO_LETTERS
        ld c, 2                       ; row
        jp draw_big

draw_title_text:
        ld hl, txt_press
        ld b, 8
        ld c, 12
        call print_at
        ld hl, txt_by1
        ld b, 3
        ld c, 21
        call print_at
        ld hl, txt_by2
        ld b, 6
        ld c, 22
        call print_at
        ret

show_mode:
        ld hl, txt_classic
        ld a, (mode)
        or a
        jr z, .have
        ld hl, txt_turbo
        cp MD_TURBO
        jr z, .have
        ld hl, txt_night
        cp MD_NIGHT
        jr z, .have
        ld hl, txt_zen
.have:  ld b, 7
        ld c, 14
        jp print_at

show_music:
        ld hl, txt_music_on
        ld a, (music_on)
        or a
        jr nz, .have
        ld hl, txt_music_off
.have:  ld b, 7
        ld c, 16
        jp print_at

tick_title:
        ; the trigger, blinking, and the dino's idle animation
        ld a, (over_t)                ; a moment before the keys count, or the
        or a                          ; trigger that left the end card would
        jr z, .keys_on                ; start a game from here
        dec a
        ld (over_t), a
.keys_on:
        ld a, (blink_t)
        inc a
        ld (blink_t), a
        and 0x3f
        cp 32
        jr nc, .blank
        ld hl, txt_press
        ld b, 8
        ld c, 12
        call print_at
        jr .after
.blank: ld a, 13
        call row_addr
        ld de, 8
        add hl, de
        call vdp_setaddr
        ld b, 13
        xor a
.bl:    out (VDPDATA), a
        djnz .bl
.after:
        ld a, (blink_t)
        and 0x20
        jr z, .idle1
        ld a, SPR_DINO_RUN1
        jr .idle
.idle1: ld a, SPR_DINO_RUN2
.idle:  ld (t0), a
        call hide_sprites
        ld a, 0
        ld (t1), a                    ; the first entry
        ld a, DINO_X
        ld (t2), a
        xor a
        ld (t3), a
        ld a, GROUND_Y - DINO_H
        ld (t5), a
        ld a, (spr_cols)
        ld (t4), a
        call sat_group              ; the dino, four entries
        call push_sprites
        ld a, (over_t)
        or a
        jr nz, .no_fire
        ld a, J_FIRE
        call pressed
        or a
        jp nz, start_game
.no_fire:
        ld a, J_LEFT
        call pressed
        or a
        call nz, mode_prev
        ld a, J_RIGHT
        call pressed
        or a
        call nz, mode_next
        ld a, J_B
        call pressed
        or a
        ret z
        call music_toggle
        ret

mode_prev:
        ld a, (mode)
        dec a
        cp 0xff
        jr nz, .set
        ld a, MODE_COUNT - 1
.set:   ld (mode), a
        call load_hi
        jp title_enter                  ; a new mode has its own sky

mode_next:
        ld a, (mode)
        inc a
        cp MODE_COUNT
        jr nz, .set
        xor a
.set:   ld (mode), a
        call load_hi
        jp title_enter

music_toggle:
        ld a, (music_on)
        xor 1
        ld (music_on), a
        or a
        jr nz, .on
        call music_stop
        jp show_music
.on:    call music_start
        jp show_music

; ==========================================================================
;  a game
; ==========================================================================
start_game:
        ld a, ST_PLAY
        ld (state), a
        xor a
        ld (score), a
        ld (score + 1), a
        ld (score + 2), a
        ld (hundreds), a
        ld (flash_t), a
        ld (dist), a
        ld (dist + 1), a
        ld (move_acc), a
        ld (move_acc + 1), a
        ld (scroll), a
        ld (ob_n), a
        ld (ob_wait), a
        ld (cl_wait), a
        ld (cl_acc), a
        ld (jumping), a
        ld (ducking), a
        ld (crash_t), a
        ld (over_t), a
        ld (pose), a
        ld (run_t), a
        ld (speed_t), a
        ld (theme_ix), a
        ld ix, ob
        ld b, MAX_OB
        ld de, OB_SIZE
        call clear_slots
        ld ix, cl
        ld b, MAX_CLOUD
        ld de, CL_SIZE
        call clear_slots
        ld hl, (GROUND_Y - DINO_H) * 16
        ld (y16), hl
        ld hl, 0
        ld (vy16), hl
        ld a, 0
        ld (dino_y), a
        call mode_speed
        call clear_hud
        call draw_sky
        ld a, (theme_ix)
        ld e, a
        ld d, 0
        ld hl, theme_seq
        add hl, de
        ld a, (hl)
        call set_theme
        call draw_ground_row
        call fill_sand
        call draw_hud
        jp music_start

; IX = the first slot, B = how many, DE = the stride
clear_slots:
        ld (ix+0), 0
        add ix, de
        djnz clear_slots
        ret

mode_speed:
        ld a, (mode)
        ld e, a
        ld d, 0
        ld hl, mode_start
        add hl, de
        ld a, (hl)
        ld (speed), a
        ret

mode_max:
        ld a, (mode)
        ld e, a
        ld d, 0
        ld hl, mode_maxes
        add hl, de
        ld a, (hl)
        ret

; ==========================================================================
;  the dino
; ==========================================================================
tick_play:
        call dino_tick
        call move_tick
        call ob_tick
        call cl_tick
        call collide
        call add_distance
        call set_sprites
        call hud_tick
        call speed_tick
        ret

; ---- gravity, jumping, ducking -----------------------------------------
dino_tick:
        ld a, (pad)
        and J_DOWN
        jr z, .stand
        ld a, (jumping)
        or a
        jr nz, .fastfall
        ld a, 1
        ld (ducking), a
        jr .jump
.fastfall:
        ld a, 1
        ld (ducking), a
        ld hl, (vy16)                 ; the browser game's speedDropCoefficient
        ld de, GRAVITY * DUCK_FALL
        add hl, de
        ld (vy16), hl
        jr .jump
.stand: xor a
        ld (ducking), a
.jump:
        ld a, (pad)
        and (J_UP | J_FIRE)
        jr z, .nograv
        ld a, (jumping)
        or a
        jr nz, .nograv
        ld a, 1
        ld (jumping), a
        ld hl, JUMP_V
        ld (vy16), hl
        ld hl, sfx_jump
        call sfx_play
.nograv:
        ld a, (jumping)
        or a
        jr z, .onfloor
        ld hl, (vy16)
        ld de, GRAVITY
        add hl, de
        ld (vy16), hl
        ld hl, (y16)
        ld de, (vy16)
        add hl, de
        ld (y16), hl
        ld de, (GROUND_Y - DINO_H) * 16
        or a
        sbc hl, de
        jr c, .posed                  ; still up there
        ld hl, (GROUND_Y - DINO_H) * 16
        ld (y16), hl
        ld hl, 0
        ld (vy16), hl
        xor a
        ld (jumping), a
        jr .posed
.onfloor:
        ld hl, (GROUND_Y - DINO_H) * 16
        ld (y16), hl
        ld hl, 0
        ld (vy16), hl
.posed:
        ld hl, (y16)
        srl h
        rr l
        srl h
        rr l
        srl h
        rr l
        srl h
        rr l
        ld a, l
        ld (dino_y), a
        ld a, (jumping)
        or a
        jr nz, .air
        ld a, (ducking)
        or a
        jr nz, .duck
        ld hl, (frame)
        ld a, l
        and 0x04
        ld a, PO_RUN1
        jr z, .set
        ld a, PO_RUN2
        jr .set
.air:   ld a, PO_JUMP
        jr .set
.duck:  ld hl, (frame)
        ld a, l
        and 0x08
        ld a, PO_DUCK1
        jr z, .set
        ld a, PO_DUCK2
.set:   ld (pose), a
        ret

; ---- speed, and the pixels everything moved this frame ------------------
speed_tick:
        ld a, (mode)
        cp MD_ZEN
        ret z
        ld a, (speed_t)
        inc a
        cp SPEED_EVERY
        jr c, .keep
        xor a
        ld (speed_t), a
        call mode_max
        ld b, a
        ld a, (speed)
        cp b
        ret nc
        inc a
        ld (speed), a
        ret
.keep:  ld (speed_t), a
        ret

move_tick:
        ld hl, (move_acc)
        ld a, (speed)
        ld e, a
        ld d, 0
        add hl, de
        ld a, l
        and 0x0f
        ld (t0), a
        srl h
        rr l
        srl h
        rr l
        srl h
        rr l
        srl h
        rr l
        ld a, l
        ld (px), a
        ld a, (t0)
        ld l, a
        ld h, 0
        ld (move_acc), hl
        ld a, (px)
        or a
        ret z
        ; the ground
        ld a, (scroll)
        ld b, a
        ld a, (px)
        add a, b
        and 31
        ld (scroll), a
        call draw_ground_row
        ; and everything that walks on it
        ld ix, ob
        ld b, MAX_OB
.next:  ld a, (ix+OB_ON)
        or a
        jr z, .skip
        ld l, (ix+OB_XL)
        ld h, (ix+OB_XH)
        ld a, (px)
        ld e, a
        ld d, 0
        or a
        sbc hl, de
        ld (ix+OB_XL), l
        ld (ix+OB_XH), h
        ; gone off the left?
        ld a, h
        cp 0xff
        jr nz, .skip
        ld a, l
        cp 0xe0
        jr nc, .skip
        ld (ix+OB_ON), 0
        ld a, (ob_n)
        dec a
        ld (ob_n), a
.skip:  ld de, OB_SIZE
        add ix, de
        djnz .next
        ret

; ==========================================================================
;  obstacles
; ==========================================================================
; Spawn when the right hand side of the screen has room, in groups of one to
; three, and sometimes a bird instead.  x is a signed 16 bit pixel position: a
; group starts at 248 and the slots to its right carry on past 255, which is
; why it has a high byte at all.
ob_tick:
        ld a, (ob_n)
        cp MAX_OB
        ret nc
        ld a, (ob_n)
        or a
        jr z, .spawn                  ; nothing on screen: fill the right edge
        ld a, (speed)
        srl a
        add a, 90                     ; the gap grows with the speed
        ld b, a
        xor a
        sub b                         ; 256 - gap
        ld b, a
        call ob_max_x                 ; HL = the rightmost obstacle's x
        ld a, h
        or a
        ret nz                        ; still off the right edge
        ld a, l
        cp b
        ret nc                        ; too close to where the next one goes
.spawn:
        ld a, (mode)
        ld e, a
        ld d, 0
        ld hl, mode_birds
        add hl, de
        ld a, (hundreds)
        cp (hl)
        jr c, .cacti
        call random
        cp 40
        jr nc, .cacti
        jp spawn_bird
.cacti:
        call random
        and 0x03
        jr nz, .ones
        ld a, 2
.ones:  inc a                         ; one to three
        ld (t0), a                    ; how many left to place
        call random
        and 0x01
        ld (t1), a                    ; 0 small, 1 large
        or a
        ld a, CACTUS_S_W + 1
        jr z, .space
        ld a, CACTUS_L_W + 1
.space: ld (t2), a                    ; the gap inside the group
        xor a
        ld (t3), a                    ; the slot to try
.fill:  ld a, (t3)
        cp MAX_OB
        jr nc, .done
        call ob_slot
        ld a, (hl)
        or a
        jr nz, .next
        ld (hl), 1                    ; on
        push hl
        ld hl, 248
        ld b, 0
        ld a, (t2)
        ld c, a                       ; the gap inside the group
        ld a, (t3)
        or a
        jr z, .xdone
        ld e, a
.xloop: add hl, bc
        dec e
        jr nz, .xloop
.xdone: pop de
        ex de, hl                     ; HL = the record, DE = x
        inc hl
        ld (hl), e
        inc hl
        ld (hl), d
        inc hl
        ld a, (t1)
        or a
        ld a, GROUND_Y - CACTUS_S_H
        jr z, .haves
        ld a, GROUND_Y - CACTUS_L_H
.haves: ld (hl), a                    ; y
        inc hl
        ld a, (t1)
        ld (hl), a                    ; type
        inc hl
        ld (hl), 0                    ; frame
        ld a, (ob_n)
        inc a
        ld (ob_n), a
.next:  ld a, (t3)
        inc a
        ld (t3), a
        ld a, (t0)
        dec a
        ld (t0), a
        jr nz, .fill
.done:  ret

; A = a slot number -> HL = ob + slot * OB_SIZE
ob_slot:
        ld l, a
        ld h, 0
        ld e, a
        ld d, 0
        add hl, hl
        add hl, de
        add hl, hl
        ld de, ob
        add hl, de
        ret

; HL = the rightmost obstacle's left edge (0 if there is none)
ob_max_x:
        ld hl, 0
        ld ix, ob
        ld b, MAX_OB
.next:  ld a, (ix+OB_ON)
        or a
        jr z, .skip
        ld a, (ix+OB_XH)
        ld e, a
        ld a, (ix+OB_XL)
        ld d, a
        ; if DE > HL then HL = DE
        ld a, e
        cp h
        jr c, .skip
        jr nz, .take
        ld a, d
        cp l
        jr c, .skip
.take:  ld h, e
        ld l, d
.skip:  ld de, OB_SIZE
        add ix, de
        djnz .next
        ret

spawn_bird:
        ; the first free slot gets a bird, at one of three heights
        ld ix, ob
        ld b, MAX_OB
.next:  ld a, (ix+OB_ON)
        or a
        jr z, .found
        ld de, OB_SIZE
        add ix, de
        djnz .next
        ret
.found: ld (ix+OB_ON), 1
        ld (ix+OB_XL), 248
        ld (ix+OB_XH), 0
        ld a, OB_BIRD
        ld (ix+OB_TYPE), a
        ld (ix+OB_FRAME), 0
        call random
        and 0x03
        cp 3
        jr c, .height
        ld a, 1
.height:
        ld e, a
        ld d, 0
        ld hl, bird_heights
        add hl, de
        ld a, (hl)
        ld (ix+OB_Y), a
        ld a, (ob_n)
        inc a
        ld (ob_n), a
        ret


; ==========================================================================
;  clouds: two of them, drifting slowly, drawn into the sky as cells
; ==========================================================================
cl_tick:
        ld a, (cl_acc)
        inc a
        and 0x03
        ld (cl_acc), a
        jr nz, .move
        ld a, (cl_wait)
        inc a
        ld (cl_wait), a
        cp 90
        jr c, .move
        xor a
        ld (cl_wait), a
        call cloud_spawn
.move:  ld a, (cl_acc)
        or a
        ret nz
        ld ix, cl
        ld b, MAX_CLOUD
.next:  push bc
        ld a, (ix+CL_ON)
        or a
        jr z, .skip
        call cloud_erase
        ld l, (ix+CL_XL)
        ld h, (ix+CL_XH)
        dec hl
        ld (ix+CL_XL), l
        ld (ix+CL_XH), h
        ld a, h
        or a
        jr nz, .off
        call cloud_draw
        jr .skip
.off:   ld (ix+CL_ON), 0
.skip:  pop bc
        ld de, CL_SIZE
        add ix, de
        djnz .next
        ret

cloud_spawn:
        ld ix, cl
        ld b, MAX_CLOUD
        ld c, 0
.next:  ld a, (ix+CL_ON)
        or a
        jr z, .found
        inc c
        ld de, CL_SIZE
        add ix, de
        djnz .next
        ret
.found: ld (ix+CL_ON), 1
        ld (ix+CL_XL), 248
        ld (ix+CL_XH), 0
        ld (ix+CL_SET), c
        call random
        and 0x01
        ld a, 40
        jr z, .y
        ld a, 64
.y:     ld (ix+CL_Y), a
        ld (ix+CL_PH), 0
        jp cloud_draw

; IX = a cloud: poke its four patterns with the phase it is at, then point
; four cells at them
cloud_draw:
        ld a, (ix+CL_XL)
        and 0x07
        ld (ix+CL_PH), a
        ld a, (ix+CL_SET)
        add a, a
        add a, a
        ld b, a
        ld a, TILE_CLOUD
        add a, b
        ld (t0), a                    ; the first tile of this cloud's set
        sub 64                        ; every cloud tile is in the second bank
        ld l, a
        ld h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        ld de, 0x0800
        add hl, de
        call vdp_setaddr
        ld a, (ix+CL_PH)
        add a, a
        add a, a
        add a, a
        add a, a
        add a, a                      ; * 32
        ld e, a
        ld d, 0
        ld hl, cloud_phases
        add hl, de
        ld b, 32
.pat:   ld a, (hl)
        out (VDPDATA), a
        inc hl
        djnz .pat
        ; and the four cells
        ld a, (ix+CL_Y)
        srl a
        srl a
        srl a
        call row_addr
        ld a, (ix+CL_XL)
        srl a
        srl a
        srl a
        ld e, a
        ld d, 0
        add hl, de
        call vdp_setaddr
        ld a, (t0)
        ld b, 4
.cell:  out (VDPDATA), a
        inc a
        djnz .cell
        ret

cloud_erase:
        ld a, (ix+CL_Y)
        srl a
        srl a
        srl a
        call row_addr
        ld a, (ix+CL_XL)
        srl a
        srl a
        srl a
        ld e, a
        ld d, 0
        add hl, de
        call vdp_setaddr
        ld a, TILE_SKY
        ld b, 4
.cell:  out (VDPDATA), a
        djnz .cell
        ret

; ==========================================================================
;  the sprite attribute table
; ==========================================================================
; A = entry (0..15), B = y, C = x, D = pattern, E = colour
sat_entry:
        push de
        ld l, a
        ld h, 0
        add hl, hl
        add hl, hl
        ld de, sat_buf
        add hl, de
        ld (hl), b
        inc hl
        ld (hl), c
        inc hl
        pop de
        ld (hl), d
        inc hl
        ld (hl), e
        ret

; HL = x as a signed pixel position, E = colour ->
;   A = the x byte for the table, E = the colour with the early clock if it
;   needs one, carry set if the sprite is off the screen altogether
sat_x:
        ld a, h
        cp 0xff
        jr z, .neg
        or a
        jr nz, .hide
        ld a, l
        cp 32
        jr c, .early
        or a
        ret
.neg:   ld a, l
        cp 0xe0
        jr nc, .hide
.early: add a, 32
        ld (t8), a
        ld a, e
        or 0x80
        ld e, a
        ld a, (t8)
        or a
        ret
.hide:  scf
        ret

; A = entry, HL = x, y in (t5), pattern in (t6), colour in E
sat_one:
        ld (t7), a
        call sat_x
        jr c, .hide
        ld c, a
        ld a, (t5)
        ld b, a
        ld a, (t6)
        ld d, a
        ld a, (t7)
        jp sat_entry
.hide:  ld a, (t7)
        ld b, 0xd1
        ld c, 0
        ld d, 0
        ld e, 0
        jp sat_entry

; HL = t2/t3 (x as a signed 16 bit number)
sat_x_from_t:
        ld a, (t2)
        ld l, a
        ld a, (t3)
        ld h, a
        ret

; two sprites side by side: t0 base slot, t1 entry, t2/t3 x, t4 colour, t5 y
sat_side:
        ld a, (t0)                    ; a slot number: four patterns a slot
        add a, a
        add a, a
        ld (t6), a
        call sat_x_from_t
        ld a, (t4)
        ld e, a
        ld a, (t1)
        call sat_one
        ld a, (t6)
        add a, 4                      ; the next quarter of the picture
        ld (t6), a
        call sat_x_from_t
        ld de, 16                     ; the next quarter is sixteen pixels over
        add hl, de
        ld a, (t4)
        ld e, a
        ld a, (t1)
        inc a
        jp sat_one

; two sprites stacked: the same, one above the other
sat_down:
        ld a, (t0)                    ; a slot number: four patterns a slot
        add a, a
        add a, a
        ld (t6), a
        call sat_x_from_t
        ld a, (t4)
        ld e, a
        ld a, (t1)
        call sat_one
        ld a, (t6)
        add a, 4                      ; the next quarter of the picture
        ld (t6), a
        ld a, (t5)
        add a, 16
        ld (t5), a
        call sat_x_from_t
        ld a, (t4)
        ld e, a
        ld a, (t1)
        inc a
        jp sat_one

; a 2x2 block of sprites: t0 base slot, t1 entry, t2/t3 x, t4 colour, t5 y
sat_group:
        ld a, (t0)                    ; a slot number: four patterns a slot
        add a, a
        add a, a
        ld (t6), a
        call sat_x_from_t
        ld a, (t4)
        ld e, a
        ld a, (t1)
        call sat_one
        ld a, (t6)
        add a, 4                      ; the next quarter of the picture
        ld (t6), a
        call sat_x_from_t
        ld de, 16                     ; the next quarter is sixteen pixels over
        add hl, de
        ld a, (t4)
        ld e, a
        ld a, (t1)
        inc a
        call sat_one
        ld a, (t6)
        add a, 4                      ; the next quarter of the picture
        ld (t6), a
        ld a, (t5)
        add a, 16
        ld (t5), a
        call sat_x_from_t
        ld a, (t4)
        ld e, a
        ld a, (t1)
        add a, 2
        call sat_one
        ld a, (t6)
        add a, 4                      ; the next quarter of the picture
        ld (t6), a
        call sat_x_from_t
        ld de, 16                     ; the next quarter is sixteen pixels over
        add hl, de
        ld a, (t4)
        ld e, a
        ld a, (t1)
        add a, 3
        jp sat_one

hide_sprites:
        ld hl, sat_buf
        ld b, 16
.ent:   ld (hl), 0xd1
        inc hl
        ld (hl), 0
        inc hl
        ld (hl), 0
        inc hl
        ld (hl), 0
        inc hl
        djnz .ent
        ret

push_sprites:
        ld hl, sat_buf
        ld de, SAT
        ld bc, 64
        jp vram_copy

; ==========================================================================
;  the dino and the obstacles, as sprites
; ==========================================================================
set_sprites:
        call hide_sprites
        call dino_sprites
        call ob_draw
        jp push_sprites

dino_sprites:
        ld a, (pose)
        ld e, a
        ld d, 0
        ld hl, pose_base
        add hl, de
        ld a, (hl)
        ld (t0), a
        ld a, DINO_X
        ld (t2), a
        xor a
        ld (t3), a
        ld a, (dino_y)
        ld (t5), a
        ld a, (spr_cols)
        ld (t4), a
        ld a, (pose)
        cp PO_DEAD
        jr nz, .go
        ld a, (spr_cols + 4)
        ld (t4), a
.go:    xor a
        ld (t1), a
        ld a, (pose)
        cp PO_DUCK1
        jr z, .duck
        cp PO_DUCK2
        jr z, .duck
        jp sat_group
.duck:  jp sat_side

ob_draw:
        ld ix, ob
        ld b, MAX_OB
        ld c, 4                       ; entries 0..3 are the dino
.next:  push bc
        ld a, (ix+OB_ON)
        or a
        jr z, .skip
        ld a, c
        ld (t1), a
        ld a, (ix+OB_XL)
        ld (t2), a
        ld a, (ix+OB_XH)
        ld (t3), a
        ld a, (ix+OB_Y)
        ld (t5), a
        ld a, (ix+OB_TYPE)
        cp OB_BIRD
        jr z, .bird
        cp OB_CACTUS_S
        ld a, SPR_CACTUS_S
        jr z, .small
        ld a, SPR_CACTUS_L
.small: ld (t0), a
        ld a, (spr_cols + 1)
        ld (t4), a
        call sat_down
        jr .skip
.bird:  ld a, (ix+OB_FRAME)
        or a
        ld a, SPR_BIRD_UP
        jr z, .flap
        ld a, SPR_BIRD_DOWN
.flap:  ld (t0), a
        ld a, (spr_cols + 3)
        ld (t4), a
        call sat_group
.skip:  pop bc
        ld de, OB_SIZE
        add ix, de
        ld a, c
        add a, 4
        ld c, a
        djnz .next
        ret

; ==========================================================================
;  collisions
; ==========================================================================
collide:
        ld a, 26
        ld (t0), a
        ld a, 40
        ld (t1), a
        ld a, (dino_y)
        add a, 3
        ld (t2), a
        ld a, (dino_y)
        add a, 20
        ld (t3), a
        ld a, (ducking)
        or a
        jr z, .go
        ld a, 46
        ld (t1), a
        ld a, (dino_y)
        add a, 4
        ld (t2), a
        ld a, (dino_y)
        add a, 14
        ld (t3), a
.go:    ld ix, ob
        ld b, MAX_OB
.next:  push bc
        ld a, (ix+OB_ON)
        or a
        jr z, .skip
        ld a, (ix+OB_XH)
        or a
        jr nz, .skip                  ; off the right edge, or long gone
        ld a, (ix+OB_TYPE)
        ld l, a
        ld h, 0
        add hl, hl
        add hl, hl
        ld de, ob_box
        add hl, de
        ld a, (ix+OB_XL)
        add a, (hl)                   ; x + the box's left inset
        ld (t4), a
        inc hl
        ld a, (ix+OB_Y)
        add a, (hl)                   ; y + the top inset
        ld (t5), a
        inc hl
        ld a, (hl)
        ld (t6), a                    ; width
        inc hl
        ld a, (hl)
        ld (t7), a                    ; height
        ; x: ob_l < 40 and ob_l + w > 26
        ld a, (t4)
        cp 40
        jr nc, .skip
        add a, 0
        ld e, a
        ld a, (t6)
        add a, e
        cp 26
        jr c, .skip
        jr z, .skip
        ; y: ob_t < dino_b and ob_t + h > dino_t
        ld a, (t3)
        ld e, a
        ld a, (t5)
        cp e
        jr nc, .skip
        ld a, (t5)
        add a, (t7)
        ld d, a                       ; the obstacle's bottom
        ld a, (t2)
        ld e, a
        ld a, d
        cp e
        jr c, .skip
        jr z, .skip
        ; hit
        pop bc
        jp crash
.skip:  pop bc
        ld de, OB_SIZE
        add ix, de
        djnz .next
        ret

; ==========================================================================
;  dying, and the end of the game
; ==========================================================================
crash:
        ld a, ST_DYING
        ld (state), a
        ld a, 40
        ld (crash_t), a
        ld a, PO_DEAD
        ld (pose), a
        ld hl, 0
        ld (vy16), hl
        xor a
        ld (jumping), a
        ld hl, sfx_hit
        call sfx_play
        call music_stop
        ; did it beat the high score?
        ld a, (hi)
        ld b, a
        ld a, (score)
        cp b
        jr c, .done
        jr nz, .better
        ld a, (hi + 1)
        ld b, a
        ld a, (score + 1)
        cp b
        jr c, .done
        jr nz, .better
        ld a, (hi + 2)
        ld b, a
        ld a, (score + 2)
        cp b
        jr c, .done
        jr z, .done
.better:
        ld hl, score
        ld de, hi
        ld bc, 3
        ldir
        call save_hi
.done:  ret

tick_dying:
        call set_sprites
        ld a, (crash_t)
        or a
        jr z, .over
        dec a
        ld (crash_t), a
        ret
.over:  jp over_enter

over_enter:
        ld a, ST_OVER
        ld (state), a
        xor a
        ld (over_t), a
        ld a, TILE_LOGO
        call pattern_vram
        ex de, hl
        ld hl, over_data
        ld bc, OVER_LETTERS * 4 * 8
        call vram_copy
        call hide_sprites
        call push_sprites
        ld hl, over_tiles
        ld a, 7
        ld b, OVER_LETTERS
        ld c, 5
        call draw_big
        ld hl, txt_score_is
        ld b, 9
        ld c, 9
        call print_at
        ld hl, score
        ld b, 11
        ld c, 10
        call draw_bcd5
        ld hl, txt_hi
        ld b, 9
        ld c, 13
        call print_at
        ld hl, hi
        ld b, 11
        ld c, 13
        call draw_bcd5
        ret

tick_over:
        ld a, (over_t)
        inc a
        ld (over_t), a
        cp 40
        ret c                         ; a moment before the trigger works
        and 0x1f
        cp 16
        jr nc, .blank
        ld hl, txt_press
        ld b, 8
        ld c, 18
        call print_at
        jr .keys
.blank: ld a, 18
        call row_addr
        ld de, 8
        add hl, de
        call vdp_setaddr
        ld b, 13
        xor a
.bl:    out (VDPDATA), a
        djnz .bl
.keys:  ld a, J_FIRE
        call pressed
        or a
        jp nz, title_enter
        ret

; ==========================================================================
;  the scoreboard
; ==========================================================================
add_distance:
        ld hl, (dist)
        ld a, (speed)
        ld e, a
        ld d, 0
        add hl, de
        ld de, POINT_PX * 16
        or a
        sbc hl, de
        jr c, .keep
        ld (dist), hl
        jp add_point
.keep:  add hl, de
        ld (dist), hl
        ret

add_point:
        ld hl, score + 2
        ld a, (hl)
        add a, 1
        daa
        ld (hl), a
        ret nc
        dec hl
        ld a, (hl)
        add a, 1
        daa
        ld (hl), a
        jr nc, .hundred
        dec hl
        ld a, (hl)
        add a, 1
        daa
        ld (hl), a
.hundred:
        ld a, (hundreds)
        inc a
        ld (hundreds), a
        ld a, 24
        ld (flash_t), a
        ld hl, sfx_point
        call sfx_play
        ; in the classic mode the sky turns over now and then
        ld a, (mode)
        or a
        ret nz
        ld a, (hundreds)
        and 0x03
        ret nz
        jp next_theme

next_theme:
        ld a, (theme_ix)
        inc a
        cp 4
        jr nz, .ok
        xor a
.ok:    ld (theme_ix), a
        ld e, a
        ld d, 0
        ld hl, theme_seq
        add hl, de
        ld a, (hl)
        jp set_theme

hud_tick:
        ld a, (flash_t)
        or a
        jr z, .draw
        dec a
        ld (flash_t), a
        and 0x04
        jr z, .blank
        jp draw_score
.blank: call blank_score
        ret
.draw:  jp draw_score

blank_score:
        ld a, 0
        call row_addr
        ld de, 21
        add hl, de
        call vdp_setaddr
        ld b, 10
        xor a
.row0:  out (VDPDATA), a
        djnz .row0
        ld a, 1
        call row_addr
        ld de, 21
        add hl, de
        call vdp_setaddr
        ld b, 10
.row1:  out (VDPDATA), a
        djnz .row1
        ret

; ==========================================================================
;  the music: two tracks, three bytes an event, on channels A and B
; ==========================================================================
music_start:
        ld a, (music_on)
        or a
        ret z
        ld hl, music_data
        ld e, (hl)
        inc hl
        ld d, (hl)
        inc hl
        ld (trk_a), de                ; where track A starts
        ld (trk_a + 3), de            ; and where it loops to
        ld e, (hl)
        inc hl
        ld d, (hl)
        inc hl
        ld (trk_b), de
        ld (trk_b + 3), de
        xor a
        ld (trk_a + 2), a
        ld (trk_b + 2), a
        ld a, 0
        ld (trk_a + 5), a             ; channel A
        ld a, 1
        ld (trk_b + 5), a             ; channel B
        ld a, 1
        ld (m_playing), a
        ld a, 7
        ld e, MIX_BASE
        jp psg_set

music_stop:
        xor a
        ld (m_playing), a
        ld a, 8
        ld e, 0
        call psg_set
        ld a, 9
        ld e, 0
        jp psg_set

music_tick:
        ld a, (m_playing)
        or a
        ret z
        ld ix, trk_a
        call track_tick
        ld ix, trk_b
        jp track_tick

; IX = one track: ptr lo, ptr hi, wait, loop lo, loop hi, channel
track_tick:
        ld a, (ix+2)
        or a
        jr z, .fetch
        dec (ix+2)
        ret
.fetch: ld l, (ix+0)
        ld h, (ix+1)
.again: ld a, (hl)
        inc hl
        cp 0xff
        jr nz, .note
        ld l, (ix+3)
        ld h, (ix+4)
        jr .again
.note:  ld (t0), a                    ; note
        ld a, (hl)
        inc hl
        ld (t1), a                    ; length in frames
        ld a, (hl)
        inc hl
        ld (t2), a                    ; volume
        ld (ix+0), l
        ld (ix+1), h
        ld a, (t1)
        or a
        jr nz, .nowait
        ld a, 1
.nowait:
        dec a
        ld (ix+2), a
        ld a, (ix+5)
        add a, a                      ; the channel's register pair
        ld (t3), a
        ld a, (t0)
        or a
        jr z, .rest
        dec a
        ld l, a
        ld h, 0
        add hl, hl
        ld de, note_table
        add hl, de
        ld e, (hl)
        inc hl
        ld d, (hl)                    ; DE = the period
        ld a, (t3)
        out (PSGREG), a
        ld a, e
        out (PSGDATA), a
        ld a, (t3)
        inc a
        out (PSGREG), a
        ld a, d
        out (PSGDATA), a
        jr .vol
.rest:  ld a, (t3)
        out (PSGREG), a
        xor a
        out (PSGDATA), a
        ld a, (t3)
        inc a
        out (PSGREG), a
        xor a
        out (PSGDATA), a
.vol:   ld a, (ix+5)
        add a, 8
        out (PSGREG), a
        ld a, (t2)
        or a
        jr nz, .setvol
        xor a
.setvol:
        out (PSGDATA), a
        ret

; ==========================================================================
;  the sounds: the browser page's three, measured and re-drawn for the PSG
; ==========================================================================
; A script is (frames, how many register writes, register, value, ...) with a
; zero to end it.  All of it goes through channel C, which the music leaves
; alone - the melody and the bass are on A and B - so a jump never cuts the
; tune.
sfx_play:
        ld (sfx_ptr), hl
        xor a
        ld (sfx_wait), a
        ret

sfx_tick:
        ld hl, (sfx_ptr)
        ld a, h
        or l
        ret z
        ld a, (sfx_wait)
        or a
        jr z, .step
        dec a
        ld (sfx_wait), a
        ret
.step:  ld a, (hl)
        or a
        jr z, .end
        dec a
        ld (sfx_wait), a
        inc hl
        ld b, (hl)
        inc hl
        ld a, b
        or a
        jr z, .next
.pairs: ld a, (hl)
        inc hl
        out (PSGREG), a
        ld a, (hl)
        inc hl
        out (PSGDATA), a
        djnz .pairs
.next:  ld (sfx_ptr), hl
        ret
.end:   ld hl, 0
        ld (sfx_ptr), hl
        ld a, 10
        ld e, 0
        call psg_set
        ld a, 7
        ld e, MIX_BASE
        jp psg_set

; ==========================================================================
;  the big letters: HL = four tiles a letter, A = column, B = letters,
;  C = row
; ==========================================================================
draw_big:
        ld (t4), a
        ld a, b
        ld (t5), a
        ld a, c
        ld (t6), a
        push hl                       ; the table, for the second row
        call row_addr
        ld a, (t4)
        ld e, a
        ld d, 0
        add hl, de
        call vdp_setaddr
        pop ix
        push ix
        ld a, (t5)
        ld b, a
.tl:    ld a, (ix+0)
        out (VDPDATA), a
        ld a, (ix+1)
        out (VDPDATA), a
        ld de, 4
        add ix, de
        djnz .tl
        pop ix
        ld a, (t6)
        inc a
        call row_addr
        ld a, (t4)
        ld e, a
        ld d, 0
        add hl, de
        call vdp_setaddr
        ld a, (t5)
        ld b, a
.bl:    ld a, (ix+2)
        out (VDPDATA), a
        ld a, (ix+3)
        out (VDPDATA), a
        ld de, 4
        add ix, de
        djnz .bl
        ret

; A = a tile -> HL = the VRAM address of its pattern and its colour
pattern_vram:
        push af
        and 0x3f
        ld l, a
        ld h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        ld (t9), hl
        pop af
        and 0xc0
        rrca
        rrca
        rrca
        rrca
        rrca
        rrca
        ld l, a
        ld h, 0
        add hl, hl
        ld de, bank_off
        add hl, de
        ld e, (hl)
        inc hl
        ld d, (hl)
        ld hl, (t9)
        add hl, de
        ret

bank_off:   defw 0x0000, 0x0800, 0x1000

; ==========================================================================
;  the data
; ==========================================================================
txt_hi:         defb "HI", 0
txt_press:      defb "PRESS TRIGGER", 0
txt_score_is:   defb "SCORE", 0
txt_classic:    defb "CLASSIC", 0
txt_turbo:      defb "TURBO  ", 0
txt_night:      defb "NIGHT  ", 0
txt_zen:        defb "ZEN    ", 0
txt_music_on:   defb "MUSIC ON ", 0
txt_music_off:  defb "MUSIC OFF ", 0
txt_by1:        defb "THE CHROME OFFLINE DINO", 0
txt_by2:        defb "PORTED TO THE MSX1", 0

; (column, row) of the stars that come out at night
star_cells:     defb 4,6, 11,7, 20,1, 27,8, 15,5, 8,9, 30,4, 2,7
STAR_COUNT      equ 8

; the sky goes day, dusk, night, dusk, day ...
theme_seq:      defb 0, 1, 2, 1

pose_base:      defb SPR_DINO_RUN1, SPR_DINO_RUN2, SPR_DINO_JUMP
                defb SPR_DINO_DUCK1, SPR_DINO_DUCK2, SPR_DINO_DEAD

;                   classic  turbo  night  zen
mode_start:     defb SPEED_MIN, 88, SPEED_MIN, 40
mode_maxes:     defb SPEED_MAX, 128, SPEED_MAX, 40
; the hundreds of points after which birds may turn up
mode_birds:     defb 8, 4, 3, 255

bird_heights:   defb BIRD_LOW, BIRD_MID, BIRD_HIGH

; the collision box of each obstacle: left and top inset, width, height.
; Generous enough to be fair, tight enough that flying past a cactus looks
; like flying past it.
ob_box:         defb 2, 2, 4, 15
                defb 3, 4, 6, 21
                defb 5, 6, 13, 8

; ---- the three sounds ---------------------------------------------------
; jump: the page's button-press, 500 Hz for about eighty milliseconds
sfx_jump:
        defb 1, 2, 2, 0xE0, 3, 0
        defb 1, 1, 10, 12
        defb 2, 1, 10, 8
        defb 2, 1, 10, 4
        defb 1, 1, 10, 0
        defb 0
; hit: the noise burst, 300 Hz of rubble for a fifth of a second
sfx_hit:
        defb 1, 2, 7, 0x1F, 6, 3
        defb 1, 1, 10, 13
        defb 3, 1, 6, 6
        defb 3, 1, 6, 9
        defb 3, 1, 10, 9
        defb 3, 1, 6, 14
        defb 2, 1, 10, 5
        defb 2, 1, 10, 0
        defb 0
; score-reached: 500 Hz then 800 Hz, which is exactly what the mp3 does
sfx_point:
        defb 1, 2, 2, 0xE0, 3, 0
        defb 1, 1, 10, 12
        defb 3, 2, 2, 0x8C, 3, 0
        defb 4, 1, 10, 12
        defb 3, 1, 10, 6
        defb 2, 1, 10, 0
        defb 0

        include "music.asm"
        include "gfx.asm"

        ; a cartridge is 16 KB even when the code is shorter
        ds 0x8000 - $, 0xFF
