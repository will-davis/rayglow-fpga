"""Phase 2 board top: Pi DPI in on JP8 -> HUB75 out on J32. The wall-as-monitor.

Two async clock domains meet here (this is the whole point of the CDC):
  pix  = the Pi's DPI pixel clock, arriving on JP8 (ball L18) — ~3.5 MHz for 384x128@60
  sync = the EVN's 12 MHz FTDI clock (default) -> 6 MHz shift, ~139 Hz refresh

Bench crop: the Pi is configured 384x128 (final wall geometry) but only one 64x32 panel
is attached, so the translator is built at 64x32/1-chain and the double buffer's
capture-bounds gate keeps just the top-left 64x32 of the incoming frame.

DPI pin map: INTERFACE-CONTRACT.md §4a (JP8 -> bank 3). pixel_in = the 24 data lines in
GPIO order; R/G/B channel order is provisional (grayscale console reads fine either way,
color order pinned by eye — raspberrypi/linux#6505). HSYNC (U16) is driven by the Pi but
unused here (DE-derived timing), so it's left unrequested (high-Z FPGA input).

⚠ PCLK (L18) is a general I/O, not a dedicated clock pin — watch the nextpnr log for
clock-routing warnings; at 3.5 MHz there is enormous timing margin regardless.

Build + load:  uv run python -m gateware.top_translator
               openFPGALoader -b ecp5_evn build/top.bit
"""

from amaranth import ClockDomain, ClockSignal, Elaboratable, Module
from amaranth.build import Attrs, Pins, Resource, Subsignal

from .platform import ECP5EVNPlatform
from .translator import DpiToHub75

WIDTH, SCAN = 64, 16
DPI_DATA = "U17 U18 T18 R18 U19 T19 U20 R20 T20 P20 P18 N20 " \
           "P19 N19 T16 R17 P16 R16 N17 P17 M17 N18 N16 M18"   # D0..D23 = GPIO4..27


class Top(Elaboratable):
    def elaborate(self, platform):
        m = Module()
        dpi = platform.request("dpi", 0)
        panel = platform.request("hub75", 0)

        # 'pix' domain clocked directly by the Pi's DPI pixel clock (JP8 L18).
        m.domains.pix = ClockDomain("pix")
        m.d.comb += ClockSignal("pix").eq(dpi.pclk.i)

        m.submodules.tr = tr = DpiToHub75(
            width=WIDTH, scan=SCAN, chains=1, planes=10, unit=4, vsync_active=1)
        m.d.comb += [
            tr.de.eq(dpi.de.i),
            tr.vsync.eq(dpi.vsync.i),
            tr.pixel_in.eq(dpi.data.i),          # provisional R/G/B order
            panel.rgb.o.eq(tr.rgb),
            panel.addr.o.eq(tr.addr),
            panel.clk.o.eq(tr.clk),
            panel.lat.o.eq(tr.lat),
            panel.oe.o.eq(tr.blank),
            platform.request("led", 7).o.eq(tr.frame),   # flickers at scan-frame rate
        ]
        return m


if __name__ == "__main__":
    plat = ECP5EVNPlatform()
    plat.add_resources([
        Resource("dpi", 0,
                 Subsignal("pclk", Pins("L18", dir="i")),
                 Subsignal("de", Pins("L17", dir="i")),
                 Subsignal("vsync", Pins("T17", dir="i")),
                 Subsignal("data", Pins(DPI_DATA, dir="i")),
                 Attrs(IO_TYPE="LVCMOS33")),
        Resource("hub75", 0,
                 Subsignal("rgb", Pins("A5 A4 C5 B5 B4 C4", dir="o")),
                 Subsignal("addr", Pins("B3 A3 D5 E4", dir="o")),
                 Subsignal("clk", Pins("D3", dir="o")),
                 Subsignal("lat", Pins("C3", dir="o")),
                 Subsignal("oe", Pins("E3", dir="o")),
                 Attrs(IO_TYPE="LVCMOS33", DRIVE="8", SLEWRATE="SLOW")),
    ])
    plat.build(Top(), do_program=False)
