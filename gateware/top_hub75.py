"""Phase 1 bench top: one 64x32 1/16-scan panel on J32, gradient test pattern.

Runs the scan-out engine in the 12 MHz sync domain -> 6 MHz shift clock (gentle for
direct 3.3 V drive over jumper wires, and visible on the PicoScope). B=10 planes,
U=4 -> ~139 Hz refresh, ~76 % duty (SCANOUT.md has the math).

J32 pin map (chain 0 + shared control, first 13 GPIO positions in table order —
full wiring table incl. the HUB75 connector end: SCANOUT.md):

  J32 pin :  5   6   9  10  13  14 | 17  18  21  22 | 25  26  29
  ball    : A5  A4  C5  B5  B4  C4 | B3  A3  D5  E4 | D3  C3  E3
  signal  : R1  G1  B1  R2  G2  B2 |  A   B   C   D | CLK LAT  OE

Build + load:
    uv run python -m gateware.top_hub75
    openFPGALoader -b ecp5_evn build/top.bit
"""

from amaranth import Elaboratable, Module
from amaranth.build import Attrs, Pins, Resource, Subsignal

from .patterns import banks_from_image, gradient
from .platform import ECP5EVNPlatform
from .scanout import Hub75Core

WIDTH, SCAN = 64, 16


class Top(Elaboratable):
    def elaborate(self, platform):
        m = Module()
        panel = platform.request("hub75", 0)
        image = gradient(WIDTH, 2 * SCAN)
        m.submodules.core = core = Hub75Core(
            width=WIDTH, scan=SCAN, planes=10, unit=4,
            banks_init=[banks_from_image(image, WIDTH, SCAN)],
        )
        m.d.comb += [
            panel.rgb.o.eq(core.rgb),
            panel.addr.o.eq(core.addr),
            panel.clk.o.eq(core.clk),
            panel.lat.o.eq(core.lat),
            panel.oe.o.eq(core.blank),  # OE active low: blank=1 -> panel dark
            platform.request("led", 7).o.eq(core.frame),  # flickers at frame rate
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
            # Gentle edges on purpose: unbuffered 3.3 V over jumpers wants slow slew.
            Attrs(IO_TYPE="LVCMOS33", DRIVE="8", SLEWRATE="SLOW"),
        ),
    ])
    plat.build(Top(), do_program=False)
