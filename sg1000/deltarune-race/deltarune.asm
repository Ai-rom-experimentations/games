; ==========================================================================
;  D E L T A R U N E  Chapter 3  -  H I D D E N   R A C I N G   M I N I G A M E
;  for the Sega SG-1000 (Z80 / TMS9918A / SN76489)
; ==========================================================================
;  In Deltarune Chapter 3 you can play a racing game with Susie on the TV in
;  the Green Room.  The camera faces away from the screen, so all you see is
;  Kris' hands - but the game itself really runs: a box you steer around a
;  square with the movement keys.  Hitting a wall stops the box and plays a
;  bump.  This is that minigame, playable, on SG-1000 hardware.
;
;    * white square (you) on a black track, white 2px wall all round and a
;      white 2px square in the middle, chequered finish line at the bottom
;    * you start on the right of the finish line and drive clockwise (the
;      direction the real minigame is driven - TC RF: "clockwise in a square")
;    * 4 direction movement, 2 pixels a frame, walls stop you with a bump
;    * Susie races you: her square is the magenta one, she takes the outside
;      lane at half your speed, first to 3 laps wins
;    * the middle square holds the lap counters, so the infield is a
;      scoreboard
;    * HOLD (the console button, PAUSE on the SG-1000 II) or joypad 1
;      button 2 pauses
; ==========================================================================

VDPDATA  equ 0xbe
VDPCTRL  equ 0xbf
PSG      equ 0x7f
JOYP1    equ 0xdc

; ---- geometry (256x192 pixels; the walls are 2px lines) ------------------
PX_MIN      equ 10             ; inside the outer wall
PX_MAX      equ 238            ; 238+7 = 245
PY_MIN      equ 10
PY_MAX      equ 174            ; 174+7 = 181

BOX_X       equ 57             ; the middle square blocks x 64..191 ...
BOX_XR      equ 192            ; ... so a car whose left edge is 57..191
BOX_Y       equ 49             ; and whose top is 49..135 would be inside it
BOX_YB      equ 136

CAR_W       equ 8
CAR_STEP    equ 4              ; pixels per frame for the player
CAR_SUB     equ 2              ; ... but moved in steps of this, so that a wall
CAR_SUBS    equ CAR_STEP / CAR_SUB   ; still stops the square flush against it
RIVAL_STEP  equ 2              ; Susie is half as fast

CAR_X0      equ 140            ; just right of the chequered line
CAR_Y0      equ 155            ; middle of the bottom straight
RIVAL_X0    equ 100            ; Susie starts past the line
RIVAL_Y0    equ 155

RIVAL_LEFT  equ 33             ; Susie's lane, centre of the four straights
RIVAL_RIGHT equ 215
RIVAL_TOP   equ 29
RIVAL_BOTTOM equ 155
RIVAL_LINE  equ 112            ; where her lap counts (she is 8px wide)

CP_LEFT     equ 50             ; checkpoint 1: in the left straight
CP_TOP      equ 45             ; checkpoint 2: in the top straight
CP_RIGHT    equ 205            ; checkpoint 3: in the right straight
LAPS_TO_WIN equ 3

; ---- RAM (1 KB at $C000, mirrored) ---------------------------------------
ram         equ 0xc000
state       equ ram+0          ; 0 title, 1 race, 2 won, 3 lost
pad1        equ ram+1
prev1       equ ram+2
paused      equ ram+3
nmi_req     equ ram+4
prev_b2     equ ram+5
sfx_time    equ ram+6
px          equ ram+7          ; player square, top left corner
py          equ ram+8
rx          equ ram+9          ; Susie
ry          equ ram+10
rseg        equ ram+11         ; 0 bottom, 1 left, 2 top, 3 right
cpf         equ ram+12         ; checkpoint reached, 0..3
laps        equ ram+13
rlaps       equ ram+14
hit         equ ram+15         ; a wall stopped us this frame
hit_prev    equ ram+16
sfx1        equ ram+17         ; channel 1 (the dialogue blips) timer
sfx3        equ ram+18         ; channel 3 (the wall thud) timer
jingle_time equ ram+19         ; frames left on the current note
jingle_ptr  equ ram+20         ; two bytes: where the note stream is
dlg_state   equ ram+22         ; 0 off, 1 typing, 2 finished
dlg_stream  equ ram+23         ; two bytes: the stream being typed
dlg_ptr     equ ram+25         ; two bytes: the next character
dlg_col     equ ram+27
dlg_row     equ ram+28
dlg_timer   equ ram+29
dlg_expr    equ ram+30         ; which portrait expression to show

        org 0x0000
        di
        im 1
        jp boot

        ds 0x0038 - $                 ; RST vectors are unused
        reti                          ; the VDP interrupt stays masked

        ds 0x0066 - $
        jp nmi_handler                ; console HOLD / PAUSE button

