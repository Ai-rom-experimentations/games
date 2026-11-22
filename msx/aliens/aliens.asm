; ==========================================================================
;  ALIENS! - a Galaga style fixed shooter for the MSX1
;
;  Z80 + TMS9918A (Graphics I) + AY-3-8910.  16 KB cartridge, header at
;  $4000, INIT at $4010.  The game polls the VDP status flag for its frame
;  tick and keeps interrupts off, so it needs nothing from the BIOS after
;  INIT - and never returns from INIT at all.
;
;  Build:  make            (sjasmplus --raw=aliens.rom aliens.asm)
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
PPIJOY  equ 0xa8                      ; PPI port A: joystick 1, active low
PPIKEY  equ 0xa9                      ; PPI port B: the keyboard matrix
PPIROW  equ 0xaa                      ; PPI port C: keyboard row select

; ---- the pad: one bit per direction and button, joystick or keyboard ------
J_UP    equ 0x01
J_DOWN  equ 0x02
J_LEFT  equ 0x04
J_RIGHT equ 0x08
J_FIRE  equ 0x10

; ---- VDP tables ----------------------------------------------------------
NAME    equ 0x1800
COLOUR  equ 0x2000
SAT     equ 0x1b00
SPRPAT  equ 0x3800

; ---- the shape of things -------------------------------------------------
SHIP_Y      equ 168                   ; the ship's top row
SHIP_STEP   equ 3
BULLET_STEP equ 6
DIVE_STEP   equ 2
SHOT_STEP   equ 3
FORM_MIN    equ 2                     ; the formation base column
FORM_MAX    equ 16
ALIEN_COLS  equ 6
ALIEN_ROWS  equ 3
ALIEN_ALL   equ ALIEN_COLS * ALIEN_ROWS
MAX_LIVES   equ 3

ST_TITLE equ 0
ST_PLAY  equ 1
ST_DYING equ 2
ST_OVER  equ 3
ST_WAVE  equ 4

; ---- RAM ($C000 upwards; the BIOS work area starts at $F380) -------------
ram          equ 0xc000
state        equ ram+0
pad          equ ram+1
prev         equ ram+2
timer        equ ram+3
px           equ ram+4
lives        equ ram+5
score        equ ram+6                ; three bytes of packed BCD
hi           equ ram+9
wave         equ ram+12
aliens       equ ram+13               ; 18 slots: 0 dead, $80|type diving
aliens_n     equ ram+31
form_x       equ ram+32
form_y       equ ram+33
form_dir     equ ram+34
form_t       equ ram+35
form_drop    equ ram+36
anim         equ ram+37
anim_t       equ ram+38
bullet_on    equ ram+39
bx           equ ram+40
by           equ ram+41
dive_t       equ ram+42
shot_t       equ ram+43
d_on         equ ram+44               ; diver: on, x, y, type, slot, phase
d_x          equ ram+45
d_y          equ ram+46
d_type       equ ram+47
d_slot       equ ram+48
d_ph         equ ram+49
d2_on        equ ram+50
d2_x         equ ram+51
d2_y         equ ram+52
d2_type      equ ram+53
d2_slot      equ ram+54
d2_ph        equ ram+55
s_on         equ ram+56               ; alien shot: on, x, y
s_x          equ ram+57
s_y          equ ram+58
s2_on        equ ram+59
s2_x         equ ram+60
s2_y         equ ram+61
e_on         equ ram+62               ; explosion: on, col, row, frames
e_col        equ ram+63
e_row        equ ram+64
e_t          equ ram+65
e2_on        equ ram+66
e2_col       equ ram+67
e2_row       equ ram+68
e2_t         equ ram+69
stars        equ ram+70               ; 40 stars, three bytes each
occ          equ ram+190              ; 32 x 24: 1 = an actor owns the cell
sfx_ptr      equ ram+958
sfx_wait     equ ram+960
rand         equ ram+961
title_t      equ ram+962
score_dirty  equ ram+963
hcol         equ ram+964              ; scratch for the inner loops
hrow         equ ram+965
hslot        equ ram+966
htype        equ ram+967
htile        equ ram+968
fdraw        equ ram+969
ram_top      equ 976

STAR_COUNT  equ 40
STAR_BYTES  equ 3                     ; column, row, speed counter

; ==========================================================================
;  boot
; ==========================================================================
start:
        di                            ; we poll the VDP; interrupts stay off
        call vdp_setup
        call psg_silence
        call init_ram
        call title_enter

main_loop:
        call wait_vblank
        call read_pad
        call tick_sound
        call tick_stars
        call dispatch                 ; and it comes back, every frame
        jr main_loop

; the state machine.  Everything below is reached with a jp so that its ret
; unwinds to here: a tick routine must never return into thin air.
dispatch:
        ld a, (state)
        cp ST_PLAY
        jp z, tick_play
        cp ST_DYING
        jp z, tick_dying
        cp ST_OVER
        jp z, tick_over
        cp ST_WAVE
        jp z, tick_wave
        jp tick_title

; ---- one frame, defined by the VDP status flag --------------------------
wait_vblank:
        ld bc, 0
.wait:  in a, (VDPCTRL)               ; reading the status clears the flag
        and 0x80
        jr nz, .got
        dec bc
        ld a, b
        or c
        jr nz, .wait
.got:   ret

