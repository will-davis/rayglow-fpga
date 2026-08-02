"""Two-clock test of the double buffer: write a frame in `pix`, swap, read in `sync`.

Exercises the real CDC path (FFSynchronizer + toggle handoff) with the write and read
domains on different clocks, coordinated by a shared Python flag rather than cycle
counting so the test doesn't depend on the clock ratio.
"""

from amaranth.sim import Simulator

from gateware.double_buffer import DoubleBuffer
from gateware.patterns import rgb

W, S, N = 8, 2, 1
H = 2 * S


def img(x, y):
    return rgb(x * 8 + 1, y * 16 + 2, ((x + y) * 5) & 0xFF)


def test_write_swap_read_two_clocks():
    dut = DoubleBuffer(width=W, scan=S, chains=N)
    sim = Simulator(dut)
    sim.add_clock(1e-6, domain="pix")
    sim.add_clock(0.7e-6, domain="sync")   # deliberately different rate
    state = {"written": False}

    async def writer(ctx):
        for y in range(H):
            for x in range(W):
                ctx.set(dut.wr_x, x)
                ctx.set(dut.wr_y, y)
                ctx.set(dut.wr_pixel, img(x, y))
                ctx.set(dut.wr_valid, 1)
                # frame_start rides the first pixel, exactly as DpiIn emits it
                ctx.set(dut.wr_frame_start, 1 if (x == 0 and y == 0) else 0)
                await ctx.tick("pix")
        ctx.set(dut.wr_valid, 0)
        ctx.set(dut.wr_y, H)               # y advances past the last captured row (as
        await ctx.tick("pix")              # DpiIn's counter does) -> capture-complete
        await ctx.tick("pix")              # toggle fires -> handoff
        state["written"] = True

    async def reader(ctx):
        while not state["written"]:
            await ctx.tick("sync")
        for _ in range(5):                 # let the toggle cross the synchronizer
            await ctx.tick("sync")
        ctx.set(dut.rd_frame_end, 1)       # swap at the (simulated) scan frame boundary
        await ctx.tick("sync")
        ctx.set(dut.rd_frame_end, 0)
        await ctx.tick("sync")
        for y in range(H):
            half, addr = y // S, y % S
            for x in range(W):
                ctx.set(dut.rd_addr, addr * W + x)
                await ctx.tick("sync")     # synchronous read: data valid next cycle
                got = ctx.get(dut.rd_data[N * 0 + half])
                assert got == img(x, y), (
                    f"pixel ({x},{y}) read {got:#08x}, wrote {img(x, y):#08x}"
                )

    sim.add_testbench(writer)
    sim.add_testbench(reader)
    sim.run()


def test_no_tearing_with_distinct_frames():
    """Every scan sweep must show ONE source frame — never a mix (the wall-tear bug).

    Writer streams DPI-like frames whose every pixel = the frame id, followed by
    out-of-bounds rows (like the real 480-line mode) and a blanking gap. Reader
    continuously sweeps the full buffer at a faster cadence, swapping only at its own
    sweep boundary. Any sweep containing two different ids is a torn frame. The original
    swap-on-next-frame-start protocol fails this (reader keeps showing a buffer the
    writer has started overwriting); the swap-on-capture-complete protocol passes.
    """
    W, S, N = 8, 2, 1
    H = 2 * S * N
    dut = DoubleBuffer(width=W, scan=S, chains=N)
    sim = Simulator(dut)
    sim.add_clock(1e-6, domain="pix")
    sim.add_clock(0.3e-6, domain="sync")
    state = {"done": False}
    sweeps = []

    async def writer(ctx):
        for frame in range(1, 7):
            for y in range(H + 4):                    # H captured + 4 dropped rows
                for x in range(W):
                    ctx.set(dut.wr_x, x)
                    ctx.set(dut.wr_y, y)
                    ctx.set(dut.wr_pixel, frame)
                    ctx.set(dut.wr_valid, 1)
                    ctx.set(dut.wr_frame_start, 1 if (x == 0 and y == 0) else 0)
                    await ctx.tick("pix")
                ctx.set(dut.wr_valid, 0)              # hblank
                ctx.set(dut.wr_frame_start, 0)
                for _ in range(2):
                    await ctx.tick("pix")
            for _ in range(40):                       # vblank / idle gap
                await ctx.tick("pix")
        state["done"] = True

    async def reader(ctx):
        # Dwell per address like the real scan (planes+display), so a sweep spans
        # ~60% of a writer frame — the ratio on the real wall (9.8 ms vs 16.7 ms).
        # A too-fast reader shrinks the tear window and hides the bug.
        while not state["done"]:
            seen = set()
            for addr in range(W * S):
                ctx.set(dut.rd_addr, addr)
                for _ in range(15):
                    await ctx.tick("sync")
                for h in range(2):
                    seen.add(ctx.get(dut.rd_data[h]))
            ctx.set(dut.rd_frame_end, 1)
            await ctx.tick("sync")
            ctx.set(dut.rd_frame_end, 0)
            sweeps.append(seen)

    sim.add_testbench(writer)
    sim.add_testbench(reader)
    sim.run()

    torn = [s for s in sweeps if len(s) > 1]
    assert not torn, f"torn sweeps (mixed source frames): {torn[:5]} of {len(sweeps)}"
    assert any(s != {0} for s in sweeps), "reader never saw real frames (test harness bug)"