; ==========================================================================
;  start up
; ==========================================================================
boot:
        ld sp, 0xc3f0
        call ram_clear
        call vdp_init
        call psg_init
        call gfx_upload
        call sprites_hide_all
        call vdp_display_on
        xor a
        ld (paused), a
        ld (nmi_req), a
        ld (prev1), a
        ld (prev_b2), a
        ld (hit_prev), a
        call title_enter
        jp main_loop

ram_clear:
        ld hl, 0xc000
        ld de, 0xc001
        ld bc, 0x03df
        ld (hl), 0
        ldir
        ret

; ==========================================================================
;  main loop - one pass per video frame
; ==========================================================================
main_loop:
        call wait_vblank
        call read_pads
        call check_pause
        ld a, (paused)
        or a
        jr nz, .frame_done
        call sfx_tick
        ld a, (state)
        or a
        jr nz, .not_title
        call tick_title
        jr .frame_done
.not_title:
        dec a
        jr nz, .not_race
        call tick_race
        jr .frame_done
.not_race:
        call tick_over                ; 2 = won, 3 = lost
.frame_done:
        ld a, (pad1)                  ; remembered for the edge detectors
        ld (prev1), a
        jp main_loop

wait_vblank:
        in a, (VDPCTRL)
        and 0x80
        jr z, wait_vblank
        ret

; ==========================================================================
;  title screen
; ==========================================================================
title_enter:
        xor a
        ld (state), a
        call draw_track
        call draw_title_text
        ; park both cars on the grid so the player sees them
        ld a, CAR_X0
        ld (px), a
        ld a, CAR_Y0
        ld (py), a
        ld a, RIVAL_X0
        ld (rx), a
        ld a, RIVAL_Y0
        ld (ry), a
        call update_sprites
        ld a, (pad1)
        ld (prev1), a
        ret

tick_title:
        ld a, (pad1)
        bit 4, a
        jr z, .no
        ld a, (prev1)
        bit 4, a
        jr nz, .no
        call race_start
        ret
.no:
        ret

; ==========================================================================
;  the race
; ==========================================================================
race_start:
        xor a
        ld (laps), a
        ld (rlaps), a
        ld (cpf), a
        ld (hit), a
        ld (rseg), a
        ld a, CAR_X0
        ld (px), a
        ld a, CAR_Y0
        ld (py), a
        ld a, RIVAL_X0
        ld (rx), a
        ld a, RIVAL_Y0
        ld (ry), a
        ld a, 1
        ld (state), a
        call draw_track
        call draw_hud
        call update_sprites
        ld hl, jingle_start
        jp jingle_play

tick_race:
        ld b, CAR_SUBS                ; the square moves CAR_STEP a frame, in
.move:                                ; CAR_SUB steps, so no wall is missed
        push bc
        call move_car
        pop bc
        djnz .move
        call check_cp
        ld a, (state)
        dec a
        ret nz                        ; the race ended on this frame
        call move_rival
        ld a, (state)
        dec a
        ret nz                        ; Susie's third lap ended the race
        jp update_sprites

; ---- the player: 4 directions, walls stop the square ---------------------
move_car:
        xor a
        ld (hit), a
        ; ---- left
        ld a, (pad1)
        bit 2, a
        jr z, .not_left
        ld a, (px)
        sub CAR_SUB
        jr c, .blocked                     ; ran off the byte range
        ld d, a
        ld a, (py)
        ld e, a
        call pos_blocked
        jr c, .blocked
        ld a, d
        ld (px), a
        jr .not_left
.blocked:
        ld a, 1
        ld (hit), a
.not_left:
        ; ---- right
        ld a, (pad1)
        bit 3, a
        jr z, .not_right
        ld a, (px)
        add a, CAR_SUB
        ld d, a
        ld a, (py)
        ld e, a
        call pos_blocked
        jr c, .hit_right
        ld a, d
        ld (px), a
        jr .not_right
