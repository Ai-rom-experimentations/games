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
SUSIE_STEP  equ 2              ; half the player's pace, and the knight's
                               ; is KNIGHT_STEP (above)

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

; ---- the secret mode -----------------------------------------------------
KNIGHT_STEP equ 3              ; the Roaring Knight is quicker than Susie
SHIFT_FONT  equ 141            ; the font moved one pixel right (patterns)
SWOON_TILE  equ 208            ; four glyphs in a red colour group
SWOON_SLOW  equ 120            ; frames of the slow attack before the cut
SWOON_HOLD  equ 160            ; how long the SWOON stays on screen
SW_CX       equ 120            ; where the car gets cut in half (the swoon
SW_CY       equ 104            ; doubles the sprite size, so it is 16x16)
SW_ROW      equ 11             ; and where the red word goes, above it
SW_COL      equ 13

; ---- RAM (1 KB at $C000, mirrored) ---------------------------------------
ram         equ 0xc000
state       equ ram+0          ; 0 title, 1 race, 2 won, 3 lost,
                               ; 4 the knight's line, 5 the swoon
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
dlg_count   equ ram+30         ; characters of the line printed so far
mode        equ ram+31         ; 0 Susie, 1 the Roaring Knight
rstep       equ ram+32         ; how far the rival moves each frame
font_ofs    equ ram+33         ; 0, or 128 for the wobbling copy of the font
shake       equ ram+34         ; countdown for that wobble / for the swoon
swoon_phase equ ram+35
swoon_time  equ ram+36
end_sat     equ ram+37         ; two bytes: sprite table for the end screen
ai_x        equ ram+39         ; the knight's afterimages (four slots, three
ai_y        equ ram+43         ; used: see spr_knight)
sw_pitch    equ ram+47         ; two bytes: the swoon's rising attack
sw_vol      equ ram+49
sw_gap      equ ram+50         ; how far the car has been opened up
sw_crash    equ ram+51         ; the shattering glass

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
        ld (font_ofs), a
        ld (mode), a
        ld a, 0xe0                        ; normal sprite size again
        out (VDPCTRL), a
        ld a, 0x81
        out (VDPCTRL), a
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
        jr z, .nothing                     ; button 1 is not down
        ld a, (prev1)
        bit 4, a
        ret nz                             ; ... it was already down
        ld a, (pad1)                       ; button 2 held as well?  That is the
        and 0x20                           ; secret: either both at once or 2,
        jr nz, .secret                     ; then 1, which is how two thumbs
        xor a                              ; press a pad
        ld (mode), a
        jp race_start
.secret:
        ld a, 1
        ld (mode), a
        jp race_start
.nothing:
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
        ld (font_ofs), a
        ld (shake), a
        ld a, CAR_X0
        ld (px), a
        ld a, CAR_Y0
        ld (py), a
        ld a, RIVAL_X0
        ld (rx), a
        ld (ry), a
        ld (ai_x), a                       ; the afterimage trail starts on
        ld (ai_x+1), a                     ; the grid, not up in the corner
        ld (ai_x+2), a
        ld (ai_x+3), a
        ld a, RIVAL_Y0
        ld (ry), a
        ld (ai_y), a
        ld (ai_y+1), a
        ld (ai_y+2), a
        ld (ai_y+3), a
        ld a, (mode)
        or a
        ld a, SUSIE_STEP
        jr z, .step
        ld a, KNIGHT_STEP
.step:
        ld (rstep), a
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
        ld a, (mode)
        or a
        jr z, .rival
        call rival_trail              ; his old place, before he leaves it
.rival:
        call move_rival
        ld a, (state)
        dec a
        ret nz                        ; the rival's third lap ended the race
