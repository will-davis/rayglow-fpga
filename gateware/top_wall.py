"""Phase 3 board top: the full wall over 2 or 4 chains, level-shifted by RayGLow HAT(s).

Same DPI-in / HUB75-out translator as top_translator, but multi-chain: N chains each a
384-wide strip = one tile row (no serpentine; chain k = wall row k). Scan-out runs in a
40 MHz PLL 'scan' domain (20 MHz shift, the value that ran the 6-panel chain clean).

Level shifting reuses Will's RP2350-HUB75-HAT boards (~/Projects/rayglow/hardware): each
HAT's 4x SN74AHCT245 buffer TWO chains, always-enabled (no chip-select). The ECP5 drives
each HAT's J1 socket at the RP2350-PiZero GPIO positions — passive wiring, mapped in
hardware/RAYGLOW-HAT-ADAPTER.md. NUM_CHAINS=2 => one HAT (384x64, top two rows);
NUM_CHAINS=4 => two HATs (384x128, full wall).

ECP5 output balls (bank 7, J32/J33, 3.3 V; AHCT TTL inputs accept 3.3 V):
  chain k RGB = CHAIN_RGB[k] (R1 G1 B1 R2 G2 B2);  addr A-D + CLK/LAT/OE shared (fanned
  to every HAT's control inputs). Full 4-chain map fits J32 (chains 0-2 RGB) + J33
  (chain 3 RGB + all control).

Build + load:  uv run python -m gateware.top_wall
               openFPGALoader -b ecp5_evn build/top.bit
"""

from amaranth import ClockDomain, ClockSignal, DomainRenamer, Elaboratable, Module
from amaranth.build import Attrs, Pins, Resource, Subsignal

from .pll import PLL12to40
from .platform import ECP5EVNPlatform
from .translator import DpiToHub75

NUM_CHAINS = 4          # 2 = one HAT (384x64, first bring-up); 4 = two HATs (full wall)
WIDTH, SCAN = 384, 16

# Per-chain RGB balls (R1 G1 B1 R2 G2 B2). Chains 0-2 on J32, chain 3 on J33.
CHAIN_RGB = [
    "A5 A4 C5 B5 B4 C4",
    "B3 A3 D5 E4 D3 C3",
    "E3 F4 F5 E5 B1 A2",
    "C2 B2 D1 C1 E1 D2",
]
ADDR_BALLS = "G5 H4 H3 H5"       # A B C D  (J33)
CLK_BALL, LAT_BALL, OE_BALL = "F3", "G3", "E2"   # (J33)
DPI_DATA = "U17 U18 T18 R18 U19 T19 U20 R20 T20 P20 P18 N20 " \
           "P19 N19 T16 R17 P16 R16 N17 P17 M17 N18 N16 M18"   # D0..D23 = GPIO4..27


class Top(Elaboratable):
    def elaborate(self, platform):
        m = Module()
        dpi = platform.request("dpi", 0)
        wall = platform.request("wall", 0)

        # Capture on the FALLING PCLK edge: the RP1 drives DPI data on the RISING edge
        # (mode flag +CK), so rising-edge capture samples right at the data transition —
        # fine at 3.5 MHz, marginal at 12.5 MHz (single-row glitches seen on the wall
        # 2026-07-29/30). Falling-edge sampling lands mid-eye, half a period of margin
        # each side. LED D11 (line_err) latches if any malformed line is ever captured.
        m.domains.pix = ClockDomain("pix")
        m.d.comb += ClockSignal("pix").eq(~dpi.pclk.i)
        m.submodules.pll = PLL12to40(domain="scan")     # 20 MHz HUB75 shift

        tr = DpiToHub75(width=WIDTH, scan=SCAN, chains=NUM_CHAINS, planes=10, unit=16,
                        guard=40, vsync_active=1, max_w=1024, max_h=1024,
                        expect_dpi_w=WIDTH)             # DPI hactive == wall width (384)
        m.submodules.tr = DomainRenamer({"sync": "scan"})(tr)
        m.d.comb += [
            tr.de.eq(dpi.de.i),
            tr.vsync.eq(dpi.vsync.i),
            tr.pixel_in.eq(dpi.data.i),
            wall.rgb.o.eq(tr.rgb),
            wall.addr.o.eq(tr.addr),
            wall.clk.o.eq(tr.clk),
            wall.lat.o.eq(tr.lat),
            wall.oe.o.eq(tr.blank),
            platform.request("led", 7).o.eq(tr.frame),
            platform.request("led", 6).o.eq(tr.line_err),   # D11: capture-error latch
        ]
        return m


if __name__ == "__main__":
    rgb_pins = " ".join(CHAIN_RGB[:NUM_CHAINS])          # 6*N balls, chain-major
    plat = ECP5EVNPlatform()
    plat.add_resources([
        Resource("dpi", 0,
                 Subsignal("pclk", Pins("L18", dir="i")),
                 Subsignal("de", Pins("L17", dir="i")),
                 Subsignal("vsync", Pins("T17", dir="i")),
                 Subsignal("data", Pins(DPI_DATA, dir="i")),
                 Attrs(IO_TYPE="LVCMOS33")),
        Resource("wall", 0,
                 Subsignal("rgb", Pins(rgb_pins, dir="o")),
                 Subsignal("addr", Pins(ADDR_BALLS, dir="o")),
                 Subsignal("clk", Pins(CLK_BALL, dir="o")),
                 Subsignal("lat", Pins(LAT_BALL, dir="o")),
                 Subsignal("oe", Pins(OE_BALL, dir="o")),
                 Attrs(IO_TYPE="LVCMOS33", DRIVE="8", SLEWRATE="SLOW")),
    ])
    plat.build(Top(), do_program=False)