.hit_right:
        ld a, 1
        ld (hit), a
.not_right:
        ; ---- up
        ld a, (pad1)
        bit 0, a
        jr z, .not_up
        ld a, (py)
        sub CAR_SUB
        jr c, .hit_up
        ld e, a
        ld a, (px)
        ld d, a
        call pos_blocked
        jr c, .hit_up
        ld a, e
        ld (py), a
        jr .not_up
.hit_up:
        ld a, 1
        ld (hit), a
.not_up:
        ; ---- down
        ld a, (pad1)
        bit 1, a
        jr z, .not_down
        ld a, (py)
        add a, CAR_SUB
        ld e, a
        ld a, (px)
        ld d, a
        call pos_blocked
        jr c, .hit_down
        ld a, e
        ld (py), a
        jr .not_down
.hit_down:
        ld a, 1
        ld (hit), a
.not_down:
        ; ---- bump when we run into a wall (once per contact, not every frame)
        ld a, (hit)
        ld b, a
        ld a, (hit_prev)
        xor b
        and b
        jr z, .quiet
        call sfx_bump
.quiet:
        ld a, (hit)                         ; read it back: the sound code is free to use B
        ld (hit_prev), a
        ret

; D = candidate x, E = candidate y.  Carry set when the square cannot go
; there (outside the track, or inside the middle square).
pos_blocked:
        ld a, d
        cp PX_MIN
        jr c, .bad
        cp PX_MAX + 1
        jr nc, .bad
        ld a, e
        cp PY_MIN
        jr c, .bad
        cp PY_MAX + 1
        jr nc, .bad
        ld a, d                            ; the middle square
        cp BOX_X
        jr c, .ok
        cp BOX_XR
        jr nc, .ok
        ld a, e
        cp BOX_Y
        jr c, .ok
        cp BOX_YB
        jr nc, .ok
.bad:
        scf
        ret
.ok:
        or a
        ret

; ---- lap checkpoints, so you cannot just wiggle over the line ------------
check_cp:
        ld a, (cpf)
        or a
        jr nz, .check1
        ld a, (px)                          ; 0 -> left straight
        cp CP_LEFT
        ret nc
        ld a, 1
        ld (cpf), a
        ret
.check1:
        dec a
        jr nz, .check2
        ld a, (py)                          ; 1 -> top straight
        cp CP_TOP
        ret nc
        ld a, 2
        ld (cpf), a
        ret
.check2:
        dec a
        jr nz, .finish
        ld a, (px)                          ; 2 -> right straight
        cp CP_RIGHT
        ret c
        ld a, 3
        ld (cpf), a
        ret
.finish:
        ld a, (py)                          ; 3 -> the finish line
        cp (TRACK_IN_B + 1) * 8
        ret c
        ld a, (px)
        cp FINISH_X - 7                     ; front of the square on the line
        ret c
        cp FINISH_RIGHT
        ret nc
        xor a
        ld (cpf), a
        ld a, (laps)
        inc a
        ld (laps), a
        call sfx_lap
        call draw_hud
        ld a, (laps)
        cp LAPS_TO_WIN
        ret nz
        call race_win
        ret

; ---- Susie: follows the outside lane clockwise --------------------------
move_rival:
        ld a, (rseg)
        or a
        jr nz, .seg1
        ld a, (rx)                          ; bottom straight, heading left
        cp RIVAL_LINE + 1
        jr c, .move1                        ; already past the line
        sub RIVAL_STEP
        cp RIVAL_LINE
        jr nc, .store1                      ; not over it yet
        ld (rx), a                          ; that is a lap
        jp rival_lap
.move1:
        sub RIVAL_STEP
.store1:
        cp RIVAL_LEFT
        jr c, .turn1
        ld (rx), a
        ret
.turn1:
        ld a, RIVAL_LEFT
        ld (rx), a
        ld a, 1
        ld (rseg), a
        ret
.seg1:
        dec a
        jr nz, .seg2
        ld a, (ry)                          ; left straight, heading up
        sub RIVAL_STEP
        cp RIVAL_TOP
        jr c, .turn2
        ld (ry), a
        ret