; ---- the joystick, turned the right way up ------------------------------
; The joystick is on port A (active low) and the keyboard is the matrix on
; port B: select a row on port C, read port B.  Row 8 holds the cursor keys
; and space, which is the layout the MSX Assembly Page documents and the one
; every emulator puts the cursor keys on, so the game plays with either.
read_pad:
        ld a, (pad)
        ld (prev), a
        xor a
        out (PPIROW), a               ; row 0, and the joystick on port A
        in a, (PPIJOY)
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
        out (PPIROW), a               ; leave the port as we found it
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

        ld hl, colour_data            ; 32 bytes of colour
        ld de, COLOUR
        ld bc, 32
        call vdp_write

        ld hl, pattern_data           ; the tiles
        ld de, 0x0000
        ld bc, PATTERN_COUNT * 8
        call vdp_write

        ld hl, sprite_data            ; the sprites
        ld de, SPRPAT
        ld bc, 8 * 8
        call vdp_write
        jp clear_screen

vdp_regs:
        db 0x00                       ; R0 Graphics I
        db 0xc0                       ; R1 display on, 8x8 sprites, no VDP irq
        db 0x06                       ; R2 name table   $1800
        db 0x80                       ; R3 colour table $2000
        db 0x00                       ; R4 patterns     $0000
        db 0x36                       ; R5 sprite attributes $1B00
        db 0x07                       ; R6 sprite patterns   $3800
        db 0x01                       ; R7 black backdrop

; HL = source, DE = destination, BC = count
vdp_write:
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

; HL = VRAM address
vdp_setaddr:
        ld a, l
        out (VDPCTRL), a
        ld a, h
        or 0x40
        out (VDPCTRL), a
        ret

clear_screen:
        ld hl, NAME
        call vdp_setaddr
        ld bc, 768
.clr:   xor a
        out (VDPDATA), a
        dec bc
        ld a, b
        or c
        jr nz, .clr
        ret

; A = tile, HL = cell address (NAME + row * 32 + col)
put_cell:
        push af
        call vdp_setaddr
        pop af
        out (VDPDATA), a
        ret

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
        ld hl, NAME
        ld a, c
        or a
        jr z, .rowdone
.rowlp: ld de, 32
        add hl, de
        dec a
        jr nz, .rowlp
.rowdone:
        ld a, b
        ld e, a
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

; ==========================================================================
;  the PSG (AY-3-8910)
; ==========================================================================
psg_silence:
        ld a, 7                       ; mixer: everything off
        ld e, 0x3f
        call psg_set
        ld a, 8
        ld e, 0
        call psg_set
        ld a, 9
        ld e, 0
        call psg_set
        ld a, 10
        ld e, 0
        jp psg_set

psg_set:                              ; A = register, E = value
        out (PSGREG), a
        ld a, e
        out (PSGDATA), a
        ret

; HL = a sound script (see the bottom of the file)
sfx_play:
        ld (sfx_ptr), hl
        xor a
        ld (sfx_wait), a
        ret

tick_sound:
        ld a, (sfx_wait)
        or a
        jr z, .step
        dec a
        ld (sfx_wait), a
        ret
.step:  ld hl, (sfx_ptr)
        ld a, h
        or l
        ret z                         ; nothing has ever been played
        ld a, (hl)
        or a
        ret z                         ; the last script has finished
        inc hl
        ld b, a                       ; how long this step lasts
        ld a, (hl)
        inc hl
        or a
        jr z, .hold
        push bc
        ld b, a
.w:     ld a, (hl)
        out (PSGREG), a
        inc hl
        ld a, (hl)
        out (PSGDATA), a
        inc hl
        djnz .w
        pop bc
.hold:  ld a, b
        ld (sfx_wait), a
        ld (sfx_ptr), hl
        ret

; ==========================================================================
;  RAM
; ==========================================================================
init_ram:
        ld hl, ram
        ld bc, ram_top
.clr:   xor a
        ld (hl), a
        inc hl
        dec bc
        ld a, b
        or c
        jr nz, .clr
        ld a, 0x2a
        ld (rand), a
        xor a                        ; 2000 points to beat
        ld (hi), a
        ld a, 0x20
        ld (hi+1), a
        xor a
        ld (hi+2), a
        ld a, MAX_LIVES
        ld (lives), a
        ret

; a right shifting 8 bit LFSR, period 255. The low bits are the freshly
; fed back ones, which is what matters here: this is only ever used through
; and 0x1f. (A left shifting register or a multiply by five scatter the high
; bits and leave the low ones marching in step, which made the stars line up
; in a handful of columns.)
random:
        ld a, (rand)
        srl a
        jr nc, .no
        xor 0xb8
.no:    ld (rand), a
        ret

; ==========================================================================
;  the title screen
; ==========================================================================
title_enter:
        ld a, ST_TITLE
        ld (state), a
        call clear_screen
        call init_occupancy
        ld hl, title_map              ; ALIENS! in big letters
        ld de, NAME
        ld bc, 768
        call vdp_write
        call mark_title
        ld hl, str_press
        ld b, 9
        ld c, 14
        call print_at
        ld hl, str_hi
        ld b, 9
        ld c, 17
        call print_at
        call draw_hi_title
        ld a, 120
        ld (px), a
        xor a
        ld (form_dir), a
        ld (title_t), a
        call init_stars
        jp update_sprites

tick_title:
        ld hl, title_t
        inc (hl)
        ld a, (hl)
        and 0x1f
        jr nz, .go
        bit 5, (hl)                   ; blink PRESS TRIGGER
        jr nz, .blank
        ld hl, str_press
        ld b, 9
        ld c, 14
        call print_at
        jr .go
.blank: ld hl, NAME + 14 * 32 + 9
        call vdp_setaddr
        ld b, 13
.b:     xor a
        out (VDPDATA), a
        djnz .b