.draw:
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
        ld a, (rstep)                     ; Susie 2, the knight 3
        ld b, a
        ld a, (rseg)
        or a
        jr nz, .seg1
        ld a, (rx)                          ; bottom straight, heading left
        cp RIVAL_LINE + 1
        jr c, .move1                        ; already past the line
        sub b
        cp RIVAL_LINE
        jr nc, .store1                      ; not over it yet
        ld (rx), a                          ; that is a lap
        jp rival_lap
.move1:
        sub b
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
        sub b
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
        add a, b
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
        add a, b
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
        ld a, (mode)
        or a
        jr nz, .knight
        ld hl, dlg_win                    ; Susie has something to say ...
        ld de, portrait_sat_0             ; ... and she is sulking
        call end_screen
        jr .finish
.knight:
        ld hl, dlg_knight_win             ; he cannot believe it
        ld de, knight_sat_1               ; ... and his visor hangs open
        call end_screen_spiked
        ld a, 16
        ld (shake), a                     ; the text starts to wobble
.finish:
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
        ld a, (mode)
        or a
        jr nz, .knight
        ld a, 3
        ld (state), a
        ld hl, dlg_lose                   ; she is not impressed
        ld de, portrait_sat_1             ; ... and she is gloating
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

.knight:
        ld a, 4
        ld (state), a
        ld hl, dlg_knight_lose            ; "HEH... AS EXPECTED."
        ld de, knight_sat_0
        call end_screen
        ld hl, str_knightwins
        ld b, 11
        ld c, 9
        call draw_text_str
        ld a, 70
        ld (shake), a                     ; a beat to read it, then the swoon
        ld hl, jingle_lose
        jp jingle_play

; HL = the dialogue stream, DE = the sprite table for the portrait
end_screen:
        ld (dlg_stream), hl
        ld (end_sat), de
        call draw_dialog_map
        jr end_screen_go

end_screen_spiked:                        ; the knight's box has spikes on it
        ld (dlg_stream), hl
        ld (end_sat), de
        call draw_spiked_box
end_screen_go:
        ld hl, (dlg_stream)
        call dlg_begin
        ld hl, (end_sat)
        ld de, 0x1b00
        ld bc, 81
        jp vdp_write

; the ordinary box, with a row of spikes instead of its top and bottom line
draw_spiked_box:
        call draw_dialog_map
        ld a, TILE_SPIKE_U
        ld b, DLGBOX_L + 1
        ld c, DLGBOX_T
        ld d, DLGBOX_R - DLGBOX_L - 1
        call fill_row
        ld a, TILE_SPIKE_D
        ld b, DLGBOX_L + 1
        ld c, DLGBOX_B
        ld d, DLGBOX_R - DLGBOX_L - 1
        jp fill_row

; A = tile, B = first column, C = the row, D = how many cells
fill_row:
        call text_addr
.next:
        out (VDPDATA), a
        dec d
        jr nz, .next
        ret

tick_over:
        ld a, (state)
        cp 4
        jr z, tick_knight_lost
        cp 5
        jp z, tick_swoon
        ld a, (mode)
        or a
        call nz, shake_tick               ; the knight's text will not sit still
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

; ---- he has said his line.  A moment later the swoon lands
tick_knight_lost:
        call dlg_tick
        ld a, (dlg_state)
        cp 2
        jr nz, .keys
        ld a, (shake)
        or a
        jr z, swoon_start
        dec a
        ld (shake), a
        ret
.keys:
        ld a, (pad1)
        bit 4, a
        ret z
        ld a, (prev1)
        bit 4, a
        ret nz
        jp dlg_flush

; ==========================================================================
;  the swoon: black screen, a wide white slash, a slow attack that swells,
;  then glass, the word SWOON in red, and the car opened down the middle
; ==========================================================================
swoon_start:
        ld a, 5
        ld (state), a
        xor a
        ld (swoon_phase), a
        ld (sfx_time), a                  ; nothing else may use the sound chip
        ld (jingle_time), a
        ld a, SWOON_SLOW
        ld (swoon_time), a
        ld hl, 1000
        ld (sw_pitch), hl
        ld a, 1                           ; and it swells from almost nothing
        ld (sw_vol), a
        xor a
        ld (sw_gap), a
        ld a, 0xe1                        ; doubled sprites: the car is 16x16
        out (VDPCTRL), a                  ; when it is cut open
        ld a, 0x81
        out (VDPCTRL), a
        call sw_clear
        call sw_slash
        call sw_car
        ; the long rising note starts here and is stepped in tick_swoon
        jp psg_sweep

