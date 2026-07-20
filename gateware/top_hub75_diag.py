"""Phase 1 artifact diagnostic: color bars + fade, with a live OE-pulse-width A/B.

Pattern: 8 pure-hue vertical bars (R G B C M Y W black) fading full->off top->bottom.
  - Adjacent saturated bars = crosstalk test (does the blue bar go purple? is black truly
    dark, or does it ghost?).
  - The dim bottom of each bar = dark-region test (does a hue stay true as it dims?).

SW5 switch 1 selects `unit` (LSB OE pulse) LIVE, same image both ways:
  OFF -> unit=4  (production; LSB OE pulse = 333 ns @ 6 MHz shift) -> ~139 Hz, steady
  ON  -> unit=32 (LSB OE pulse = 2.67 us)                          -> ~22 Hz, WILL FLICKER

If the top-left purple / dark-region tint CLEANS UP with the switch ON, the cause is
short-LSB-pulse nonlinearity in the panel drivers (not a wiring/SI problem). If the blue
bar stays purple regardless, it's crosstalk on the unbuffered lines -> buffer them
(74AHCT245 or the Adafruit HAT). Flicker at ON is expected (low refresh), not a fault.

Build + load:  uv run python -m gateware.top_hub75_diag
               openFPGALoader -b ecp5_evn build/top.bit
"""

from amaranth import Elaboratable, Module, Mux
from amaranth.build import Attrs, Pins, Resource, Subsignal

from .patterns import banks_from_image, color_bars_fade
from .platform import ECP5EVNPlatform
from .scanout import Hub75Core

WIDTH, SCAN = 64, 16
UNIT_LOW, UNIT_HIGH = 4, 32


class Top(Elaboratable):
    def elaborate(self, platform):
        m = Module()
        panel = platform.request("hub75", 0)
        sw = platform.request("switch", 0)          # SW5 position 1
        image = color_bars_fade(WIDTH, 2 * SCAN)
        m.submodules.core = core = Hub75Core(
            width=WIDTH, scan=SCAN, planes=10, unit=UNIT_LOW, unit_max=UNIT_HIGH,
            banks_init=[banks_from_image(image, WIDTH, SCAN)],
        )
        m.d.comb += [
            core.unit.eq(Mux(sw.i, UNIT_HIGH, UNIT_LOW)),  # PinsN: sw.i=1 when ON (grounded)
            panel.rgb.o.eq(core.rgb),
            panel.addr.o.eq(core.addr),
            panel.clk.o.eq(core.clk),
            panel.lat.o.eq(core.lat),
            panel.oe.o.eq(core.blank),
            platform.request("led", 7).o.eq(sw.i),         # LED confirms which unit is live
        ]
        return m


if __name__ == "__main__":
    plat = ECP5EVNPlatform()
    plat.add_resources([
        Resource(
            "hub75", 0,
            Subsignal("rgb", Pins("A5 A4 C5 B5 B4 C4", dir="o")),
            Subsignal("addr", Pins("B3 A3 D5 E4", dir="o")),
            Subsignal("clk", Pins("D3", dir="o")),
            Subsignal("lat", Pins("C3", dir="o")),
            Subsignal("oe", Pins("E3", dir="o")),
            Attrs(IO_TYPE="LVCMOS33", DRIVE="8", SLEWRATE="SLOW"),
        ),
    ])
    plat.build(Top(), do_program=False)
