"""Hardware-path bisection: J31 pin 2 (C7, in) wired combinationally to pin 1 (C6, out).

No UART logic — the FPGA is a piece of wire. If the probe hears its own bytes echoed,
both jumpers and the probe's UART bridge are proven and any echo failure lies in
gateware; if not, the C6 jumper / probe RX side is the fault.

Build + load:
    uv run python -m gateware.top_wire_loop
    openFPGALoader -b ecp5_evn build/top.bit
"""

from amaranth import Elaboratable, Module

from .platform import ECP5EVNPlatform


class Top(Elaboratable):
    def elaborate(self, platform):
        m = Module()
        pins = platform.request("uart", 0)
        m.d.comb += pins.tx.o.eq(pins.rx.i)
        return m


if __name__ == "__main__":
    ECP5EVNPlatform().build(Top(), do_program=False)