tick_swoon:
        ld a, (swoon_phase)
        or a
        jr z, .attack
        dec a
        jr z, .cut
        jp .hold
.attack:
        call psg_sweep
        ld a, (swoon_time)
        dec a
        ld (swoon_time), a
        ret nz
        ld a, 1                           ; the cut lands
        ld (swoon_phase), a
        ld a, 30
        ld (swoon_time), a
        ld a, 26
        ld (sw_crash), a
        call sw_word
        jp sfx_glass
.cut:
        call glass_tick
        ld a, (sw_gap)
        cp 5
        jr nc, .wait
        inc a
        ld (sw_gap), a
        call sw_car
.wait:
        ld a, (swoon_time)
        dec a
        ld (swoon_time), a
        ret nz
        ld a, 2
        ld (swoon_phase), a
        ld a, SWOON_HOLD
        ld (swoon_time), a
        ret
.hold:
        ld a, (swoon_time)
        dec a
        ld (swoon_time), a
        ret nz
        jp title_enter

; ---- a black screen
sw_clear:
        ld hl, 0x1800
        call vdp_setaddr
        ld bc, 768
.clr:
        xor a
        out (VDPDATA), a
        dec bc
        ld a, b
        or c
        jr nz, .clr
        ret

; ---- three diagonal lines, eight pixels apart, running down the screen
sw_slash:
        ld c, 0                           ; which of the three
.chain:
        ld d, 0                           ; the column
.col:
        ld a, d
        add a, c
        sub 3                             ; row = col + chain - 3
        cp 24
        jr nc, .next                      ; that cell is off the bottom
        ld e, a                           ; the row
        ld a, TILE_SLASH
        push bc
        push de
        ld b, d
        ld c, e
        call put_tile
        pop de
        pop bc
.next:
        inc d
        ld a, d
        cp 32
        jr c, .col
        inc c
        ld a, c
        cp 3
        jr c, .chain
        ret

; ---- the car, as two halves that can slide apart
sw_car:
        ld hl, 0x1b00
        call vdp_setaddr
        ld a, SW_CY - 1
        out (VDPDATA), a
        ld a, (sw_gap)
        ld c, a
        ld a, SW_CX
        sub c
        out (VDPDATA), a
        ld a, SPR_HALF_L
        out (VDPDATA), a
        ld a, 0x0f
        out (VDPDATA), a
        ld a, SW_CY - 1
        out (VDPDATA), a
        ld a, SW_CX + 8
        add a, c
        out (VDPDATA), a
        ld a, SPR_HALF_R
        out (VDPDATA), a
        ld a, 0x0f
        out (VDPDATA), a
        ld a, 0xd0
        out (VDPDATA), a
        ret

; ---- the word, in the red colour group
sw_word:
        ld b, SW_COL
        ld c, SW_ROW
        ld hl, swoon_word
.next:
        ld a, (hl)
        cp 0xff
        ret z
        push hl
        call put_tile
        pop hl
        inc hl
        inc b
        jr .next

; ---- the slow attack: one long note that climbs for two seconds while its
;      volume swells, so that the cut feels like it is coming
psg_sweep:
        ld hl, (sw_pitch)
        ld de, -6
        add hl, de
        ld (sw_pitch), hl
        ld a, (swoon_time)
        and 0x07
        jr nz, .play
        ld a, (sw_vol)                    ; a little louder every eighth frame,
        cp 14                             ; which fills the fifteen levels the
        jr nc, .play                      ; chip has over the two seconds
        inc a
        ld (sw_vol), a
