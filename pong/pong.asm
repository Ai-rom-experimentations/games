; ==========================================================================
;  P O N G  -  Sega SG-1000 (TMS9918A / SN76489 / Z80)
; ==========================================================================
;  A close reconstruction of Atari's 1972 arcade Pong:
;
;    * dashed border top and bottom, dashed centre net
;    * chunky 7-segment score digits, two digits per side (tens blank < 10)
;    * 4x24 paddles, 4x4 square ball, ball angle depends on where it is hit
;    * ball speeds up on every paddle hit, bounces off the top/bottom walls
;    * service after a point: the ball is served to the player who lost it
;    * first player to 11 wins
;    * square-wave blips on the SN76489 (paddle, wall, point)
;
;  Two players use the two joypads (P2's up/down live in port $DC bits 6-7,
;  which is how the SG-1000 wires the second controller).  "1 PLAYER"
;  hands the right paddle to a simple, beatable CPU.
;
;  Controls:  joypad up/down = move paddle, 1 = start / select,
;             PAUSE button on the console = freeze / unfreeze.
; ==========================================================================

VDPDATA  equ 0xbe
VDPCTRL  equ 0xbf
PSG      equ 0x7f
JOYP1    equ 0xdc                ; player 1 + player 2 up/down
JOYP2    equ 0xdd                ; player 2 buttons, left/right

; ---- court geometry (256x192 pixels) -------------------------------------
PADDLE_H    equ 24
PADDLE_MIN  equ 8              ; topmost paddle y
PADDLE_MAX  equ 160            ; lowest paddle y (160+24 = 184)
PADDLE_STEP equ 3              ; pixels per frame for a human paddle
PLX         equ 20             ; left paddle x
PRX         equ 232            ; right paddle x
BALL_SIZE   equ 4              ; the ball is a 4x4 square, like the arcade
BALL_MIN_Y  equ 8
BALL_MAX_Y  equ 180
BALL_HOME_X equ 126
BALL_HOME_Y equ 92
WIN_SCORE   equ 11

; ---- RAM (the SG-1000 has 1 KB, mirrored over $C000-$FFFF) ----------------
ram         equ 0xc000
state       equ ram+0          ; 0 = title, 1 = playing, 2 = game over
mode        equ ram+1          ; 1 = one player (CPU on the right), 2 = two
menu_sel    equ ram+2          ; 0 = 1 player, 1 = 2 players
score1      equ ram+3
score2      equ ram+4
winner      equ ram+5
p1y         equ ram+6
p2y         equ ram+7
bx          equ ram+8
by          equ ram+9
bdx         equ ram+10         ; signed
bdy         equ ram+11         ; signed
serve_t     equ ram+12
sfx_time    equ ram+13
pad1        equ ram+14
prev1       equ ram+16
nmi_req     equ ram+17
paused      equ ram+18
tmp_ones    equ ram+19
tmp_tens    equ ram+20
blink       equ ram+21

; ---- name table addresses used at run time -------------------------------
SCORE1_ONES equ 0x1800 + 1*32 + 10
SCORE1_TENS equ 0x1800 + 1*32 + 8
SCORE2_ONES equ 0x1800 + 1*32 + 22
SCORE2_TENS equ 0x1800 + 1*32 + 20
MARK_ROW12  equ 0x1800 + 12*32 + 10
MARK_ROW14  equ 0x1800 + 14*32 + 10

        org 0x0000
        di
        im 1
        jp boot

        ds 0x0038 - $                 ; RST vectors are unused
        reti                          ; the VDP interrupt stays masked

        ds 0x0066 - $
        jp nmi_handler                ; PAUSE button on the console

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
        ld (paused),a
        ld (nmi_req),a
        ld (menu_sel),a
        ld (mode),a
        ld (prev1),a
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
;  main loop - everything runs once per video frame
; ==========================================================================
main_loop:
        call wait_vblank
        call read_pads
        call check_pause
        ld a, (paused)
        or a
        jr z, .running
        call pause_blink
        jp main_loop
.running:
        call sfx_tick
        ld a, (state)
        or a
        jp z, tick_title
        dec a
        jp z, tick_play
        jp tick_over

; wait for the VDP to start the vertical blank (status bit 7)
wait_vblank:
        in a, (VDPCTRL)
        and 0x80
        jr z, wait_vblank
        ret

