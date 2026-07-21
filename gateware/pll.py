"""EHXPLLL wrapper: multiply the 12 MHz 'sync' clock into a named output domain.

Divider params come from `ecppll -i 12 -o <MHz>`. For FEEDBK_PATH=CLKOP the output is
f_out = 12 * CLKFB_DIV / CLKI_DIV and the VCO = f_out * CLKOP_DIV must land in the
400-800 MHz window (ECP5 datasheet sysCLOCK PLL section). The output domain is held in
reset until the PLL asserts LOCK — logic clocked from an unlocked PLL sees garbage edges.

Presets (name = output freq; the HUB75 shift clock is half the scan-domain clock, since
the scan-out uses 2 cycles per pixel):
    PLL12to60  60 MHz -> 30 MHz shift   (aggressive; fine for <=~4-panel chains)
    PLL12to40  40 MHz -> 20 MHz shift   (6-panel chain default)
    PLL12to30  30 MHz -> 15 MHz shift   (very conservative fallback for long chains)
"""

from amaranth import ClockDomain, ClockSignal, Elaboratable, Instance, Module, ResetSignal, Signal


class EcpPll(Elaboratable):
    """One CLKOP EHXPLLL from the 12 MHz 'sync' reference into `domain`."""

    def __init__(self, *, domain, out_mhz, clki_div, clkfb_div, clkop_div, cphase):
        self.domain = domain
        self.locked = Signal()
        self._p = (out_mhz, clki_div, clkfb_div, clkop_div, cphase)

    def elaborate(self, platform):
        m = Module()
        out_mhz, clki_div, clkfb_div, clkop_div, cphase = self._p
        clkop = Signal()
        m.submodules.ehxplll = Instance(
            "EHXPLLL",
            a_FREQUENCY_PIN_CLKI="12",
            a_FREQUENCY_PIN_CLKOP=str(out_mhz),
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
            p_CLKI_DIV=clki_div,
            p_CLKOP_ENABLE="ENABLED",
            p_CLKOP_DIV=clkop_div,
            p_CLKOP_CPHASE=cphase,
            p_CLKOP_FPHASE=0,
            p_FEEDBK_PATH="CLKOP",
            p_CLKFB_DIV=clkfb_div,
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


def PLL12to60(domain="fast"):
    return EcpPll(domain=domain, out_mhz=60, clki_div=1, clkfb_div=5, clkop_div=10, cphase=4)


def PLL12to40(domain="scan"):
    return EcpPll(domain=domain, out_mhz=40, clki_div=3, clkfb_div=10, clkop_div=15, cphase=7)


def PLL12to30(domain="scan"):
    return EcpPll(domain=domain, out_mhz=30, clki_div=2, clkfb_div=5, clkop_div=20, cphase=9)
