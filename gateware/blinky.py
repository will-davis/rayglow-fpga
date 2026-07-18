"""Smallest possible synchronous design: a free-running counter blinks an LED.

The LED is the counter's MSB, so it toggles every 2**period_bits clock cycles — the
canonical "is the toolchain alive" design, and the sim target proving the uv stack works.
"""

from amaranth import Module, Signal
from amaranth.lib import wiring
from amaranth.lib.wiring import Out


class Blinky(wiring.Component):
    led: Out(1)

    def __init__(self, period_bits=22):
        self.period_bits = period_bits
        super().__init__()

    def elaborate(self, platform):
        m = Module()
        counter = Signal(self.period_bits + 1)
        m.d.sync += counter.eq(counter + 1)
        m.d.comb += self.led.eq(counter[-1])
        return m