; while paused the ball blinks, so the freeze is obvious
pause_blink:
        ld a, (blink)
        inc a
        ld (blink), a
        and 0x10
        jr z, .visible
        ld hl, 0x1b00 + 6*4            ; ball sprite entry, y byte
        call vdp_setaddr
        ld a, 0xd0
        out (VDPDATA), a
        ret
.visible:
        jp update_sprites

nmi_handler:
        push af
        ld a, (nmi_req)
        inc a
        ld (nmi_req), a
        pop af
        retn

check_pause:
        ld a, (nmi_req)
        or a
        ret z
        xor a
        ld (nmi_req), a
        ld (sfx_time), a               ; stop whatever blip is playing
        ld a, 0x9f
        out (PSG), a
        ld a, (paused)
        xor 1
        ld (paused), a
        ret

; ==========================================================================
;  input
; ==========================================================================
read_pads:
        in a, (JOYP1)
        cpl
        ld (pad1), a                  ; b0 up, b1 down, b2 left, b3 right,
                                      ; b4 button 1, b5 button 2,
                                      ; b6 P2 up, b7 P2 down
        ret
; (player 2's buttons and left/right sit on port $DD, bits 0-3; Pong only
;  needs up/down, which the SG-1000 wires into port $DC)

; ==========================================================================
;  VDP helpers
; ==========================================================================
; HL = VRAM address, select it for writing
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
        ; registers first, with the display still blanked: a real SG-1000
        ; powers up with R1 = $00, so the VDP addresses VRAM in its 4K layout
        ; until R1 bit 7 is written.  Programming R1 up front switches it to
        ; 16K before anything else touches VRAM.
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
        ; now wipe all 16 KB of VRAM while the display is off
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

; unblank the display once the tables are in place
vdp_display_on:
        ld a, 0xe0                    ; 16K, display on, frame interrupt enabled
                                      ; (the Z80 keeps IRQs masked and polls
                                      ;  the status read flag instead)
        out (VDPCTRL), a
        ld a, 0x81
        out (VDPCTRL), a
        ret

vdp_regs:
        db 0x00                       ; R0: Graphics I
        db 0xa0                       ; R1: 16K + interrupt flag, display off
                                      ;  (vdp_display_on sets bit 6 later)
        db 0x06                       ; R2: name table    $1800  (x $400)
        db 0x80                       ; R3: colour table  $2000  (unit $40)
        db 0x00                       ; R4: patterns      $0000  (x $800)
        db 0x36                       ; R5: sprite attrs  $1B00
        db 0x07                       ; R6: sprite pats   $3800
        db 0x00                       ; R7: black backdrop

gfx_upload:
        ld hl, pattern_data
        ld de, 0x0000
        ld bc, PATTERN_COUNT * 8
        call vdp_write
        ; colour table: white on black for every tile group
        ld hl, 0x2000
        call vdp_setaddr
        ld b, 32
        ld a, 0xf1
.cl:
        out (VDPDATA), a
        djnz .cl
        ; sprite patterns
        ld hl, sprite_patterns
        ld de, 0x3800
        ld bc, 16
        jp vdp_write

sprites_hide_all:
        ld hl, 0x1b00
        call vdp_setaddr
        ld b, 32
.h:
        ld a, 0xd0
        out (VDPDATA), a
        xor a
        out (VDPDATA), a
        out (VDPDATA), a
        out (VDPDATA), a
        djnz .h
        ret

; A = screen y, B = x, C = pattern, D = colour
spr_emit:
        dec a
        out (VDPDATA), a
        ld a, b
        out (VDPDATA), a
        ld a, c
        out (VDPDATA), a
        ld a, d
        out (VDPDATA), a
        ret

update_sprites:
        ld hl, 0x1b00
        call vdp_setaddr
        ld d, 0x0f
        ; ---- left paddle (3 sprites tall)
        ld a, (p1y)
        ld b, PLX
        ld c, SPR_PADDLE
        call spr_emit
        ld a, (p1y)
        add a, 8
        ld b, PLX
        ld c, SPR_PADDLE
        call spr_emit
        ld a, (p1y)
        add a, 16
        ld b, PLX
        ld c, SPR_PADDLE
        call spr_emit
        ; ---- right paddle
        ld a, (p2y)
        ld b, PRX
        ld c, SPR_PADDLE
        call spr_emit
        ld a, (p2y)
        add a, 8
        ld b, PRX
        ld c, SPR_PADDLE
        call spr_emit
        ld a, (p2y)
        add a, 16
        ld b, PRX
        ld c, SPR_PADDLE
        call spr_emit
        ; ---- ball
        ld a, (bx)
        ld b, a                        ; b = x
        ld a, (by)                     ; a = y
        ld c, SPR_BALL
        ld d, 0x0f
        call spr_emit
        ret

