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
                await ctx.tick("pix")
        ctx.set(dut.wr_valid, 0)
        ctx.set(dut.wr_frame_start, 1)     # signal frame complete -> handoff
        await ctx.tick("pix")
        ctx.set(dut.wr_frame_start, 0)
        await ctx.tick("pix")
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
