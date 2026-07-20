"""Capstone sim: a DPI video frame in the `pix` domain appears, byte-exact after gamma,
on the HUB75 pins in the `sync` domain — end-to-end through the clock-domain crossing.

A software panel reconstructs the displayed image from the scan-out pins (same technique
as test_scanout) and, after the buffer has swapped in the fed frame, one full scan frame
must match unit*lut[pixel] for every pixel. The writer feeds the same image every frame,
so the reconstructed frame matches regardless of exactly when the swap lands.
"""

from amaranth.sim import Simulator

from gateware.patterns import rgb
from gateware.translator import DpiToHub75

W, S, N, B, U = 8, 2, 1, 2, 1
H = 2 * S
LUT2 = [v >> 6 for v in range(256)]          # 8-bit code -> 2-bit weight (0..3)


def img(x, y):
    return rgb(x * 32, y * 64, ((x + y) * 40) & 0xFF)


def ch(pixel, c):
    return (pixel >> (16 - 8 * c)) & 0xFF


def dpi_frame():
    """DE/VSYNC/pixel per pix-cycle: a VSYNC blank line, then H lines of W + hblank."""
    hb = 2
    cyc = [(0, 1 if i < 2 else 0, 0) for i in range(W + hb)]
    for y in range(H):
        cyc += [(1, 0, img(x, y)) for x in range(W)]
        cyc += [(0, 0, 0) for _ in range(hb)]
    return cyc


def test_dpi_video_reaches_panel():
    dut = DpiToHub75(width=W, scan=S, chains=N, planes=B, unit=U, lut_init=LUT2,
                     max_w=16, max_h=16)
    sim = Simulator(dut)
    sim.add_clock(1e-6, domain="pix")
    sim.add_clock(0.3e-6, domain="sync")     # scan-out runs faster than DPI, as on hardware
    state = {"written": False}

    async def writer(ctx):
        for _frame in range(4):
            for de, vs, p in dpi_frame():
                ctx.set(dut.de, de)
                ctx.set(dut.vsync, vs)
                ctx.set(dut.pixel_in, p)
                await ctx.tick("pix")
        ctx.set(dut.de, 0)
        ctx.set(dut.vsync, 0)
        state["written"] = True

    async def panel(ctx):
        while not state["written"]:
            await ctx.tick("sync")

        # Accumulate exactly one full scan frame = the span between two `frame` rising
        # edges (front has settled on the fed image by now).
        acc = [[[0] * 3 for _ in range(W)] for _ in range(H)]
        row_shift, latched, prev_clk = [], None, 0
        prev_frame, edges = ctx.get(dut.frame), 0
        for _ in range(40000):
            clk, lat, blank = ctx.get(dut.clk), ctx.get(dut.lat), ctx.get(dut.blank)
            addr, rgbv, frame = ctx.get(dut.addr), ctx.get(dut.rgb), ctx.get(dut.frame)
            if frame and not prev_frame:
                edges += 1
                if edges == 1:
                    acc = [[[0] * 3 for _ in range(W)] for _ in range(H)]
                    row_shift, latched = [], None
                elif edges == 2:
                    break
            if edges >= 1:
                if clk and not prev_clk:
                    row_shift.append(rgbv)
                if lat:
                    latched, row_shift = row_shift, []
                if not blank and latched is not None:
                    for x in range(min(len(latched), W)):
                        for half in range(2):
                            for c in range(3):
                                if (latched[x] >> (half * 3 + c)) & 1:
                                    acc[addr + half * S][x][c] += 1
            prev_clk, prev_frame = clk, frame
            await ctx.tick("sync")
        else:
            raise AssertionError("two scan-frame boundaries never observed")

        for y in range(H):
            for x in range(W):
                for c in range(3):
                    expect = U * LUT2[ch(img(x, y), c)]
                    assert acc[y][x][c] == expect, (
                        f"pixel ({x},{y}) ch{c}: lit {acc[y][x][c]}, expected {expect}"
                    )
        state["done"] = True

    sim.add_testbench(writer)
    sim.add_testbench(panel)
    sim.run()
    assert state.get("done"), "panel testbench did not finish"
