"""Bitstream top: Blinky on LED0 from the 12 MHz FTDI clock (~1.4 Hz blink).

Build (needs yosys/nextpnr-ecp5/ecppack on PATH — ROADMAP Phase 0):
    uv run python -m gateware.top_blinky
Load into SRAM (volatile, instant):
    openFPGALoader -b ecp5_evn build/top.bit
"""

from amaranth import Elaboratable, Module

from .blinky import Blinky
from .platform import ECP5EVNPlatform


class Top(Elaboratable):
    def elaborate(self, platform):
        m = Module()
        m.submodules.blinky = blinky = Blinky(period_bits=22)
        m.d.comb += platform.request("led", 0).o.eq(blinky.led)
        return m


if __name__ == "__main__":
    ECP5EVNPlatform().build(Top(), do_program=False)