.go:    call tick_ship                 ; the ship slides about, for the look of it
        call update_sprites
        ld a, (pad)
        and J_FIRE
        jr z, .done
        ld a, (prev)
        and J_FIRE
        ret nz
        jp new_game
.done:  ret

tick_ship:
        ld a, (title_t)
        and 0x3f
        ret nz
        ld a, (form_dir)
        or a
        jr nz, .right
        ld a, (px)
        cp 16
        jr c, .flip
        sub 8
        ld (px), a
        ret
.flip:  ld a, 1
        ld (form_dir), a
        ret
.right: ld a, (px)
        cp 232
        jr nc, .flip2
        add a, 8
        ld (px), a
        ret
.flip2: xor a
        ld (form_dir), a
        ret

; ---- the occupancy map: which cells a star must not draw over ------------
init_occupancy:
        ld hl, occ
        ld bc, 768
.clr:   xor a
        ld (hl), a
        inc hl
        dec bc
        ld a, b
        or c
        jr nz, .clr
        ret

; keep the stars off the title's own cells
mark_title:
        ld hl, occ + 5 * 32 + 9
        ld b, 2
.row:   push bc
        push hl
        ld b, 14                      ; the big letters are 14 cells wide
.col:   ld (hl), 1
        inc hl
        djnz .col
        pop hl
        pop bc
        ld de, 32
        add hl, de
        djnz .row
        ld hl, occ + 14 * 32 + 9
        ld b, 13
.c1:    ld (hl), 1
        inc hl
        djnz .c1
        ld hl, occ + 17 * 32 + 9
        ld b, 16
.c2:    ld (hl), 1
        inc hl
        djnz .c2
        ret

; ==========================================================================
;  a new game
; ==========================================================================
new_game:
        xor a
        ld (score), a
        ld (score+1), a
        ld (score+2), a
        ld (score_dirty), a
        ld a, MAX_LIVES
        ld (lives), a
        ld a, 1
        ld (wave), a
        ld a, 120
        ld (px), a
        call clear_screen
        call init_occupancy
        call init_stars
        call draw_hud
        call new_wave
        ld a, ST_WAVE
        ld (state), a
        ld a, 80
        ld (timer), a
        jp draw_wave_text

; a fresh formation: everything alive, every timer armed
new_wave:
        ld hl, aliens
        ld b, ALIEN_COLS
        ld a, 3                       ; the top row is the boss
        call fill_row
        ld b, ALIEN_COLS
        ld a, 2
        call fill_row
        ld b, ALIEN_COLS
        ld a, 1
        call fill_row
        ld a, ALIEN_ALL
        ld (aliens_n), a
        ld a, 3
        ld (form_x), a
        ld a, 2
        ld (form_y), a
        ld a, 1
        ld (form_dir), a
        ld a, 24
        ld (form_t), a
        ld a, 240
        ld (form_drop), a
        xor a
        ld (anim), a
        ld (anim_t), a
        ld (bullet_on), a
        ld (d_on), a
        ld (d2_on), a
        ld (s_on), a
        ld (s2_on), a
        ld (e_on), a
        ld (e2_on), a
        ld a, 90
        ld (dive_t), a
        ld a, 70
        ld (shot_t), a
        ld a, 1
        jp formation_pass

fill_row:
        ld (hl), a
        inc hl
        djnz fill_row
        ret

draw_wave_text:
        ld hl, str_wave
        ld b, 13
        ld c, 12
        call print_at
        ld a, (wave)
        add a, '0'
        call char_tile
        ld hl, NAME + 12 * 32 + 18
        jp put_cell

draw_wave_num:
        ld a, (wave)
        add a, '0'
        call char_tile
        ld hl, NAME + 32 + 5
        jp put_cell

tick_wave:
        call tick_anim
        call tick_formation
        call update_sprites
        ld hl, timer
        dec (hl)
        ret nz
        ld a, ST_PLAY
        ld (state), a
        ld hl, NAME + 12 * 32 + 13
        call vdp_setaddr
        ld b, 6
.clr:   xor a
        out (VDPDATA), a
        djnz .clr
        ret

; ==========================================================================
;  playing: one frame
; ==========================================================================
tick_play:
        call move_ship
        call fire
        call tick_bullet
        call tick_divers
        call tick_shots
        call tick_explosions
        call tick_formation
        call tick_anim
        call tick_spawn
        call update_sprites
        ld a, (score_dirty)
        or a
        jr z, .score
        call draw_score
        xor a
        ld (score_dirty), a
.score: ld a, (aliens_n)
        or a
        ret nz
        jp wave_clear

move_ship:
        ld a, (pad)
        bit 2, a
        jr z, .nol
        ld a, (px)
        or a
        jr z, .nol                    ; already against the left wall
        cp SHIP_STEP
        jr nc, .left
        xor a                         ; and not quite there: land on it
        ld (px), a
        jr .nol
.left:  sub SHIP_STEP
        ld (px), a
.nol:   ld a, (pad)
        bit 3, a
        jr z, .nor
        ld a, (px)
        cp 248
        jr nc, .nor
        add a, SHIP_STEP
        cp 248
        jr c, .right
        ld a, 248
.right: ld (px), a
.nor:   ret

fire:
        ld a, (pad)
        and J_FIRE
        ret z
        ld a, (bullet_on)
        or a
        ret nz
        ld a, 1
        ld (bullet_on), a
        ld a, (px)
        add a, 3
        ld (bx), a
        ld a, SHIP_Y - 12
        ld (by), a
        ld hl, sfx_shoot
        jp sfx_play