def test_slow_reader_drops_frames_never_tears():
    """The 120 Hz-DPI regime: reader sweep LONGER than DPI_period - capture_time.

    Here the completion-fired toggle alone is not enough — by the time the reader swaps,
    the old writer had already started overwriting its front buffer (the constraint the
    60 Hz mode satisfies and the ~122 Hz modes violate). The skip-gated writer must
    instead sit out source frames: every sweep still shows exactly ONE source frame,
    ids only move forward, and the sat-out frames are observable as `skip` pulses and
    as ids that never reach the panel.
    """
    W, S, N = 8, 2, 1
    H = 2 * S * N
    FRAMES = 12
    dut = DoubleBuffer(width=W, scan=S, chains=N)
    sim = Simulator(dut)
    sim.add_clock(1e-6, domain="pix")
    sim.add_clock(0.3e-6, domain="sync")
    state = {"done": False, "skips": 0}
    sweeps = []

    async def writer(ctx):
        for frame in range(1, FRAMES + 1):
            for y in range(H + 4):                    # H captured + 4 dropped rows
                for x in range(W):
                    ctx.set(dut.wr_x, x)
                    ctx.set(dut.wr_y, y)
                    ctx.set(dut.wr_pixel, frame)
                    ctx.set(dut.wr_valid, 1)
                    ctx.set(dut.wr_frame_start, 1 if (x == 0 and y == 0) else 0)
                    await ctx.tick("pix")
                ctx.set(dut.wr_valid, 0)              # hblank
                ctx.set(dut.wr_frame_start, 0)
                for _ in range(2):
                    await ctx.tick("pix")
            for _ in range(40):                       # vblank / idle gap
                await ctx.tick("pix")
        for _ in range(300):                          # idle: let the reader drain
            await ctx.tick("pix")
        state["done"] = True

    async def skip_monitor(ctx):
        while not state["done"]:
            if ctx.get(dut.skip):
                state["skips"] += 1
            await ctx.tick("pix")

    async def reader(ctx):
        # Dwell 20 (vs 15 in the test above): sweep ~96 us against a 120 us source
        # period whose capture completes ~42 us in — budget ~78 us, so the reader
        # misses the handoff window on a steady fraction of frames, as the ~140 Hz
        # scan does against a ~122 Hz DPI source (7.1 ms sweep vs ~6.1 ms budget).
        while not state["done"]:
            seen = set()
            for addr in range(W * S):
                ctx.set(dut.rd_addr, addr)
                for _ in range(20):
                    await ctx.tick("sync")
                for h in range(2):
                    seen.add(ctx.get(dut.rd_data[h]))
            ctx.set(dut.rd_frame_end, 1)
            await ctx.tick("sync")
            ctx.set(dut.rd_frame_end, 0)
            sweeps.append(seen)

    sim.add_testbench(writer)
    sim.add_testbench(skip_monitor)
    sim.add_testbench(reader)
    sim.run()

    torn = [s for s in sweeps if len(s) > 1]
    assert not torn, f"torn sweeps (mixed source frames): {torn[:5]} of {len(sweeps)}"
    shown = [next(iter(s)) for s in sweeps if s and s != {0}]
    assert shown, "reader never saw real frames (test harness bug)"
    assert shown == sorted(shown), f"displayed ids went backwards: {shown}"
    dropped = set(range(1, FRAMES + 1)) - set(shown)
    assert state["skips"] >= 2, f"skip gate never engaged (skips={state['skips']})"
    assert dropped, "no source frame was dropped — timing regime not exercised"
    # Every capture the writer DID make must reach the panel (the end-of-run idle lets
    # the reader drain), so the only route to a dropped id is a skip pulse: 1:1.
    assert state["skips"] == len(dropped), (
        f"skips={state['skips']} vs dropped ids={sorted(dropped)} — a capture was lost"
    )