.turn2:
        ld a, RIVAL_TOP
        ld (ry), a
        ld a, 2
        ld (rseg), a
        ret
.seg2:
        dec a
        jr nz, .seg3
        ld a, (rx)                          ; top straight, heading right
        add a, RIVAL_STEP
        cp RIVAL_RIGHT
        jr nc, .turn3
        ld (rx), a
        ret
.turn3:
        ld a, RIVAL_RIGHT
        ld (rx), a
        ld a, 3
        ld (rseg), a
        ret
.seg3:
        ld a, (ry)                          ; right straight, heading down
        add a, RIVAL_STEP
        cp RIVAL_BOTTOM
        jr nc, .turn4
        ld (ry), a
        ret
.turn4:
        ld a, RIVAL_BOTTOM
        ld (ry), a
        xor a
        ld (rseg), a
        ret

rival_lap:
        ld a, (rlaps)
        inc a
        ld (rlaps), a
        call draw_hud
        ld a, (rlaps)
        cp LAPS_TO_WIN
        ret nz
        jp race_lose

; ==========================================================================
;  the two end screens (the result is written inside the middle square)
; ==========================================================================
race_win:
        ld a, 2
        ld (state), a
        ld hl, dlg_win
        xor a                             ; expression 0: Susie is sulking
        call end_screen
        ld hl, str_win
        ld b, 13
        ld c, 9
        call draw_text_str
        ld hl, str_press
        ld b, 13
        ld c, 13
        call draw_text_str
        ld hl, jingle_win
        jp jingle_play

race_lose:
        ld a, 3
        ld (state), a
        ld hl, dlg_lose
        ld a, 1                           ; expression 1: Susie is gloating
        call end_screen
        ld hl, str_susiewins
        ld b, 12
        ld c, 9
        call draw_text_str
        ld hl, str_press
        ld b, 13
        ld c, 13
        call draw_text_str
        ld hl, jingle_lose
        jp jingle_play

; HL = the dialogue stream, A = which portrait expression to show
end_screen:
        ld (dlg_expr), a
        ld (dlg_stream), hl
        call draw_dialog_map
        ld hl, (dlg_stream)
        call dlg_begin
        ld a, (dlg_expr)
        jp sprites_portrait

tick_over:
        call dlg_tick                     ; keep typing
        ld a, (pad1)
        bit 4, a
        jr z, .no
        ld a, (prev1)
        bit 4, a
        ret nz                            ; the button was already down
        ld a, (dlg_state)
        cp 2
        jr z, .leave
        jp dlg_flush                      ; first press: hurry the text up
.leave:
        jp title_enter                    ; then back to the title screen
.no:
        ret

; ==========================================================================
;  drawing
; ==========================================================================
draw_track:
        ld hl, track_map
        ld de, 0x1800
        ld bc, 768
        jp vdp_write

draw_dialog_map:
        ld hl, dialog_map
        ld de, 0x1800
        ld bc, 768
        jp vdp_write

; ==========================================================================
;  the dialogue box: a typewriter that prints one character every other
;  frame with a blip.  A stream is  col, row, "text", 0 ... $FF
; ==========================================================================
dlg_begin:                                ; HL = stream
        ld a, 1
        ld (dlg_state), a
        ld a, 2
        ld (dlg_timer), a
        jp dlg_next_line

dlg_next_line:                            ; HL = col, row, text...
        ld a, (hl)
        ld (dlg_col), a
        inc hl
        ld a, (hl)
        ld (dlg_row), a
        inc hl
        ld (dlg_ptr), hl
        ret

dlg_tick:                                 ; once a frame
        ld a, (dlg_state)
        dec a
        ret nz                            ; 0 = nothing on screen, 2 = done
        ld a, (dlg_timer)
        or a
        jr z, dlg_step
        dec a
        ld (dlg_timer), a
        ret

dlg_step:                                 ; print one more character
        ld a, (dlg_state)
        dec a
        ret nz
        ld a, 2
        ld (dlg_timer), a
        ld hl, (dlg_ptr)
        ld a, (hl)
        or a
        jr nz, .print
        inc hl                            ; the line ended
        ld a, (hl)
        cp 0xff
        jr z, .done
        jp dlg_next_line                  ; on to the next line
.done:
        ld a, 2
        ld (dlg_state), a
        ret