; ---- the player's bullet -------------------------------------------------
tick_bullet:
        ld a, (bullet_on)
        or a
        ret z
        ld a, (by)
        sub BULLET_STEP
        jr c, .gone
        ld (by), a
        cp 16
        jr c, .gone
        ; inside a diving alien?
        ld ix, d_on
        call bullet_diver
        or a
        jr nz, .gone
        ld ix, d2_on
        call bullet_diver
        or a
        jr nz, .gone
        ; inside an alien's cell?  the bullet sits two pixels wide at bx, so
        ; bx + 1 is the middle of the ship and of the alien above it
        ld a, (bx)
        add a, 1
        srl a
        srl a
        srl a                         ; A = column
        ld d, a
        ld a, (by)
        srl a
        srl a
        srl a                         ; A = row
        ld e, a
        call hit_alien
        ret nc
.gone:  xor a
        ld (bullet_on), a
        ret

; IX = a diver; A = nonzero if the bullet hit it (and it is gone)
bullet_diver:
        ld a, (ix+0)
        or a
        ret z
        ld b, (ix+1)
        ld a, (bx)
        ld c, a
        call near8
        jr nc, .miss
        ld b, (ix+2)
        ld a, (by)
        ld c, a
        call near8
        jr nc, .miss
        ; the diver is shot
        ld a, (ix+3)
        call alien_score
        ld e, (ix+4)
        ld d, 0
        ld hl, aliens
        add hl, de
        xor a
        ld (hl), a                    ; the slot is empty for good
        ld a, (aliens_n)
        dec a
        ld (aliens_n), a
        xor a
        ld (ix+0), a
        ld hl, sfx_boom
        call sfx_play
        ld a, 1
        ret
.miss:  xor a
        ret

; B and C -> carry set if |B - C| < 8
near8:
        ld a, b
        sub c
        jr nc, .pos
        neg
.pos:   cp 8
        ret

; D = column, E = row.  Carry set if an alien was hit (and is gone).
hit_alien:
        ld a, d
        ld (hcol), a
        ld a, e
        ld (hrow), a
        xor a
        ld (hslot), a
.loop:  ld a, (hslot)
        cp ALIEN_ALL
        jr nc, .no
        ld e, a
        ld d, 0
        ld hl, aliens
        add hl, de
        ld a, (hl)
        or a
        jr z, .next
        bit 7, a
        jr nz, .next
        ld (htype), a
        ld a, (hslot)
        call slot_cell                ; D = col, E = row
        ld a, (hcol)
        cp d
        jr nz, .next
        ld a, (hrow)
        cp e
        jr nz, .next
        ; hit
        ld a, (hslot)
        ld e, a
        ld d, 0
        ld hl, aliens
        add hl, de
        xor a
        ld (hl), a
        ld a, (aliens_n)
        dec a
        ld (aliens_n), a
        ld a, (htype)
        call alien_score
        ld a, (hcol)
        ld h, a
        ld a, (hrow)
        ld l, a
        call add_explosion
        ld hl, sfx_boom
        call sfx_play
        scf
        ret
.next:  ld a, (hslot)
        inc a
        ld (hslot), a
        jr .loop
.no:    or a
        ret

; A = the alien's type -> the points for it
alien_score:
        cp 3
        jr z, .boss
        cp 2
        jr z, .fly
        ld hl, points_a
        jr .add
.boss:  ld hl, points_c
        jr .add
.fly:   ld hl, points_b
.add:   jp add_points

; ==========================================================================
;  the formation
; ==========================================================================
; A = slot -> D = column, E = row
slot_cell:
        ld c, a
        ld b, 0
        ld hl, form_dx
        add hl, bc
        ld a, (hl)
        ld d, a
        ld a, (form_x)
        add a, d
        ld d, a
        ld hl, form_dy
        add hl, bc
        ld a, (hl)
        ld e, a
        ld a, (form_y)
        add a, e
        ld e, a
        ret

tick_formation:
        ld hl, form_t
        dec (hl)
        jr nz, .drop
        xor a
        call formation_pass            ; wipe the old cells
        ld a, (form_x)
        ld b, a
        ld a, (form_dir)
        add a, b
        cp FORM_MIN
        jr c, .turn_right
        cp FORM_MAX + 1
        jr nc, .turn_left
        ld (form_x), a
        jr .redraw
.turn_right:
        ld a, 1
        ld (form_dir), a
        ld a, (form_x)
        inc a
        ld (form_x), a
        jr .redraw
.turn_left:
        ld a, 0xff
        ld (form_dir), a
        ld a, (form_x)
        dec a
        ld (form_x), a
.redraw:
        ld a, (wave)                  ; the sway quickens with every wave,
        add a, a                      ; but never gets faster than 20 frames
        ld b, a
        ld a, 46
        sub b
        cp 20
        jr nc, .ok
        ld a, 20
.ok:    ld (form_t), a
        ld a, 1
        call formation_pass
.drop:  ld hl, form_drop
        dec (hl)
        ret nz
        ld a, 240
        ld (form_drop), a
        ld a, (form_y)
        cp 12
        ret nc
        xor a
        call formation_pass
        ld a, (form_y)
        inc a
        ld (form_y), a
        ld a, 1
        jp formation_pass

; A = 1: draw the formation, A = 0: erase it
formation_pass:
        ld (fdraw), a
        xor a
        ld (hslot), a
.slot:  ld a, (hslot)
        ld e, a
        ld d, 0
        ld hl, aliens
        add hl, de
        ld a, (hl)
        or a
        jr z, .next
        bit 7, a
        jr nz, .next
        ld (htype), a
        ld a, (hslot)
        call slot_cell                ; D = col, E = row
        ld a, d
        ld (hcol), a
        ld a, e
        ld (hrow), a
        ld a, (fdraw)
        or a
        jr z, .erase
        ld a, (htype)
        ld b, 0
        ld c, a
        ld a, (anim)
        ld b, a
        ld a, c
        call alien_tile
        jr .put
