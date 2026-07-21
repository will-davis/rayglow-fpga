"""Phase 2 board top: Pi DPI in on JP8 -> HUB75 out on J32. The wall-as-monitor.

Three clock domains meet here:
  pix  = the Pi's DPI pixel clock on JP8 (ball L18), ~12.5 MHz for 384x480@60
  scan = a 60 MHz PLL (from the 12 MHz FTDI clock) -> 30 MHz HUB75 shift
  sync = the raw 12 MHz FTDI clock, used only as the PLL reference

The scan-out runs in `scan` (60 MHz): a 6-panel-wide strip (384 px) shifts 6x longer
than one panel, so the 12 MHz default clock would sag to ~63 Hz / 34% duty. The PLL
brings it to ~150 Hz / ~68% duty at unit=16. Achieved with NO change to the scan-out
engine or double buffer — just a DomainRenamer mapping their `sync` -> `scan`, while DPI
capture stays in `pix`. The CDC (double_buffer.py) becomes pix<->scan; it doesn't care.

GEOMETRY: single chain of 6x P4/P6 64x32 panels = 384x32 (1/16 scan). The Pi renders
384x32 (`--width 384 --height 32`) into the top-left of its 384x480 DPI frame; the FPGA
captures that 384x32 region (bounds-gated) and drives all six panels off one HUB75 chain.

For a single 64x32 bench panel instead, set WIDTH=64 (the PLL is harmless there too).

Build + load:  uv run python -m gateware.top_translator
               openFPGALoader -b ecp5_evn build/top.bit
"""

from amaranth import ClockDomain, ClockSignal, DomainRenamer, Elaboratable, Module
from amaranth.build import Attrs, Pins, Resource, Subsignal

from .pll import PLL12to40
from .platform import ECP5EVNPlatform
from .translator import DpiToHub75

WIDTH, SCAN = 384, 16
DPI_DATA = "U17 U18 T18 R18 U19 T19 U20 R20 T20 P20 P18 N20 " \
           "P19 N19 T16 R17 P16 R16 N17 P17 M17 N18 N16 M18"   # D0..D23 = GPIO4..27


class Top(Elaboratable):
    def elaborate(self, platform):
        m = Module()
        dpi = platform.request("dpi", 0)
        panel = platform.request("hub75", 0)

        # 'pix' domain clocked by the Pi's DPI pixel clock (JP8 L18).
        m.domains.pix = ClockDomain("pix")
        m.d.comb += ClockSignal("pix").eq(dpi.pclk.i)
        # 'scan' domain = 40 MHz PLL from the 12 MHz 'sync' reference -> 20 MHz HUB75
        # shift. Dropped from 60/30 MHz: 30 MHz shift bled color toward white per panel
        # over the 6-deep chain (data lines not settling); 20 MHz is comfortably within
        # the v1-wall regime (37.5 MHz clean over 4). Fallback PLL12to30 (15 MHz) if needed.
        m.submodules.pll = PLL12to40(domain="scan")

        tr = DpiToHub75(width=WIDTH, scan=SCAN, chains=1, planes=10, unit=16,
                        guard=40, vsync_active=1, max_w=1024, max_h=1024)
        m.submodules.tr = DomainRenamer({"sync": "scan"})(tr)   # scan-out at 60 MHz
        m.d.comb += [
            tr.de.eq(dpi.de.i),
            tr.vsync.eq(dpi.vsync.i),
            tr.pixel_in.eq(dpi.data.i),          # confirmed rgb888, no swizzle
            panel.rgb.o.eq(tr.rgb),
            panel.addr.o.eq(tr.addr),
            panel.clk.o.eq(tr.clk),
            panel.lat.o.eq(tr.lat),
            panel.oe.o.eq(tr.blank),
            platform.request("led", 7).o.eq(tr.frame),
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