.print:
        sub 0x20
        add a, TILE_FONT
        ld c, a                           ; the tile
        ld a, (dlg_col)
        ld b, a
        ld a, (dlg_row)
        ld e, a
        ld a, c
        ld c, e
        call put_tile
        ld hl, (dlg_ptr)
        inc hl
        ld (dlg_ptr), hl
        ld a, (dlg_col)
        inc a
        ld (dlg_col), a
        jp sfx_blip

dlg_flush:                                ; fill the box in at once
        ld b, 120
.loop:
        push bc
        call dlg_step
        pop bc
        ld a, (dlg_state)
        cp 2
        ret z
        djnz .loop
        ret

; the title text table from gfx.asm: col, row, text, 0 ... $FF
draw_title_text:
        ld hl, title_text
.next:
        ld a, (hl)
        cp 0xff
        ret z
        ld b, a
        inc hl
        ld c, (hl)
        inc hl
        push hl
        call draw_text_str
        pop hl
.skip:
        ld a, (hl)
        inc hl
        or a
        jr nz, .skip
        jr .next

; HL = zero terminated text, B = column, C = row
draw_text_str:
        call text_addr
.loop:
        ld a, (hl)
        or a
        ret z
        sub 0x20
        add a, TILE_FONT
        out (VDPDATA), a
        inc hl
        jr .loop

; A = tile, B = column, C = row
put_tile:
        push af
        call text_addr
        pop af
        out (VDPDATA), a
        ret

; point the VDP at (B, C) in the name table
text_addr:
        push af
        push hl
        ld l, c
        ld h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl                    ; row * 32
        ld a, b
        add a, l
        ld l, a
        ld a, h
        adc a, 0
        ld h, a
        ld de, 0x1800
        add hl, de
        call vdp_setaddr
        pop hl
        pop af
        ret

; the lap counters live inside the middle square
draw_hud:
        ld hl, str_lap
        ld b, HUD1_COL
        ld c, HUD1_ROW
        call draw_text_str
        ld a, (laps)
        inc a                              ; you are on lap 1..3
        cp LAPS_TO_WIN + 1
        jr c, .l
        ld a, LAPS_TO_WIN
.l:
        add a, 0x30
        sub 0x20 - TILE_FONT
        ld b, HUD1_COL + 4
        ld c, HUD1_ROW
        call put_tile
        ld hl, str_of3
        ld b, HUD1_COL + 5
        ld c, HUD1_ROW
        call draw_text_str

        ld hl, str_susie
        ld b, HUD2_COL
        ld c, HUD2_ROW
        call draw_text_str
        ld a, (rlaps)
        cp LAPS_TO_WIN
        jr c, .r
        ld a, LAPS_TO_WIN - 1
.r:
        inc a
        add a, 0x30
        sub 0x20 - TILE_FONT
        ld b, HUD2_COL + 6
        ld c, HUD2_ROW
        call put_tile
        ld hl, str_of3
        ld b, HUD2_COL + 7
        ld c, HUD2_ROW
        jp draw_text_str

; ---- sprites: the player (white) and Susie (magenta) ---------------------
update_sprites:
        ld hl, 0x1b00
        call vdp_setaddr
        ld a, (py)
        dec a                              ; sprites sit one line lower
        out (VDPDATA), a
        ld a, (px)
        out (VDPDATA), a
        xor a
        out (VDPDATA), a                   ; pattern 0
        ld a, 0x0f                         ; white
        out (VDPDATA), a
        ld a, (ry)
        dec a
        out (VDPDATA), a
        ld a, (rx)
        out (VDPDATA), a
        xor a
        out (VDPDATA), a
        ld a, 0x0d                         ; light magenta
        out (VDPDATA), a
        ld a, 0xd0                         ; end of the sprite list
        out (VDPDATA), a
        ret

sprites_portrait:                         ; A = 0 sulking, 1 gloating
        or a
        ld hl, portrait_sat_1
        jr nz, .go
        ld hl, portrait_sat_0
.go:
        ld de, 0x1b00
        ld bc, 81
        jp vdp_write

sprites_hide_all:
        ld hl, 0x1b00
        call vdp_setaddr
        ld b, 32
        ld a, 0xd0
.h:
        out (VDPDATA), a
        djnz .h
        ret