.erase: xor a
.put:   ld (htile), a
        ld a, (hcol)
        ld b, a
        ld a, (hrow)
        ld c, a
        call cell_addr
        ld a, (htile)
        call put_cell
        ld a, (hcol)
        ld b, a
        ld a, (hrow)
        ld c, a
        ld a, (fdraw)
        or a
        jr z, .free
        call occ_set
        jr .next
.free:  call occ_clear
.next:  ld a, (hslot)
        inc a
        ld (hslot), a
        cp ALIEN_ALL
        jr c, .slot
        ret

; A = type, B = animation frame (0/1) -> A = tile
alien_tile:
        cp 2
        jr z, .b
        cp 3
        jr z, .c
        ld a, TILE_ALIEN_A
        jr .frame
.b:     ld a, TILE_ALIEN_B
        jr .frame
.c:     ld a, TILE_ALIEN_C
.frame: add a, b
        ret

tick_anim:
        ld hl, anim_t
        inc (hl)
        ld a, (hl)
        cp 16
        ret c
        ld (hl), 0
        ld a, (anim)
        xor 1
        ld (anim), a
        ld a, 1
        jp formation_pass

; ==========================================================================
;  divers and shots
; ==========================================================================
tick_spawn:
        ld hl, dive_t
        dec (hl)
        jr nz, .shots
        ld a, 140
        ld b, a
        ld a, (wave)
        add a, a
        add a, a
        add a, a
        ld c, a
        ld a, b
        sub c
        cp 50
        jr nc, .ok
        ld a, 50
.ok:    ld (dive_t), a
        call spawn_diver
.shots: ld hl, shot_t
        dec (hl)
        ret nz
        ld a, 90
        ld b, a
        ld a, (wave)
        add a, a
        add a, a
        add a, a
        ld c, a
        ld a, b
        sub c
        cp 35
        jr nc, .ok2
        ld a, 35
.ok2:   ld (shot_t), a
        jp spawn_shot

spawn_diver:
        ld a, (d_on)
        or a
        jr z, .one
        ld a, (d2_on)
        or a
        ret nz
        ld ix, d2_on
        jr .pick
.one:   ld ix, d_on
.pick:  ld b, 12
.try:   push bc
        call random
        and 0x1f
        cp ALIEN_ALL
        jr nc, .miss
        ld e, a
        ld d, 0
        ld hl, aliens
        add hl, de
        ld a, (hl)
        or a
        jr z, .miss
        bit 7, a
        jr nz, .miss
        ld (ix+3), a                  ; type
        ld a, e
        ld (ix+4), a                  ; which slot it came from
        or 0x80
        ld (hl), a
        ld a, e
        call slot_cell                ; D = col, E = row
        ld a, d
        add a, a
        add a, a
        add a, a
        ld (ix+1), a                  ; x
        ld a, e
        add a, a
        add a, a
        add a, a
        ld (ix+2), a                  ; y
        ld (ix+5), 0
        ld (ix+0), 1
        ; the tile goes, the sprite arrives
        ld a, (ix+4)
        call slot_cell
        ld a, d
        ld (hcol), a
        ld a, e
        ld (hrow), a
        ld b, d
        ld c, e
        call cell_addr
        xor a
        call put_cell
        ld a, (hcol)
        ld b, a
        ld a, (hrow)
        ld c, a
        call occ_clear
        ld hl, sfx_dive
        call sfx_play
        pop bc
        ret
.miss:  pop bc
        djnz .try
        ret

tick_divers:
        ld ix, d_on
        call tick_diver
        ld ix, d2_on
        jp tick_diver

tick_diver:
        ld a, (ix+0)
        or a
        ret z
        ld a, (ix+2)
        add a, DIVE_STEP
        cp 184
        jr nc, .home
        ld (ix+2), a
        ld a, (ix+5)
        inc a
        ld (ix+5), a
        and 0x08
        jr z, .left
        ld a, (ix+1)
        cp 240
        jr nc, .check
        inc a
        ld (ix+1), a
        jr .check
.left:  ld a, (ix+1)
        or a
        jr z, .check
        dec a
        ld (ix+1), a
.check: ld b, (ix+1)
        ld a, (px)
        ld c, a
        call near8
        jr nc, .out
        ld b, (ix+2)
        ld a, SHIP_Y
        ld c, a
        call near8
        jr nc, .out
        xor a
        ld (ix+0), a
        call diver_home
        jp player_dies
.out:   ret
.home:  xor a
        ld (ix+0), a
        call diver_home
        ret

; IX = a diver that has finished: its alien goes back in its slot
diver_home:
        ld e, (ix+4)
        ld d, 0
        ld hl, aliens
        add hl, de
        ld a, (ix+3)
        ld (hl), a
        ld a, 1
        jp formation_pass

; ---- the aliens' shots ---------------------------------------------------
spawn_shot:
        ld a, (s_on)
        or a
        jr z, .one
        ld a, (s2_on)
        or a
        ret nz
        ld ix, s2_on
        jr .pick