; ==========================================================================
;  sound (SN76489, channel 0)
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

; HL = tone divider (3579545/(32*N) Hz), C = length in frames
sfx_play:
        ld a, l
        and 0x0f
        or 0x80
        out (PSG), a                   ; tone latch, low 4 bits
        ld a, h
        add a, a
        add a, a
        add a, a
        add a, a
        ld b, a
        ld a, l
        rrca
        rrca
        rrca
        rrca
        and 0x0f
        or b
        and 0x3f
        out (PSG), a                   ; tone high 6 bits
        ld a, 0x90
        out (PSG), a                   ; volume 0 = loudest
        ld a, c
        ld (sfx_time), a
        ret

sfx_tick:
        ld a, (sfx_time)
        or a
        ret z
        dec a
        ld (sfx_time), a
        ret nz
        ld a, 0x9f                     ; channel 0 off
        out (PSG), a
        ret

sfx_hit:                               ; ball meets paddle ~490 Hz
        ld hl, 228
        ld c, 8
        jp sfx_play

sfx_wall:                              ; ball meets wall ~226 Hz
        ld hl, 495
        ld c, 6
        jp sfx_play

sfx_point:                             ; somebody scored ~113 Hz
        ld hl, 990
        ld c, 26
        jp sfx_play

sfx_blip:                              ; menu tick
        ld hl, 340
        ld c, 4
        jp sfx_play

; ==========================================================================
;  title screen
; ==========================================================================
title_enter:
        xor a
        ld (state), a
        call sprites_hide_all
        ld hl, title_map
        ld de, 0x1800
        ld bc, 768
        call vdp_write
        ld a, 88
        ld (p1y), a
        ld (p2y), a
        ld a, BALL_HOME_X
        ld (bx), a
        ld a, BALL_HOME_Y
        ld (by), a
        ld a, 3
        ld (bdx), a
        ld a, 2
        ld (bdy), a
        call draw_menu_marker
        call update_sprites
        ret

draw_menu_marker:
        ld hl, MARK_ROW12
        call vdp_setaddr
        ld a, TILE_BLANK
        out (VDPDATA), a
        ld hl, MARK_ROW14
        call vdp_setaddr
        ld a, TILE_BLANK
        out (VDPDATA), a
        ld a, (menu_sel)
        or a
        ld hl, MARK_ROW12
        jr z, .go
        ld hl, MARK_ROW14
.go:
        call vdp_setaddr
        ld a, TILE_FONT + 0x1e         ; '>' marker
        out (VDPDATA), a
        ret

tick_title:
        ; ---- up: first option
        ld a, (pad1)
        bit 0, a
        jr z, .no_up
        ld a, (prev1)
        bit 0, a
        jr nz, .no_up
        ld a, (menu_sel)
        or a
        jr z, .no_up
        xor a
        ld (menu_sel), a
        call sfx_blip
        call draw_menu_marker
.no_up:
        ; ---- down: second option
        ld a, (pad1)
        bit 1, a
        jr z, .no_down
        ld a, (prev1)
        bit 1, a
        jr nz, .no_down
        ld a, (menu_sel)
        or a
        jr nz, .no_down
        ld a, 1
        ld (menu_sel), a
        call sfx_blip
        call draw_menu_marker
.no_down:
        ; ---- button 1 starts the game
        ld a, (pad1)
        bit 4, a
        jr z, .no_start
        ld a, (prev1)
        bit 4, a
        jr nz, .no_start
        ld a, (menu_sel)
        inc a
        ld (mode), a
        call game_start
        jp main_loop
.no_start:
        ld a, (pad1)
        ld (prev1), a
        call title_ball
        call update_sprites
        jp main_loop