; ==========================================================================
;  VDP set up (registers first, then VRAM - see the pong README)
; ==========================================================================
vdp_setaddr:
        ld a, l
        out (VDPCTRL), a
        ld a, h
        or 0x40
        out (VDPCTRL), a
        ret

; HL = source, DE = VRAM destination, BC = byte count
vdp_write:
        push hl
        ld h, d
        ld l, e
        call vdp_setaddr
        pop hl
.loop:
        ld a, (hl)
        out (VDPDATA), a
        inc hl
        dec bc
        ld a, b
        or c
        jr nz, .loop
        ret

vdp_init:
        ld hl, vdp_regs
        ld c, 0
        ld b, 8
.rl:
        ld a, (hl)
        out (VDPCTRL), a
        ld a, c
        or 0x80
        out (VDPCTRL), a
        inc hl
        inc c
        djnz .rl
        ld hl, 0x0000
        call vdp_setaddr
        ld bc, 0x4000
.clr:
        xor a
        out (VDPDATA), a
        dec bc
        ld a, b
        or c
        jr nz, .clr
        ret

vdp_display_on:
        ld a, 0xe0                         ; 16K, display on, frame IRQ flag
        out (VDPCTRL), a
        ld a, 0x81
        out (VDPCTRL), a
        ret

vdp_regs:
        db 0x00                            ; R0: Graphics I
        db 0xa0                            ; R1: 16K + IRQ flag, display off
        db 0x06                            ; R2: name table    $1800
        db 0x80                            ; R3: colour table  $2000
        db 0x00                            ; R4: patterns      $0000
        db 0x36                            ; R5: sprite attrs  $1B00
        db 0x07                            ; R6: sprite pats   $3800
        db 0x00                            ; R7: black backdrop

gfx_upload:
        ld hl, pattern_data
        ld de, 0x0000
        ld bc, PATTERN_COUNT * 8
        call vdp_write
        ld hl, 0x2000                      ; colour table: white on black
        call vdp_setaddr
        ld b, 32
        ld a, 0xf1
.cl:
        out (VDPDATA), a
        djnz .cl
        ld hl, sprite_patterns
        ld de, 0x3800
        ld bc, 8
        call vdp_write
        ld hl, portrait_data              ; Susie's two portraits
        ld de, 0x3800 + PORTRAIT_BASE * 8
        ld bc, 40 * 8
        jp vdp_write

; ==========================================================================
;  sound (SN76489 channel 0)
; ==========================================================================
psg_init:
        ld a, 0x9f
        out (PSG), a
        ld a, 0xbf
        out (PSG), a
        ld a, 0xdf
        out (PSG), a
        ld a, 0xff
        out (PSG), a
        ret

; HL = 10 bit divider (3579545 / (32 * N) Hz), B = $80 channel 0 / $A0
; channel 1, A = volume attenuation (0 loudest, 15 silent)
psg_tone:
        push af
        ld a, l
        and 0x0f
        or b
        out (PSG), a
        ld a, h
        add a, a
        add a, a
        add a, a
        add a, a
        ld c, a
        ld a, l
        rrca
        rrca
        rrca
        rrca
        and 0x0f
        or c
        and 0x3f
        out (PSG), a
        pop af
        or b
        or 0x10
        out (PSG), a
        ret

; ---- one shot on channel 0: HL = divider, A = length in frames ----------
sfx_ch0:
        push af
        ld b, 0x80
        xor a
        call psg_tone
        pop af
        ld (sfx_time), a
        ret

; ---- one shot on channel 1: HL = divider, A = length in frames ----------
sfx_ch1:
        push af
        ld b, 0xa0
        ld a, 2                           ; the blips are a bit quieter
        call psg_tone
        pop af
        ld (sfx1), a
        ret

; ---- the wall thud: noise on channel 3, low rate, very short ------------
sfx_bump:
        ld a, 0xe6                        ; white noise, slowest rate
        out (PSG), a
        ld a, 0xf2                        ; channel 3 volume
        out (PSG), a
        ld a, 3
        ld (sfx3), a
        ret

sfx_lap:                                  ; a lap: a short high blip
        ld hl, 340
        ld a, 6
        jp sfx_ch0

sfx_blip:                                 ; one dialogue character, ~1.2 kHz
        ld hl, 95
        ld a, 1
        jp sfx_ch1

