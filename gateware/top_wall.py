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

from amaranth import (Cat, ClockDomain, ClockSignal, DomainRenamer, Elaboratable,
                      Module, Mux, Signal)
from amaranth.build import Attrs, Pins, Resource, Subsignal
from amaranth.lib.cdc import FFSynchronizer

from .pll import PLL12to40, PLL12to48, PLL12to60
from .platform import ECP5EVNPlatform
from .translator import DpiToHub75

NUM_CHAINS = 4          # 2 = one HAT (384x64, first bring-up); 4 = two HATs (full wall)
WIDTH, SCAN = 384, 16

# Shift-clock SI experiment knobs (2026-08-01). The SI cliff sits between 20 MHz shift
# (40 MHz scan, proven clean) and 30 MHz (60 MHz scan, cascading skew from ~panel 3).
# SCAN_PLL picks the scan clock; WALL_SLEW picks the output edge rate into the HATs —
# "SLOW" was a leftover from unbuffered direct-drive; "FAST" buys timing margin at the
# '245 inputs (Will's 22R-made-it-worse datum says the edges were already too lazy).
SCAN_PLL = PLL12to48    # refresh @ B=11/U=8/splits: 60 MHz->175.5 Hz, 48->140.4, 40->117.0
WALL_SLEW = "SLOW"

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
        # 60 MHz scan -> 30 MHz HUB75 shift. Precedent: these HATs ran v1 at 37.5 MHz
        # over 4-panel chains; this is 30 over 6. Refresh 117.9 -> 176.9 Hz at identical
        # brightness/duty. Watch for the color-bleed-to-white SI signature + D9-D11; the
        # fallback is PLL12to40 (one line).
        m.submodules.pll = SCAN_PLL(domain="scan")

        # overlap=True + slot-major schedule with MSB subfield splitting: plane 10 shows
        # as 4 quarter-slots and plane 9 as 2 halves, spread across the sweep — 75 % of
        # each pixel's light arrives ~4x per frame (effective motion sampling ~700 Hz)
        # for ~0.7 % refresh cost: ~175.5 Hz at 77 % duty, full brightness. The 16-row
        # motion seam is scan physics; this shrinks its amplitude by ~the split factor.
        tr = DpiToHub75(width=WIDTH, scan=SCAN, chains=NUM_CHAINS, planes=11, unit=8,
                        unit_max=16, guard=40, overlap=True, splits={9: 2, 10: 4},
                        vsync_active=1, max_w=1024, max_h=1024,
                        expect_dpi_w=WIDTH)             # DPI hactive == wall width (384)
        m.submodules.tr = DomainRenamer({"sync": "scan"})(tr)

        # Hardware brightness knob: SW5 positions 1-4 = a 4-bit code (position 1 = LSB).
        # All OFF -> default unit=8 (today's brightness). Any other pattern -> unit 1-15:
        # 1 ~ 12 % ... 15 ~ 190 %. Dimmer also means faster refresh; brighter, slower
        # (71.8 Hz at 15). Synchronized into the scan domain; a mid-frame change just
        # takes effect at the next plane latch.
        sw_raw = Cat(platform.request("switch", i).i for i in range(4))
        sw = Signal(4)
        m.submodules.sw_sync = FFSynchronizer(sw_raw, sw, o_domain="scan")
        m.d.comb += tr.unit.eq(Mux(sw == 0, 8, sw))
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
            # Capture-health cluster (armed after first VSYNC — startup partials ignored):
            platform.request("led", 6).o.eq(tr.err_long),    # D11: LONG lines = PCLK ringing
            platform.request("led", 5).o.eq(tr.err_short),   # D10: SHORT lines = DE glitches
            platform.request("led", 4).o.eq(tr.err_blink),   # D9: blinks ~0.4s per bad line
        ]
        return m


if __name__ == "__main__":
    rgb_pins = " ".join(CHAIN_RGB[:NUM_CHAINS])          # 6*N balls, chain-major
    plat = ECP5EVNPlatform()
    plat.add_resources([
        Resource("dpi", 0,
                 # HYSTERESIS=ON (Schmitt-style input) on the two edge-critical lines:
                 # if the 40-pin ribbon rings at 12.5 MHz, this filters the double-edges.
                 Subsignal("pclk", Pins("L18", dir="i"),
                           Attrs(IO_TYPE="LVCMOS33", HYSTERESIS="ON")),
                 Subsignal("de", Pins("L17", dir="i"),
                           Attrs(IO_TYPE="LVCMOS33", HYSTERESIS="ON")),
                 Subsignal("vsync", Pins("T17", dir="i"), Attrs(IO_TYPE="LVCMOS33")),
                 Subsignal("data", Pins(DPI_DATA, dir="i"), Attrs(IO_TYPE="LVCMOS33"))),
        Resource("wall", 0,
                 Subsignal("rgb", Pins(rgb_pins, dir="o")),
                 Subsignal("addr", Pins(ADDR_BALLS, dir="o")),
                 Subsignal("clk", Pins(CLK_BALL, dir="o")),
                 Subsignal("lat", Pins(LAT_BALL, dir="o")),
                 Subsignal("oe", Pins(OE_BALL, dir="o")),
                 Attrs(IO_TYPE="LVCMOS33", DRIVE="8", SLEWRATE=WALL_SLEW)),
    ])
    plat.build(Top(), do_program=False)
