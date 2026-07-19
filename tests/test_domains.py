"""Multi-clock simulation: DomainRenamer moves a module into a second clock domain.

The EHXPLLL primitive itself can't be simulated (it's an analog block); the sim drives
the 'fast' domain with its own clock instead, which is exactly what the PLL does on
hardware. Each blinky must toggle every 2**period_bits ticks OF ITS OWN domain.
"""

from amaranth import ClockDomain, DomainRenamer, Module
from amaranth.sim import Simulator

from gateware.blinky import Blinky


def test_domain_renamer_two_clocks():
    m = Module()
    m.domains += ClockDomain("fast")
    m.submodules.slow = slow = Blinky(period_bits=3)
    m.submodules.fast = fast = DomainRenamer("fast")(Blinky(period_bits=3))

    sim = Simulator(m)
    sim.add_clock(1 / 12e6)
    sim.add_clock(1 / 60e6, domain="fast")

    def watch(led, domain):
        async def bench(ctx):
            toggles = 0
            prev = ctx.get(led)
            for _ in range(64):
                await ctx.tick(domain)
                cur = ctx.get(led)
                toggles += cur != prev
                prev = cur
            assert toggles == 8, f"{domain}: {toggles} toggles in 64 ticks, expected 8"

        return bench

    sim.add_testbench(watch(slow.led, "sync"))
    sim.add_testbench(watch(fast.led, "fast"))
    sim.run()
