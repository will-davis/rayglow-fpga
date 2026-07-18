"""Amaranth platform for the Lattice ECP5 Evaluation Board (LFE5UM5G-85F-EVN).

Pin data from the board User Guide, FPGA-EB-02017-1.3 (.reference/ecp5-evn/), tables
cited inline. Only Phase 0 resources are defined; the JP8 DPI ingest (Phase 2) and
J32/J33 HUB75 outputs (Phase 3) land with their phases so every pin here is exercised.
"""

from amaranth.build import Attrs, Clock, Pins, PinsN, Resource
from amaranth.vendor import LatticeECP5Platform


class ECP5EVNPlatform(LatticeECP5Platform):
    device = "LFE5UM5G-85F"
    package = "BG381"
    speed = "8"

    # UG Table 4.1: 12 MHz from the FT2232H — only alive while USB is plugged and JP2 is
    # installed (JP1 removed). Fine on the bench; standalone designs must switch to the
    # X2 200 MHz oscillator (Y19/W20, LVDS, JP9 open) + PLL — resource added in Phase 0
    # once its bank IO_TYPE is verified on hardware.
    default_clk = "clk12"

    resources = [
        Resource("clk12", 0, Pins("A10", dir="i"), Clock(12e6), Attrs(IO_TYPE="LVCMOS33")),
        # UG Table 7.4: eight red LEDs, bank 1, lit when driven low.
        *[
            Resource("led", i, PinsN(pin, dir="o"), Attrs(IO_TYPE="LVCMOS33"))
            for i, pin in enumerate("A13 A12 B19 A18 B18 C17 A17 B17".split())
        ],
        # UG Table 7.3: SW4, the general-purpose push button, drives low when pressed
        # (schematic Fig A.9: 10k pull-up + 100nF, so it arrives debounced-ish).
        Resource("button", 0, PinsN("P4", dir="i"), Attrs(IO_TYPE="LVCMOS33")),
        # UG Table 7.1 / schematic Fig A.10: SW5 eight-position DIP, 4.7k pull-ups,
        # closed (ON) = grounded, hence PinsN. Switches 1-3 bank 6, 4-8 bank 1.
        # NB Table 2.1 claims VCCIO1 defaults to 2.5 V but Fig A.11 shows the 0-ohm
        # strap (R105) from +3.3 V populated — LVCMOS33 matches the schematic; meter
        # VCCIO1 (TP27) if bank-1 IO ever misbehaves.
        *[
            Resource("switch", i, PinsN(pin, dir="i"), Attrs(IO_TYPE="LVCMOS33"))
            for i, pin in enumerate("J1 H1 K1 E15 D16 B16 C16 A16".split())
        ],
    ]

    connectors = []
