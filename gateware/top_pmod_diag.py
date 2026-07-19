"""J31 wiring diagnostic: every PMOD data pin is a pulled-up input with an edge latch.

LED n lights (and stays lit) once J31 data pin n has seen a falling edge:
  LED0..3 (D5..D8)  = J31 pins 1,2,3,4  (balls C6,C7,E8,D8)
  LED4..7 (D9..D12) = J31 pins 7,8,9,10 (balls C8,B8,A7,A8)
Stream UART bytes into the header and the lit LED identifies where the sender's TX
wire physically landed. Pull-ups keep unconnected pins quiet.

Build + load:
    uv run python -m gateware.top_pmod_diag
    openFPGALoader -b ecp5_evn build/top.bit
"""

from amaranth import Cat, Elaboratable, Module, Signal
from amaranth.build import Attrs, Pins, Resource
from amaranth.lib.cdc import FFSynchronizer

from .platform import ECP5EVNPlatform


class Top(Elaboratable):
    def elaborate(self, platform):
        m = Module()
        pmod = platform.request("pmod_in", 0)
        synced = Signal(8, init=0xFF)
        m.submodules.sync_pins = FFSynchronizer(pmod.i, synced, init=0xFF)

        prev = Signal(8, init=0xFF)
        latch = Signal(8)
        m.d.sync += [prev.eq(synced), latch.eq(latch | (prev & ~synced))]

        leds = Cat(platform.request("led", i).o for i in range(8))
        m.d.comb += leds.eq(latch)
        return m


if __name__ == "__main__":
    plat = ECP5EVNPlatform()
    plat.add_resources([
        Resource(
            "pmod_in", 0,
            Pins("C6 C7 E8 D8 C8 B8 A7 A8", dir="i"),
            Attrs(IO_TYPE="LVCMOS33", PULLMODE="UP"),
        ),
    ])
    plat.build(Top(), do_program=False)