; ---- the little note player behind the jingles -------------------------
; a stream is: frames, divider low, divider high, ... ending with a 0 count
jingle_play:                              ; HL = stream
        ld a, (hl)
        or a
        ret z
        ld (jingle_ptr), hl
        ld a, 1
        ld (jingle_time), a               ; the first note starts next frame
        ret

jingle_tick:
        ld a, (jingle_time)
        or a
        ret z
        dec a
        ld (jingle_time), a
        ret nz
        ld hl, (jingle_ptr)
        ld a, (hl)
        or a
        jr nz, .note
        ld a, 0x9f                        ; the stream ended
        out (PSG), a
        ret
.note:
        inc hl
        ld e, (hl)
        inc hl
        ld d, (hl)
        inc hl
        ld (jingle_ptr), hl
        ld (jingle_time), a
        ex de, hl                         ; HL = divider
        ld b, 0x80
        xor a
        jp psg_tone

sfx_tick:
        ld a, (sfx_time)                  ; channel 0 one shots
        or a
        jr z, .ch1
        dec a
        ld (sfx_time), a
        jr nz, .ch1
        ld a, 0x9f
        out (PSG), a
.ch1:
        ld a, (sfx1)
        or a
        jr z, .ch3
        dec a
        ld (sfx1), a
        jr nz, .ch3
        ld a, 0xbf
        out (PSG), a
.ch3:
        ld a, (sfx3)
        or a
        jr z, .jingle
        dec a
        ld (sfx3), a
        jr nz, .jingle
        ld a, 0xff
        out (PSG), a
.jingle:
        jp jingle_tick

; ==========================================================================
;  input / pause
; ==========================================================================
read_pads:
        in a, (JOYP1)
        cpl
        ld (pad1), a                       ; b0 up, b1 down, b2 left,
        ret                                ; b3 right, b4 button 1, b5 button 2

nmi_handler:
        push af
        ld a, (nmi_req)
        inc a
        ld (nmi_req), a
        pop af
        retn

check_pause:
        ld a, (pad1)
        and 0x20                           ; joypad 1 button 2
        ld b, a
        ld a, (prev_b2)
        xor b
        and b
        jr z, .hold
        call pause_toggle
.hold:
        ld a, b
        ld (prev_b2), a
        ld a, (nmi_req)                    ; console HOLD button
        or a
        ret z
        xor a
        ld (nmi_req), a
        ; fall through

pause_toggle:
        xor a
        ld (sfx_time), a
        ld a, 0x9f
        out (PSG), a
        ld a, (paused)
        xor 1
        ld (paused), a
        ret

; ==========================================================================
;  text
; ==========================================================================
str_lap:       db "LAP ", 0
str_of3:       db "/3", 0
str_susie:     db "SUSIE ", 0
str_win:       db "YOU WIN", 0
str_susiewins: db "SUSIE WINS", 0
str_press:     db "PRESS 1", 0

; ---- the little tunes.  A stream is  frames, divider low, divider high
;      and a zero frame count ends it.  The dividers are 3579545/(32*N) Hz.
NOTE_C4        equ 428
NOTE_E4        equ 339
NOTE_G4        equ 285
NOTE_C5        equ 214
NOTE_E5        equ 170
NOTE_G5        equ 143
NOTE_C6        equ 107

jingle_start:                             ; race start
        db 4, NOTE_G5 & 0xff, NOTE_G5 >> 8
        db 10, NOTE_C6 & 0xff, NOTE_C6 >> 8
        db 0

jingle_win:                               ; a rising sting
        db 5, NOTE_C5 & 0xff, NOTE_C5 >> 8
        db 5, NOTE_E5 & 0xff, NOTE_E5 >> 8
        db 5, NOTE_G5 & 0xff, NOTE_G5 >> 8
        db 18, NOTE_C6 & 0xff, NOTE_C6 >> 8
        db 0

jingle_lose:                              ; and a falling one
        db 8, NOTE_G4 & 0xff, NOTE_G4 >> 8
        db 8, NOTE_E4 & 0xff, NOTE_E4 >> 8
        db 20, NOTE_C4 & 0xff, NOTE_C4 >> 8
        db 0

; ==========================================================================
;  graphics data (generated by tools/gen_gfx.py)
; ==========================================================================
        include "gfx.asm"

        ds 0x4000 - $, 0xff
