"""Phase 0 interactive: heartbeat + button + DIP switches, all pure wiring.

LED7 = heartbeat (~1.4 Hz) — proof the clock is alive.
LED0 = lit while SW4 (the user push button) is held.
LEDs 1-6 = DIP switches 1-6 (SW5), live.

Build + load:
    uv run python -m gateware.top_phase0
    openFPGALoader -b ecp5_evn build/top.bit
"""

from amaranth import Elaboratable, Module

from .blinky import Blinky
from .platform import ECP5EVNPlatform


class Top(Elaboratable):
    def elaborate(self, platform):
        m = Module()
        m.submodules.heartbeat = heartbeat = Blinky(period_bits=22)
        m.d.comb += platform.request("led", 7).o.eq(heartbeat.led)
        m.d.comb += platform.request("led", 0).o.eq(platform.request("button", 0).i)
        for i in range(1, 7):
            m.d.comb += platform.request("led", i).o.eq(platform.request("switch", i - 1).i)
        return m


if __name__ == "__main__":
    ECP5EVNPlatform().build(Top(), do_program=False)