.one:   ld ix, s_on
.pick:  ld b, 12
.try:   push bc
        call random
        and 0x1f
        cp ALIEN_ALL
        jr nc, .miss
        ld e, a
        ld d, 0
        ld hl, aliens
        add hl, de
        ld a, (hl)
        or a
        jr z, .miss
        bit 7, a
        jr nz, .miss
        ld a, e
        call slot_cell
        ld a, d
        add a, a
        add a, a
        add a, a
        add a, 3
        ld (ix+1), a
        ld a, e
        add a, a
        add a, a
        add a, a
        add a, 7
        ld (ix+2), a
        ld (ix+0), 1
        ld hl, sfx_shot
        call sfx_play
        pop bc
        ret
.miss:  pop bc
        djnz .try
        ret

tick_shots:
        ld ix, s_on
        call tick_shot
        ld ix, s2_on
        jp tick_shot

tick_shot:
        ld a, (ix+0)
        or a
        ret z
        ld a, (ix+2)
        add a, SHOT_STEP
        cp 184
        jr nc, .gone
        ld (ix+2), a
        ld b, (ix+1)
        ld a, (px)
        add a, 4
        ld c, a
        call near8
        jr nc, .out
        ld b, (ix+2)
        ld a, SHIP_Y + 2
        ld c, a
        call near8
        jr nc, .out
        xor a
        ld (ix+0), a
        jp player_dies
.out:   ret
.gone:  xor a
        ld (ix+0), a
        ret

; ==========================================================================
;  dying, and the end of the game
; ==========================================================================
player_dies:
        ld a, ST_DYING
        ld (state), a
        ld a, 50
        ld (timer), a
        ld hl, sfx_death
        call sfx_play
        xor a
        ld (bullet_on), a
        ld (d_on), a
        ld (d2_on), a
        ld (s_on), a
        ld (s2_on), a
        ret

tick_dying:
        ld hl, timer
        dec (hl)
        jr nz, .draw
        ld a, (lives)
        dec a
        ld (lives), a
        jr z, .over
        call draw_lives
        ld a, 120
        ld (px), a
        ld a, ST_PLAY
        ld (state), a
.draw:  jp update_sprites
.over:  jp game_over

game_over:
        ld a, ST_OVER
        ld (state), a
        ld a, 220
        ld (timer), a
        ld hl, str_over
        ld b, 11
        ld c, 12
        call print_at
        call draw_lives               ; no ships left, so the icons go too
        call update_hi
        ld hl, sfx_over
        call sfx_play
        jp update_sprites            ; and the ship is gone

; is this score the new best?
update_hi:
        ld hl, score
        ld de, hi
        ld b, 3
.cmp:   ld a, (de)
        cp (hl)
        jr c, .copy
        jr nz, .done
        inc hl
        inc de
        djnz .cmp
        ret
.copy:  ld hl, score
        ld de, hi
        ld bc, 3
        ldir
        jp draw_hi
.done:  ret

tick_over:
        ld hl, timer
        dec (hl)
        jr z, .leave
        ld a, (pad)
        and J_FIRE
        ret z
        ld a, (prev)
        and J_FIRE
        ret nz
.leave: jp title_enter

; ==========================================================================
;  a wave is over
; ==========================================================================
wave_clear:
        ld a, (wave)
        inc a
        cp 9
        jr c, .ok
        ld a, 8
.ok:    ld (wave), a
        xor a
        ld (d_on), a
        ld (d2_on), a
        ld (s_on), a
        ld (s2_on), a
        ld (e_on), a
        ld (e2_on), a
        ld hl, points_clear
        call add_points
        call draw_wave_num
        call new_wave
        ld a, ST_WAVE
        ld (state), a
        ld a, 80
        ld (timer), a
        call draw_wave_text
        ld hl, sfx_wave
        jp sfx_play

; ==========================================================================
;  explosions: a three frame tile animation at a cell
; ==========================================================================
; H = column, L = row
add_explosion:
        ld a, (e_on)
        or a
        jr z, .one
        ld a, (e2_on)
        or a
        ret nz
        ld ix, e2_on
        jr .use
.one:   ld ix, e_on
.use:   ld (ix+1), h
        ld (ix+2), l
        ld (ix+3), 9
        ld (ix+0), 1
        ret

tick_explosions:
        ld ix, e_on
        call tick_explosion
        ld ix, e2_on
        jp tick_explosion

tick_explosion:
        ld a, (ix+0)
        or a
        ret z
        dec (ix+3)
        jr nz, .draw
        xor a
        ld (ix+0), a
        ld a, (ix+1)
        ld (hcol), a
        ld a, (ix+2)
        ld (hrow), a
        ld b, a
        ld a, (hcol)
        ld b, a
        ld a, (hrow)
        ld c, a
        push bc
        call occ_clear
        pop bc
        call cell_addr
        xor a
        jp put_cell
.draw:  ld a, (ix+3)
        cp 6
        jr nc, .a
        cp 3
        jr nc, .b
        ld a, TILE_EXPLOSION + 2
        jr .put
.b:     ld a, TILE_EXPLOSION + 1
        jr .put
.a:     ld a, TILE_EXPLOSION
.put:   push af
        ld a, (ix+1)
        ld b, a
        ld a, (ix+2)
        ld c, a
        call occ_set
        pop af
        ld b, (ix+1)
        ld c, (ix+2)
        call cell_addr
        jp put_cell

; ==========================================================================
;  the stars
; ==========================================================================
init_stars:
        ld hl, stars
        ld b, STAR_COUNT
.next:  push bc
        push hl
        call random
        and 0x1f
        ld (hl), a                    ; column
        ld d, a
        inc hl
        call random
        and 0x1f
        cp 22
        jr c, .ok
        sub 10
.ok:    add a, 2                      ; rows 2..23, under the scoreboard
        ld (hl), a
        ld e, a
        inc hl
        ld (hl), 0                    ; phase
        call star_draw                ; and it is on the screen at once
        pop hl
        ld de, STAR_BYTES
        add hl, de
        pop bc
        djnz .next
        ret