; the ball bounces around inside the court behind the title text
title_ball:
        ld a, (bx)
        ld hl, bdx
        add a, (hl)
        ld (bx), a
        cp 24
        jr nc, .xmax
        ld a, 24
        ld (bx), a
        ld a, 3
        ld (bdx), a
        jr .y
.xmax:
        cp 228
        jr c, .y
        ld a, 228
        ld (bx), a
        ld a, 0xfd
        ld (bdx), a
.y:
        ld a, (by)
        ld hl, bdy
        add a, (hl)
        ld (by), a
        cp BALL_MIN_Y
        jr nc, .ymax
        ld a, BALL_MIN_Y
        ld (by), a
        ld a, (bdy)
        neg
        ld (bdy), a
        jr .done
.ymax:
        cp BALL_MAX_Y
        jr c, .done
        ld a, BALL_MAX_Y
        ld (by), a
        ld a, (bdy)
        neg
        ld (bdy), a
.done:
        ret

; ==========================================================================
;  starting a match
; ==========================================================================
game_start:
        xor a
        ld (score1), a
        ld (score2), a
        ld a, 88
        ld (p1y), a
        ld (p2y), a
        call sprites_hide_all
        call field_draw
        ld a, 1
        ld (state), a
        call serve_left                ; first service goes to player 1
        ld a, 60
        ld (serve_t), a
        call update_sprites
        ret

field_draw:
        ld hl, field_map
        ld de, 0x1800
        ld bc, 768
        call vdp_write
        jp show_scores

; ==========================================================================
;  scores
; ==========================================================================
show_scores:
        ld a, (score1)
        ld hl, SCORE1_ONES
        ld de, SCORE1_TENS
        call draw_score
        ld a, (score2)
        ld hl, SCORE2_ONES
        ld de, SCORE2_TENS
        jp draw_score

; A = score, HL = ones cell, DE = tens cell
draw_score:
        ld b, 0
.loop:
        cp 10
        jr c, .digits
        sub 10
        inc b
        jr .loop
.digits:
        ld (tmp_ones), a
        ld a, b
        ld (tmp_tens), a
        push hl                        ; keep the ones cell safe
        ; ---- tens digit (blank below 10)
        ld a, (tmp_tens)
        or a
        jr nz, .tens
        ld a, 0xff
.tens:
        ex de, hl                      ; HL = tens cell
        call draw_digit_block
        pop hl                         ; HL = ones cell
        ld a, (tmp_ones)
        jp draw_digit_block

; A = digit 0-9 or $FF for a blank, HL = name table address of top left tile
draw_digit_block:
        cp 0xff
        jr nz, .real
        ld b, 3
.blank:
        push bc
        call vdp_setaddr
        ld a, TILE_BLANK
        out (VDPDATA), a
        out (VDPDATA), a
        pop bc
        ld de, 32
        add hl, de
        djnz .blank
        ret
.real:
        ld c, a
        add a, a
        add a, c
        add a, a
        add a, TILE_DIG2X
        ld c, a
        ld b, 3
.row:
        push bc
        call vdp_setaddr
        ld a, c
        out (VDPDATA), a
        inc a
        out (VDPDATA), a
        pop bc
        ld de, 32
        add hl, de
        ld a, c
        add a, 2
        ld c, a
        djnz .row
        ret

; ==========================================================================
;  playing
; ==========================================================================
tick_play:
        call paddle_input
        ld a, (serve_t)
        or a
        jr z, .live
        dec a
        ld (serve_t), a
        jr .out
.live:
        call ball_update
.out:
        call update_sprites
        ld a, (pad1)
        ld (prev1), a
        jp main_loop

; A = paddle y, C = signed step -> A = new y, kept inside the court
move_paddle:
        add a, c
        cp PADDLE_MIN
        jr nc, .hi
        ld a, PADDLE_MIN
        ret
.hi:
        cp PADDLE_MAX + 1
        ret c
        ld a, PADDLE_MAX
        ret

paddle_input:
        ; ---- player 1, left paddle
        ld a, (pad1)
        bit 0, a
        jr z, .p1_down
        ld a, (p1y)
        ld c, 0xfd                     ; up 3 px
        call move_paddle
        ld (p1y), a
.p1_down:
        ld a, (pad1)
        bit 1, a
        jr z, .p2
        ld a, (p1y)
        ld c, PADDLE_STEP
        call move_paddle
        ld (p1y), a