.play:
        ld hl, (sw_pitch)
        ld b, 0x80
        ld a, (sw_vol)
        jp psg_tone

; ---- and the glass
sfx_glass:
        ld a, 0xe4                        ; white noise, fastest rate
        out (PSG), a
        ld a, 0xf0
        out (PSG), a
        ret

glass_tick:
        ld a, (sw_crash)
        or a
        ret z
        dec a
        ld (sw_crash), a
        jr nz, .noise
        ld a, 0xff
        out (PSG), a
        ret
.noise:
        and 0x03                          ; the shards change pitch as they fall
        or 0xe4
        out (PSG), a
        ld a, (sw_crash)
        srl a
        srl a
        srl a
        or 0xf0
        out (PSG), a
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
        xor a
        ld (dlg_count), a
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
        push af
        ld a, (dlg_col)
        ld b, a
        ld a, (dlg_row)
        ld c, a
        pop af
        call dlg_char
        ld hl, (dlg_ptr)
        inc hl
        ld (dlg_ptr), hl
        ld a, (dlg_col)
        inc a
        ld (dlg_col), a
        ld a, (dlg_count)
        inc a
        ld (dlg_count), a
        jp sfx_blip

; A = the character, B = column, C = row.  The tile comes from whichever
; copy of the font is selected, which is how the text is made to wobble.
dlg_char:
        sub 0x20
        add a, TILE_FONT
        ld e, a
        ld a, (font_ofs)
        add a, e
        jp put_tile

; reprint everything that has been typed so far, in the current font
redraw_dialog:
        ld hl, (dlg_stream)
        ld a, (dlg_count)
        or a
        ret z
        ld b, a
.line:
        ld d, (hl)                        ; this line starts at ...
        ld a, d
        cp 0xff
        ret z
        inc hl
        ld e, (hl)                        ; ... this row
        inc hl
.char:
        ld a, (hl)
        or a
        jr z, .next_line
        push hl
        push de
        push bc
        ld a, d
        ld b, a
        ld c, e
        ld a, (hl)
        call dlg_char
        pop bc
        pop de
        pop hl
        inc hl
        inc d
        dec b
        ret z                             ; that is as far as the typewriter got
        jr .char
.next_line:
        inc hl
        ld a, (hl)
        cp 0xff
        ret z
        jr .line

; ---- the knight's text does not sit still -------------------------------
shake_tick:
        ld a, (shake)
        or a
        jr z, .wobble
        dec a
        ld (shake), a
        ret
.wobble:
        ld a, 14
        ld (shake), a
        ld a, (font_ofs)
        xor 128                           ; between the font and its shifted copy
        ld (font_ofs), a
        call redraw_dialog
        ld hl, str_win
        ld b, 13
        ld c, 9
        call draw_text_str
        ld hl, str_press
        ld b, 13
        ld c, 13
        jp draw_text_str

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
        push af
        ld a, (font_ofs)
        ld e, a
        pop af
        add a, e
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
        ld d, HUD2_COL + 6                 ; where the lap digit goes
        ld a, (mode)
        or a
        jr z, .name
        ld hl, str_knight
        inc d                              ; his name has no space in it
.name:
        ld b, HUD2_COL
        ld c, HUD2_ROW
        push de
        call draw_text_str
        pop de
        ld a, (rlaps)
        cp LAPS_TO_WIN
        jr c, .r
        ld a, LAPS_TO_WIN - 1
.r:
        inc a
        add a, 0x30
        sub 0x20 - TILE_FONT
        ld b, d
        ld c, HUD2_ROW
        push de
        call put_tile
        pop de
        inc d
        ld hl, str_of3
        ld b, d
        ld c, HUD2_ROW
        jp draw_text_str

; ---- sprites: the player (white) and the rival ---------------------------
update_sprites:
        ld a, (mode)
        or a
        jr nz, spr_knight
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