tick_stars:
        ld hl, stars
        ld b, STAR_COUNT
.star:  push bc
        push hl
        inc hl
        inc hl
        ld a, (hl)
        inc a
        cp 4
        jr c, .keep
        xor a
.keep:  ld (hl), a
        or a
        jr nz, .next
        pop hl
        push hl
        ld d, (hl)                    ; column
        inc hl
        ld e, (hl)                    ; row
        push de
        call star_erase
        pop de
        inc e
        ld a, e
        cp 24
        jr c, .keepr
        push de
        call random
        and 0x1f
        ld d, a
        pop de
        ld e, 2
.keepr: pop hl
        push hl
        ld (hl), d
        inc hl
        ld (hl), e
        call star_draw
.next:  pop hl
        ld de, STAR_BYTES
        add hl, de
        pop bc
        djnz .star
        ret

; D = column, E = row
star_draw:
        push de
        ld b, d
        ld c, e
        call occ_test
        pop de
        jr c, .skip
        ld a, d
        and 0x03
        cp 3                          ; 4 possible columns, 3 star tiles
        jr c, .tile
        xor a
.tile:  add a, TILE_STARS
        push af
        ld b, d
        ld c, e
        call cell_addr
        pop af
        jp put_cell
.skip:  ret

star_erase:
        push de
        ld b, d
        ld c, e
        call occ_test
        pop de
        jr c, .skip
        ld b, d
        ld c, e
        call cell_addr
        xor a
        jp put_cell
.skip:  ret

; ==========================================================================
;  cells, the occupancy map, and the sprite table
; ==========================================================================
; B = column, C = row -> HL = the cell in the name table
cell_addr:
        ld h, 0
        ld l, c
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl                    ; row * 32
        ld a, b
        add a, l
        ld l, a
        ld a, 0
        adc a, h
        ld h, a
        ld de, NAME
        add hl, de
        ret

; B = column, C = row -> HL = the cell in the occupancy map
occ_addr:
        ld h, 0
        ld l, c
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        ld a, b
        add a, l
        ld l, a
        ld a, 0
        adc a, h
        ld h, a
        ld de, occ
        add hl, de
        ret

occ_set:
        call occ_addr
        ld (hl), 1
        ret

occ_clear:
        call occ_addr
        ld (hl), 0
        ret

; B = column, C = row -> carry set if an actor owns the cell
occ_test:
        call occ_addr
        ld a, (hl)
        or a
        ret z
        scf
        ret

; ---- the sprite attribute table -----------------------------------------
update_sprites:
        ld hl, SAT
        call vdp_setaddr
        ld a, (state)
        cp ST_DYING
        jr z, .boom
        cp ST_OVER
        jr z, .noship
        ld a, SHIP_Y - 1
        out (VDPDATA), a
        ld a, (px)
        out (VDPDATA), a
        ld a, SPR_SHIP
        out (VDPDATA), a
        ld a, 15
        out (VDPDATA), a
        jr .bullet
.boom:  ld a, SHIP_Y - 1
        out (VDPDATA), a
        ld a, (px)
        out (VDPDATA), a
        ld a, SPR_EXPLOSION
        out (VDPDATA), a
        ld a, 9
        out (VDPDATA), a
        jr .bullet
.noship:
        call hide_sprite
.bullet:
        ld a, (bullet_on)
        or a
        jr z, .nob
        ld a, (by)
        dec a
        out (VDPDATA), a
        ld a, (bx)
        out (VDPDATA), a
        ld a, SPR_BULLET
        out (VDPDATA), a
        ld a, 11
        out (VDPDATA), a
        jr .d1
.nob:   call hide_sprite
.d1:    ld ix, d_on
        call put_diver
        ld ix, d2_on
        call put_diver
        ld a, (s_on)
        or a
        jr z, .s1h
        ld a, (s_y)
        dec a
        out (VDPDATA), a
        ld a, (s_x)
        out (VDPDATA), a
        ld a, SPR_SHOT
        out (VDPDATA), a
        ld a, 8
        out (VDPDATA), a
        jr .s2
.s1h:   call hide_sprite
.s2:    ld a, (s2_on)
        or a
        jr z, .s2h
        ld a, (s2_y)
        dec a
        out (VDPDATA), a
        ld a, (s2_x)
        out (VDPDATA), a
        ld a, SPR_SHOT
        out (VDPDATA), a
        ld a, 8
        out (VDPDATA), a
        jr .end
.s2h:   call hide_sprite
.end:   ld a, 0xd0
        out (VDPDATA), a
        ret

; 0xd0 means "end of the sprite list" to the VDP, so a sprite that is only
; resting has to be parked out of sight with 0xd1: the entries after it still
; count.  (With 0xd0 here the divers never showed unless a bullet happened to
; be in the air, and the aliens' shots only ever showed when nothing else was
; parked in between.)
hide_sprite:
        ld a, 0xd1
        out (VDPDATA), a
        xor a
        out (VDPDATA), a
        out (VDPDATA), a
        out (VDPDATA), a
        ret

put_diver:
        ld a, (ix+0)
        or a
        jr z, hide_sprite
        ld a, (ix+2)
        dec a
        out (VDPDATA), a
        ld a, (ix+1)
        out (VDPDATA), a
        ld a, (ix+3)                  ; type 1..3 -> sprite 2..4
        add a, SPR_ALIEN_A - 1
        out (VDPDATA), a
        ld a, (ix+3)
        ld hl, diver_colour
        ld e, a
        ld d, 0
        add hl, de
        ld a, (hl)
        out (VDPDATA), a
        ret