.p2:
        ld a, (mode)
        cp 1
        jp z, cpu_ai
        ; ---- player 2, right paddle (up/down on port $DC, bits 6-7)
        ld a, (pad1)
        bit 6, a
        jr z, .p2_down
        ld a, (p2y)
        ld c, 0xfd
        call move_paddle
        ld (p2y), a
.p2_down:
        ld a, (pad1)
        bit 7, a
        ret z
        ld a, (p2y)
        ld c, PADDLE_STEP
        call move_paddle
        ld (p2y), a
        ret

; the one player opponent: follows the ball with a small dead zone and a
; limited speed, so steep shots beat it
cpu_ai:
        ld a, (bdx)
        bit 7, a
        jr nz, .idle                   ; ball going away
        ld a, (bx)
        cp 128
        jr c, .idle                    ; ball still on the other half
        ld a, (by)
        add a, 2                       ; ball centre
        jr .target
.idle:
        ld a, 88                       ; drift back to the middle
.target:
        ld b, a
        ld a, (p2y)
        add a, 12                      ; paddle centre
        ld c, a
        ld a, b
        sub c                          ; signed distance, + = move down
        jr z, .done
        bit 7, a
        jr nz, .up
        cp 5
        ret c
        ld a, (p2y)
        ld c, 2
        call move_paddle
        ld (p2y), a
        ret
.up:
        neg
        cp 5
        ret c
        ld a, (p2y)
        ld c, 0xfe
        call move_paddle
        ld (p2y), a
.done:
        ret

; ==========================================================================
;  the ball
; ==========================================================================
ball_update:
        ld a, (bx)
        ld hl, bdx
        add a, (hl)
        ld (bx), a
        ld a, (by)
        ld hl, bdy
        add a, (hl)
        ld (by), a
        ; ---- top wall
        ld a, (by)
        cp BALL_MIN_Y
        jr nc, .bottom
        ld a, BALL_MIN_Y
        ld (by), a
        ld a, (bdy)
        neg
        ld (bdy), a
        call sfx_wall
.bottom:
        ld a, (by)
        cp BALL_MAX_Y
        jr c, .left
        ld a, BALL_MAX_Y
        ld (by), a
        ld a, (bdy)
        neg
        ld (bdy), a
        call sfx_wall
.left:
        ld a, (bdx)
        bit 7, a
        jr z, .right
        ; ---- moving left: past the paddle?
        ld a, (bx)
        cp PLX - 8
        jp c, score_p2
        cp PLX + 6
        jr nc, check_right
        ld a, (p1y)
        call voverlap
        jr nc, check_right
        ld a, PLX - 3                  ; ball right edge on the paddle face
        ld (bx), a
        call bounce_left
        jr check_right
.right:
        ; ---- moving right: past the paddle?
        ld a, (bx)
        cp PRX + 8
        jp nc, score_p1
        cp PRX - 7
        jr c, ball_done
        ld a, (p2y)
        call voverlap
        jr nc, ball_done
        ld a, PRX - 4
        ld (bx), a
        call bounce_right
ball_done:
        ret

check_right:
        ld a, (bx)
        cp PRX + 8
        jp nc, score_p1
        cp PRX - 7
        ret c
        ld a, (p2y)
        call voverlap
        ret nc
        ld a, PRX - 4
        ld (bx), a
        jp bounce_right

; does the ball overlap a paddle whose top is in A?  carry set = yes
voverlap:
        ld c, a
        ld a, (by)
        add a, BALL_SIZE               ; ball bottom + 1
        cp c
        jr c, .no                      ; ball is above the paddle
        ld a, c
        add a, PADDLE_H
        ld c, a
        ld a, (by)
        cp c
        jr nc, .no                     ; ball is below the paddle
        scf
        ret
.no:
        or a
        ret

; ball bounced off the left paddle -> now travelling right
bounce_left:
        call bounce_angle
        ld a, (bdx)
        call abs_inc_cap
        ld (bdx), a
        jp sfx_hit

; ball bounced off the right paddle -> now travelling left
bounce_right:
        call bounce_angle
        ld a, (bdx)
        call abs_inc_cap
        neg
        ld (bdx), a
        jp sfx_hit

; vertical speed from where the ball met the paddle (6 zones over 24 px)
bounce_angle:
        ld a, (by)
        add a, 2
        ld c, a                        ; ball centre
        ; which paddle are we next to?
        ld a, (bx)
        cp 128
        ld a, (p1y)
        jr c, .zone
        ld a, (p2y)