rival_trail:                              ; shuffle the knight's afterimages
        ld a, (ai_x+2)
        ld (ai_x+3), a
        ld a, (ai_x+1)
        ld (ai_x+2), a
        ld a, (ai_x)
        ld (ai_x+1), a
        ld a, (rx)
        ld (ai_x), a
        ld a, (ai_y+2)
        ld (ai_y+3), a
        ld a, (ai_y+1)
        ld (ai_y+2), a
        ld a, (ai_y)
        ld (ai_y+1), a
        ld a, (ry)
        ld (ai_y), a
        ret

; the secret race.  The earliest sprite in the table wins any overlap, so the
; order matters: you, then the knight, then his afterimages - and only two of
; those, because four sprites is all a TMS9918A shows on one scanline.
spr_knight:
        ld hl, 0x1b00
        call vdp_setaddr
        ld a, (py)
        dec a
        out (VDPDATA), a
        ld a, (px)
        out (VDPDATA), a
        ld a, SPR_SOLID
        out (VDPDATA), a
        ld a, 0x0f
        out (VDPDATA), a
        ld a, (ry)
        dec a
        out (VDPDATA), a
        ld a, (rx)
        out (VDPDATA), a
        ld a, SPR_KNIGHT
        out (VDPDATA), a
        ld a, 0x0f                             ; black car, white outline
        out (VDPDATA), a
        ld c, 2
        ld hl, ai_x + 2
        ld de, ai_y + 2
.trail:
        dec hl
        dec e
        ld a, (de)
        dec a
        out (VDPDATA), a
        ld a, (hl)
        out (VDPDATA), a
        ld a, SPR_KNIGHT
        out (VDPDATA), a
        ld a, 0x0e                             ; grey: the afterimage
        out (VDPDATA), a
        dec c
        jr nz, .trail
        ld a, 0xd0
        out (VDPDATA), a
        ret

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
        ld hl, 0x2000 + 26                 ; ... except one group, which is red
        call vdp_setaddr
        ld a, 0x81
        out (VDPDATA), a
        ld hl, sprite_patterns              ; solid, outline, two halves
        ld de, 0x3800
        ld bc, 32
        call vdp_write
        ld hl, portrait_data                ; Susie and the knight, 2 faces each
        ld de, 0x3800 + PORTRAIT_BASE * 8
        ld bc, 80 * 8
        call vdp_write
        ; fall through

; ---- the pattern sets only the secret mode needs ------------------------
; a copy of the font one pixel to the right (so the text can wobble without
; moving whole cells) and four glyphs in the red colour group for SWOON
font_extra:
        ld hl, SHIFT_FONT * 8
        call vdp_setaddr
        ld hl, pattern_data + TILE_FONT * 8
        ld c, 2
.bank:
        ld b, 0
.byte:
        ld a, (hl)
        srl a
        out (VDPDATA), a
        inc hl
        djnz .byte
        dec c
        jr nz, .bank
        ld hl, SWOON_TILE * 8
        call vdp_setaddr
        ld hl, swoon_chars
.glyph:
        ld a, (hl)
        or a
        ret z
        push hl
        sub 32
        add a, TILE_FONT
        ld l, a
        ld h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        ld de, pattern_data
        add hl, de
        ld b, 8
.copy:
        ld a, (hl)
        out (VDPDATA), a
        inc hl
        djnz .copy
        pop hl
        inc hl
        jr .glyph

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
        ld a, (state)                      ; on the title button 2 is half of
        or a                               ; the secret code, not a pause
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
str_knight:    db "KNIGHT", 0
str_knightwins: db "KNIGHT WINS", 0
swoon_chars:   db "SWON", 0
swoon_word:    db SWOON_TILE, SWOON_TILE+1, SWOON_TILE+2, SWOON_TILE+2
               db SWOON_TILE+3, 0xff
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
