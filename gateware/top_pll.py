"""Phase 0 PLL milestone: two clock domains, visibly different blink rates.

LED7 = heartbeat in the 12 MHz 'sync' domain (~1.4 Hz)
LED0 = the SAME Blinky renamed into the 60 MHz PLL domain (~7.2 Hz — exactly 5x)
LED1 = solid when the PLL reports LOCK

Build + load:
    uv run python -m gateware.top_pll
    openFPGALoader -b ecp5_evn build/top.bit
"""

from amaranth import DomainRenamer, Elaboratable, Module

from .blinky import Blinky
from .pll import PLL12to60
from .platform import ECP5EVNPlatform


class Top(Elaboratable):
    def elaborate(self, platform):
        m = Module()
        m.submodules.pll = pll = PLL12to60()
        m.submodules.slow = slow = Blinky(period_bits=22)
        m.submodules.fast = fast = DomainRenamer("fast")(Blinky(period_bits=22))
        m.d.comb += [
            platform.request("led", 7).o.eq(slow.led),
            platform.request("led", 0).o.eq(fast.led),
            platform.request("led", 1).o.eq(pll.locked),
        ]
        return m


if __name__ == "__main__":
    ECP5EVNPlatform().build(Top(), do_program=False)
