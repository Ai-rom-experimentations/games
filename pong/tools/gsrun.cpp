/*
 * Runs pong.sg on the Gearsystem core - the emulator Manic Emu uses - and
 * writes the frame as a PPM, plus optionally the 16 KB of VDP VRAM.
 *
 * This is the cross-check for tools/sg1000.py: a ROM that only looks right in
 * our own emulator is not necessarily right on hardware (that is exactly how
 * the swapped R3/R4 table registers survived the bundled tests for a while).
 *
 * Build against a Gearsystem checkout (https://github.com/drhelius/Gearsystem):
 *
 *     g++ -std=c++14 -O2 -w -I$GS/src -I$GS/platforms/shared/dependencies/miniz \
 *         $GS/src/*.cpp $GS/src/audio/*.cpp $GS/src/audio/emu2413/emu2413.c \
 *         $GS/platforms/shared/dependencies/miniz/miniz.c \
 *         tools/gsrun.cpp -o gsrun
 *
 * Usage:
 *
 *     ./gsrun pong.sg out.ppm [frames] [script] [vram.bin]
 *
 * `script` is one character per frame (cycled if it is shorter than `frames`):
 *   b  hold button 1        -  release button 1
 *   u  pad 1 up             d  pad 1 down
 *   U  pad 2 up             D  pad 2 down
 *   n  nothing held
 *
 * e.g. 'n'*20 + 'b'*20 + 'n'*1200 starts a one player match and lets the CPU
 * win it 11-0.
 */
#include "GearsystemCore.h"
#include "Cartridge.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

/* Gearsystem's log.h declares this; only its desktop front end defines it. */
bool g_mcp_stdio_mode = false;

static unsigned char frame_buffer[320 * 288 * 4];
static short sample_buffer[8192];

static std::vector<unsigned char> read_file(const char* path)
{
    std::vector<unsigned char> data;
    FILE* file = fopen(path, "rb");
    if (file == NULL)
        return data;
    fseek(file, 0, SEEK_END);
    long size = ftell(file);
    fseek(file, 0, SEEK_SET);
    if (size > 0) {
        data.resize(size);
        if (fread(data.data(), 1, size, file) != (size_t)size)
            data.clear();
    }
    fclose(file);
    return data;
}

static void write_ppm(const char* path, int width, int height)
{
    FILE* file = fopen(path, "wb");
    if (file == NULL)
        return;
    fprintf(file, "P6\n%d %d\n255\n", width, height);
    for (int i = 0; i < width * height; i++) {
        unsigned char rgb[3] = { frame_buffer[i * 4 + 0],
                                 frame_buffer[i * 4 + 1],
                                 frame_buffer[i * 4 + 2] };
        fwrite(rgb, 1, 3, file);
    }
    fclose(file);
}

static void apply_script(GearsystemCore& core, char key)
{
    switch (key) {
        case 'b':
            core.KeyPressed(Joypad_1, Key_1);
            break;
        case '-':
            core.KeyReleased(Joypad_1, Key_1);
            break;
        case 'u':
            core.KeyPressed(Joypad_1, Key_Up);
            core.KeyReleased(Joypad_1, Key_Down);
            break;
        case 'd':
            core.KeyPressed(Joypad_1, Key_Down);
            core.KeyReleased(Joypad_1, Key_Up);
            break;
        case 'U':
            core.KeyPressed(Joypad_2, Key_Up);
            core.KeyReleased(Joypad_2, Key_Down);
            break;
        case 'D':
            core.KeyPressed(Joypad_2, Key_Down);
            core.KeyReleased(Joypad_2, Key_Up);
            break;
        case 'n':
            core.KeyReleased(Joypad_1, Key_1);
            core.KeyReleased(Joypad_1, Key_Up);
            core.KeyReleased(Joypad_1, Key_Down);
            core.KeyReleased(Joypad_2, Key_Up);
            core.KeyReleased(Joypad_2, Key_Down);
            break;
        default:
            break;
    }
}

int main(int argc, char** argv)
{
    if (argc < 3) {
        fprintf(stderr, "usage: %s rom.sg out.ppm [frames] [script] [vram.bin]\n",
                argv[0]);
        return 2;
    }

    std::vector<unsigned char> rom = read_file(argv[1]);
    if (rom.empty()) {
        fprintf(stderr, "cannot read %s\n", argv[1]);
        return 1;
    }

    GearsystemCore core;
    core.Init(GS_PIXEL_RGBA8888);

    Cartridge::ForceConfiguration config;
    config.type = Cartridge::CartridgeRomOnlyMapper;
    config.zone = Cartridge::CartridgeJapanSMS;
    config.region = Cartridge::CartridgeNTSC;
    config.system = Cartridge::CartridgeSG1000;      /* never auto-detect */

    if (!core.LoadROMFromBuffer(rom.data(), (int)rom.size(), &config, argv[1])) {
        fprintf(stderr, "the core refused to load %s\n", argv[1]);
        return 1;
    }

    int frames = (argc > 3) ? atoi(argv[3]) : 120;
    const char* script = (argc > 4) ? argv[4] : "";
    int script_length = (int)strlen(script);

    for (int frame = 0; frame < frames; frame++) {
        if (script_length > 0)
            apply_script(core, script[frame % script_length]);
        int samples = 0;
        core.RunToVBlank(frame_buffer, sample_buffer, &samples);
    }

    core.KeyReleased(Joypad_1, Key_1);
    core.KeyReleased(Joypad_1, Key_Up);
    core.KeyReleased(Joypad_1, Key_Down);
    core.KeyReleased(Joypad_2, Key_Up);
    core.KeyReleased(Joypad_2, Key_Down);

    GS_RuntimeInfo info = {};
    core.GetRuntimeInfo(info);
    write_ppm(argv[2], info.screen_width, info.screen_height);

    if (argc > 5) {
        FILE* file = fopen(argv[5], "wb");
        if (file != NULL) {
            fwrite(core.GetVideo()->GetVRAM(), 1, 0x4000, file);
            fclose(file);
        }
    }

    printf("%s: %d frames, %dx%d\n", argv[2], frames,
           info.screen_width, info.screen_height);
    return 0;
}
