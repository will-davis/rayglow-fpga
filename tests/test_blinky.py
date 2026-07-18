"""First simulation: proves the uv/Amaranth stack end-to-end with zero system deps."""

from amaranth.sim import Simulator

from gateware.blinky import Blinky


def test_led_is_counter_msb():
    dut = Blinky(period_bits=3)  # LED = counter bit 3 -> toggles every 8 cycles
    sim = Simulator(dut)
    sim.add_clock(1e-6)

    async def bench(ctx):
        for tick in range(64):
            assert ctx.get(dut.led) == (tick >> 3) & 1, f"wrong LED state at tick {tick}"
            await ctx.tick()

    sim.add_testbench(bench)
    sim.run()