diver_colour:
        db 0, 3, 7, 11

; ==========================================================================
;  the HUD
; ==========================================================================
draw_hud:
        ld hl, str_score
        ld b, 0
        ld c, 0
        call print_at
        ld hl, str_hi
        ld b, 16
        ld c, 0
        call print_at
        ld hl, str_wave
        ld b, 0
        ld c, 1
        call print_at
        call draw_score
        call draw_hi
        call draw_wave_num
        jp draw_lives

draw_score:
        ld hl, NAME + 6
        ld de, score
        jp draw_bcd3

draw_hi:                              ; the copies in the scoreboard
        ld hl, NAME + 19
        ld de, hi
        jp draw_bcd3

draw_hi_title:                        ; and the one on the title screen
        ld hl, NAME + 17 * 32 + 12
        ld de, hi
        jp draw_bcd3

; HL = where to put it, DE = three bytes of packed BCD, six tiles
draw_bcd3:
        push de
        call vdp_setaddr
        pop hl
        ld b, 3
.byte:  ld a, (hl)
        push hl
        push bc
        rrca
        rrca
        rrca
        rrca
        and 0x0f
        call put_digit
        pop bc
        pop hl
        ld a, (hl)
        and 0x0f
        push hl
        push bc
        call put_digit
        pop bc
        pop hl
        inc hl
        djnz .byte
        ret

put_digit:
        add a, '0'
        call char_tile
        out (VDPDATA), a
        ret

draw_lives:
        ld hl, NAME + 32 + 25          ; row 1, right of the high score
        call vdp_setaddr
        ld b, 6
.clr:   xor a
        out (VDPDATA), a
        djnz .clr
        ld a, (lives)
        or a
        ret z
        cp MAX_LIVES
        jr c, .have
        ld a, MAX_LIVES
.have:  ld b, a
        ld hl, NAME + 32 + 25
        call vdp_setaddr
.icon:  ld a, TILE_SHIP_ICON
        out (VDPDATA), a
        xor a
        out (VDPDATA), a
        djnz .icon
        ret

; ==========================================================================
;  the score
; ==========================================================================
; HL = a three byte BCD value (most significant first) to add to the score
add_points:
        inc hl
        inc hl
        ld de, score + 2
        ld b, 3
        or a
.loop:  ld a, (de)
        adc a, (hl)
        daa
        ld (de), a
        dec hl
        dec de
        djnz .loop
        ld a, 1
        ld (score_dirty), a
        ret

points_a:     db 0x00, 0x00, 0x50     ; 50
points_b:     db 0x00, 0x01, 0x00     ; 100
points_c:     db 0x00, 0x01, 0x50     ; 150
points_clear: db 0x00, 0x02, 0x00     ; 200 for a cleared wave

; ==========================================================================
;  strings and tables
; ==========================================================================
str_score: db "SCORE ", 0
str_hi:    db "HI ", 0
str_wave:  db "WAVE ", 0
str_press: db "PRESS TRIGGER", 0
str_over:  db "GAME OVER", 0

form_dx:   db 0, 3, 6, 9, 12, 15
           db 0, 3, 6, 9, 12, 15
           db 0, 3, 6, 9, 12, 15
form_dy:   db 0, 0, 0, 0, 0, 0
           db 2, 2, 2, 2, 2, 2
           db 4, 4, 4, 4, 4, 4

; ==========================================================================
;  sound effects: steps of (frames, writes, register, value ...)
; ==========================================================================
sfx_shoot:
        db 2, 4, 7, 0x3e, 0, 93, 1, 0, 8, 13
        db 2, 4, 7, 0x3e, 0, 130, 1, 0, 8, 9
        db 2, 3, 0, 180, 1, 0, 8, 4
        db 1, 1, 8, 0
        db 0
sfx_boom:
        db 3, 3, 7, 0x37, 6, 12, 8, 15
        db 3, 2, 6, 18, 8, 11
        db 4, 2, 6, 26, 8, 6
        db 2, 1, 8, 0
        db 0
sfx_shot:
        db 2, 4, 7, 0x3e, 0, 60, 1, 1, 8, 6
        db 2, 3, 0, 45, 1, 1, 8, 0
        db 0
sfx_dive:
        db 3, 4, 7, 0x3e, 0, 200, 1, 0, 8, 8
        db 3, 3, 0, 150, 1, 0, 8, 4
        db 2, 1, 8, 0
        db 0
sfx_death:
        db 4, 3, 7, 0x37, 6, 20, 8, 15
        db 4, 2, 6, 30, 8, 12
        db 4, 2, 6, 8, 8, 9
        db 6, 2, 6, 40, 8, 4
        db 3, 1, 8, 0
        db 0
sfx_wave:
        db 4, 4, 7, 0x3e, 0, 143, 1, 0, 8, 12
        db 4, 4, 0, 113, 1, 0, 8, 12
        db 4, 4, 0, 85, 1, 0, 8, 12
        db 6, 4, 7, 0x37, 6, 16, 8, 8
        db 4, 1, 8, 0
        db 0
sfx_over:
        db 8, 4, 7, 0x3e, 0, 200, 1, 1, 8, 10
        db 8, 4, 0, 170, 1, 1, 8, 10
        db 8, 4, 0, 140, 1, 1, 8, 10
        db 10, 4, 0, 110, 1, 1, 8, 10
        db 4, 1, 8, 0
        db 0

; ==========================================================================
        include "gfx.asm"

        defs 0x8000 - $, 0xff
