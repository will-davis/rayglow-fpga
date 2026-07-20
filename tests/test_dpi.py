"""Verify the DPI decoder against a synthesized DE/VSYNC/RGB stream (2 frames)."""

from amaranth.sim import Simulator

from gateware.dpi import DpiIn
from gateware.patterns import rgb

W, H, HBLANK = 4, 3, 2


def pix(x, y):
    return rgb(x * 10, y * 10, (x + y) & 0xFF)


def frame_cycles():
    """One frame: a VSYNC-bearing blank line, then H active lines each W wide + hblank."""
    cyc = [(0, 1 if i < 2 else 0, 0) for i in range(W + HBLANK)]  # vblank w/ vsync pulse
    for y in range(H):
        cyc += [(1, 0, pix(x, y)) for x in range(W)]
        cyc += [(0, 0, 0) for _ in range(HBLANK)]
    return cyc


def test_dpi_decode_two_frames():
    dut = DpiIn(max_w=8, max_h=8)
    sim = Simulator(dut)
    sim.add_clock(1e-6)

    stream = frame_cycles() * 2
    got = []

    async def bench(ctx):
        for de, vs, p in stream:
            ctx.set(dut.de, de)
            ctx.set(dut.vsync, vs)
            ctx.set(dut.pixel_in, p)
            if ctx.get(dut.valid):
                got.append((ctx.get(dut.x), ctx.get(dut.y),
                            ctx.get(dut.pixel), ctx.get(dut.frame_start)))
            await ctx.tick()

    sim.add_testbench(bench)
    sim.run()

    expected = []
    for _f in range(2):
        for y in range(H):
            for x in range(W):
                expected.append((x, y, pix(x, y), 1 if (x == 0 and y == 0) else 0))

    assert len(got) == 2 * W * H, f"emitted {len(got)} active pixels, expected {2 * W * H}"
    assert got == expected, "coordinate/pixel/frame_start mismatch"
    # frame_start pulses exactly twice, once per frame, and only at (0,0)
    starts = [(g[0], g[1]) for g in got if g[3]]
    assert starts == [(0, 0), (0, 0)], f"frame_start fired at {starts}"


def test_dpi_vsync_active_low():
    """Same stream logic with inverted VSYNC polarity still finds frame starts."""
    dut = DpiIn(max_w=8, max_h=8, vsync_active=0)
    sim = Simulator(dut)
    sim.add_clock(1e-6)

    stream = [(de, 1 - vs, p) for (de, vs, p) in frame_cycles()]  # invert vsync
    starts = []

    async def bench(ctx):
        for de, vs, p in stream:
            ctx.set(dut.de, de)
            ctx.set(dut.vsync, vs)
            ctx.set(dut.pixel_in, p)
            if ctx.get(dut.valid) and ctx.get(dut.frame_start):
                starts.append((ctx.get(dut.x), ctx.get(dut.y)))
            await ctx.tick()

    sim.add_testbench(bench)
    sim.run()
    assert starts == [(0, 0)], f"frame_start fired at {starts}"
