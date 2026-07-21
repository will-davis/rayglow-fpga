"""Golden-model verification of the HUB75 scan-out engine.

The testbench is a software panel: it watches the real pins, clocks the RGB bits into a
model shift register on CLK rising edges, copies it to row latches on LAT, and integrates
lit-time per pixel per channel while blank is low. Over one full frame, every pixel's
accumulated on-time must equal  unit * lut[source_channel]  EXACTLY — that's the whole
point of binary-coded modulation. Structural properties are asserted along the way.

Runs at a shrunken geometry so a full frame is a few hundred cycles; a real-geometry
(64x32, B=10) single-row smoke test guards against parametrization rot.
"""

import pytest
from amaranth.sim import Simulator

from gateware.patterns import banks_from_image, counting
from gateware.scanout import Hub75Core

LUT3 = [v >> 5 for v in range(256)]  # 8-bit code -> 3-bit value, easy to reason about


def channel(pix, ch):
    return (pix >> (16 - 8 * ch)) & 0xFF


def run_frame_and_check(chains, unit_drive=None, guard=0):
    W, S, B, U = 8, 2, 3, 2
    eff = unit_drive if unit_drive is not None else U
    imgs = [counting(W, 2 * S) for _ in range(chains)]
    for c, img in enumerate(imgs):          # make each chain's content distinct
        img[0][0] = (17 * (c + 1)) << 16
    dut = Hub75Core(
        width=W, scan=S, chains=chains, planes=B, unit=U, unit_max=8, guard=guard,
        banks_init=[banks_from_image(img, W, S) for img in imgs], lut_init=LUT3,
    )
    sim = Simulator(dut)
    sim.add_clock(1e-6)

    acc = [[[[0] * 3 for _ in range(W)] for _ in range(2 * S)] for _ in range(chains)]

    async def bench(ctx):
        if unit_drive is not None:
            ctx.set(dut.unit, unit_drive)
        row_shift = []
        latched = None
        prev_clk = 0
        for _ in range(50_000):
            clk, lat = ctx.get(dut.clk), ctx.get(dut.lat)
            blank, addr = ctx.get(dut.blank), ctx.get(dut.addr)
            rgb, frame = ctx.get(dut.rgb), ctx.get(dut.frame)

            if clk and not prev_clk:
                assert blank, "v1 property violated: shifting while displaying"
                row_shift.append(rgb)
            if lat:
                assert blank and not clk, "LAT must strobe while blanked, CLK idle"
                assert len(row_shift) == W, f"latched {len(row_shift)} pixels, expected {W}"
                latched = row_shift
                row_shift = []
            if not blank:
                assert latched is not None
                for x in range(W):
                    bits = latched[x]
                    for c in range(chains):
                        for half in range(2):
                            for ch in range(3):
                                if (bits >> (c * 6 + half * 3 + ch)) & 1:
                                    acc[c][addr + half * S][x][ch] += 1
            prev_clk = clk
            if frame:
                return
            await ctx.tick()
        raise AssertionError("no frame pulse within cycle budget")

    sim.add_testbench(bench)
    sim.run()

    for c in range(chains):
        for y in range(2 * S):
            for x in range(W):
                for ch in range(3):
                    expect = eff * LUT3[channel(imgs[c][y][x], ch)]
                    got = acc[c][y][x][ch]
                    assert got == expect, (
                        f"chain {c} pixel ({x},{y}) ch{ch}: lit {got} cycles, expected {expect}"
                    )


def test_golden_frame_one_chain():
    run_frame_and_check(chains=1)


def test_golden_frame_two_chains():
    run_frame_and_check(chains=2)


def test_runtime_unit_scales_littime():
    # Driving core.unit changes every pixel's on-time proportionally (the live A/B knob).
    run_frame_and_check(chains=1, unit_drive=5)


def test_blanking_guard_preserves_littime():
    # The guard adds blanked settle cycles after LATCH; lit-time (BCM weights) unchanged.
    run_frame_and_check(chains=1, guard=4)


def test_blanking_guard_blanks_before_display():
    # After each LAT pulse there must be >=guard blanked cycles before OE de-asserts.
    W, S, B, U, G = 8, 1, 2, 1, 4
    img = counting(W, 2 * S)
    dut = Hub75Core(width=W, scan=S, planes=B, unit=U, guard=G,
                    banks_init=[banks_from_image(img, W, S)])
    sim = Simulator(dut)
    sim.add_clock(1e-6)

    async def bench(ctx):
        saw_lat = False
        blanked_since_lat = 0
        checked = 0
        for _ in range(4000):
            lat, blank = ctx.get(dut.lat), ctx.get(dut.blank)
            if lat:
                saw_lat, blanked_since_lat = True, 0
            elif saw_lat and blank:
                blanked_since_lat += 1
            elif saw_lat and not blank:          # OE on: measure the gap we accumulated
                assert blanked_since_lat >= G, f"only {blanked_since_lat} guard cycles, want >={G}"
                saw_lat = False
                checked += 1
                if checked >= B:                  # checked a full row's worth of planes
                    return
            await ctx.tick()
        raise AssertionError("never observed guarded latch->display transitions")

    sim.add_testbench(bench)
    sim.run()


def test_real_geometry_one_row_smoke():
    W, S, B, U = 64, 16, 10, 4
    img = counting(W, 2 * S)
    dut = Hub75Core(width=W, scan=S, planes=B, unit=U,
                    banks_init=[banks_from_image(img, W, S)])
    sim = Simulator(dut)
    sim.add_clock(1e-6)

    async def bench(ctx):
        lats = 0
        prev_lat = 0
        budget = B * (2 * W + 3) + U * ((1 << B) - 1) + 100
        for _ in range(budget):
            lat = ctx.get(dut.lat)
            if lat and not prev_lat:
                lats += 1
            prev_lat = lat
            if ctx.get(dut.addr) == 1:      # first row finished
                assert lats == B, f"{lats} latches in row 0, expected {B}"
                return
            await ctx.tick()
        raise AssertionError("row 0 never completed")

    sim.add_testbench(bench)
    sim.run()


def test_banks_from_image_geometry_guard():
    with pytest.raises(AssertionError):
        banks_from_image(counting(8, 7), 8, 4)  # height must be 2*scan
