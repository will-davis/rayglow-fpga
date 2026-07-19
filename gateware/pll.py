"""EHXPLLL wrapper: multiply the 12 MHz 'sync' clock into a named fast domain.

Parameters straight from `ecppll -i 12 -o 60`: VCO = 12 x CLKFB_DIV(5) x CLKOP_DIV(10)
= 600 MHz (legal window 400-800 MHz, ECP5 datasheet sysCLOCK PLL section), CLKOP =
VCO / CLKOP_DIV = 60 MHz, feedback path CLKOP. The new domain is held in reset until
the PLL reports LOCK — logic clocked from an unlocked PLL sees garbage edges.
"""

from amaranth import ClockDomain, ClockSignal, Elaboratable, Instance, Module, ResetSignal, Signal


class PLL12to60(Elaboratable):
    def __init__(self, domain="fast"):
        self.domain = domain
        self.locked = Signal()

    def elaborate(self, platform):
        m = Module()
        clkop = Signal()
        m.submodules.ehxplll = Instance(
            "EHXPLLL",
            a_FREQUENCY_PIN_CLKI="12",
            a_FREQUENCY_PIN_CLKOP="60",
            a_ICP_CURRENT="12",
            a_LPF_RESISTOR="8",
            a_MFG_ENABLE_FILTEROPAMP="1",
            a_MFG_GMCREF_SEL="2",
            p_PLLRST_ENA="DISABLED",
            p_INTFB_WAKE="DISABLED",
            p_STDBY_ENABLE="DISABLED",
            p_DPHASE_SOURCE="DISABLED",
            p_OUTDIVIDER_MUXA="DIVA",
            p_OUTDIVIDER_MUXB="DIVB",
            p_OUTDIVIDER_MUXC="DIVC",
            p_OUTDIVIDER_MUXD="DIVD",
            p_CLKI_DIV=1,
            p_CLKOP_ENABLE="ENABLED",
            p_CLKOP_DIV=10,
            p_CLKOP_CPHASE=4,
            p_CLKOP_FPHASE=0,
            p_FEEDBK_PATH="CLKOP",
            p_CLKFB_DIV=5,
            i_RST=0,
            i_STDBY=0,
            i_CLKI=ClockSignal("sync"),
            i_CLKFB=clkop,
            i_PHASESEL0=0,
            i_PHASESEL1=0,
            i_PHASEDIR=1,
            i_PHASESTEP=1,
            i_PHASELOADREG=1,
            i_PLLWAKESYNC=0,
            i_ENCLKOP=0,
            o_CLKOP=clkop,
            o_LOCK=self.locked,
        )
        m.domains += ClockDomain(self.domain)
        m.d.comb += [
            ClockSignal(self.domain).eq(clkop),
            ResetSignal(self.domain).eq(~self.locked),
        ]
        return m