.zone:
        ld b, a
        ld a, c
        sub b
        jr c, .top
        cp PADDLE_H
        jr nc, .bottom
        srl a
        srl a
        jr .look
.top:
        xor a
        jr .look
.bottom:
        ld a, 5
.look:
        ld e, a
        ld d, 0
        ld hl, vy_table
        add hl, de
        ld a, (hl)
        ld (bdy), a
        ret

vy_table:
        db 0xfd, 0xfe, 0xff, 0x01, 0x02, 0x03    ; -3,-2,-1,+1,+2,+3

; A = signed speed -> A = |speed| + 1, capped at 4
abs_inc_cap:
        bit 7, a
        jr z, .pos
        neg
.pos:
        cp 4
        ret nc
        inc a
        ret

; ==========================================================================
;  scoring
; ==========================================================================
score_p2:
        ld a, (score2)
        inc a
        ld (score2), a
        call sfx_point
        call show_scores
        ld a, (score2)
        cp WIN_SCORE
        jp nc, win_p2
        call serve_left
        jr serve_wait

score_p1:
        ld a, (score1)
        inc a
        ld (score1), a
        call sfx_point
        call show_scores
        ld a, (score1)
        cp WIN_SCORE
        jp nc, win_p1
        call serve_right
serve_wait:
        ld a, 45
        ld (serve_t), a
        ret

; put the ball back in the middle heading for the player who lost the point
serve_left:
        ld a, BALL_HOME_X
        ld (bx), a
        ld a, BALL_HOME_Y
        ld (by), a
        ld a, 0xfe                     ; -2
        ld (bdx), a
        ld a, 1
        ld (bdy), a
        ret

serve_right:
        ld a, BALL_HOME_X
        ld (bx), a
        ld a, BALL_HOME_Y
        ld (by), a
        ld a, 2
        ld (bdx), a
        ld a, 1
        ld (bdy), a
        ret

win_p1:
        ld a, 1
        jr game_over
win_p2:
        ld a, 2
game_over:
        ld (winner), a
        ld a, 2
        ld (state), a
        ld a, 0xd1                     ; park the ball off screen
        ld (by), a
        call over_text
        call update_sprites
        ld a, (pad1)
        ld (prev1), a
        jp main_loop

over_text:
        ld hl, str_gameover
        ld b, 11
        ld c, 10
        call draw_text_str
        ld a, (winner)
        cp 1
        jr z, .p1
        ld a, (mode)                   ; mode 1 = one player, paddle 2 is the CPU
        or a
        jr nz, .cpu
        ld hl, str_p2wins
        ld b, 9
        jr .p
.cpu:
        ld hl, str_cpuwins
        ld b, 11
        jr .p
.p1:
        ld hl, str_p1wins
        ld b, 9
.p:
        ld c, 12
        call draw_text_str
        ld hl, str_again
        ld b, 5
        ld c, 16
        jp draw_text_str

tick_over:
        ld a, (pad1)
        bit 4, a
        jr z, .no
        ld a, (prev1)
        bit 4, a
        jr nz, .no
        ld a, (pad1)                   ; the button is still held next frame
        ld (prev1), a
        call title_enter
        jp main_loop
.no:
        ld a, (pad1)
        ld (prev1), a
        jp main_loop

; ==========================================================================
;  text
; ==========================================================================
; HL = zero terminated string, B = column, C = row
draw_text_str:
        push hl
        ld l, c
        ld h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl                     ; row * 32
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
.loop:
        ld a, (hl)
        or a
        ret z
        sub 0x20
        add a, TILE_FONT
        out (VDPDATA), a
        inc hl
        jr .loop

str_gameover:  db "GAME OVER", 0
str_p1wins:    db "PLAYER 1 WINS", 0
str_p2wins:    db "PLAYER 2 WINS", 0
str_cpuwins:   db "CPU WINS     ", 0   ; padded so it clears the wider string
str_again:     db "PRESS 1 TO PLAY AGAIN", 0

; ==========================================================================
;  graphics data (generated by tools/gen_gfx.py)
; ==========================================================================
        include "gfx.asm"

; pad the cartridge image to 16 KB so every emulator is happy
        ds 0x4000 - $, 0xff
