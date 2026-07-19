"""Minimal 8N1 UART, both directions — the project's first real FSMs.

Framing: idle high; start bit low, 8 data bits LSB-first, stop bit high. Each bit lasts
`divisor` clock cycles, so baud = clk / divisor (12 MHz / 104 = 115,385 ~ 115,200 +0.16 %,
well inside the ~2 % per-frame tolerance UARTs allow since they resync on every start edge).

The receiver double-registers rx through FFSynchronizer first: rx is async to our clock,
and sampling an async signal straight into an FSM invites metastability.
"""

from amaranth import Cat, Module, Signal
from amaranth.lib import wiring
from amaranth.lib.cdc import FFSynchronizer
from amaranth.lib.wiring import In, Out


class UartTx(wiring.Component):
    data: In(8)
    valid: In(1)
    ready: Out(1)
    tx: Out(1, init=1)

    def __init__(self, divisor):
        self.divisor = divisor
        super().__init__()

    def elaborate(self, platform):
        m = Module()
        timer = Signal(range(self.divisor))
        bits = Signal(range(11))  # bit periods left: start + 8 data + stop
        shreg = Signal(9)         # data LSB-first, then stop

        m.d.comb += self.ready.eq(bits == 0)

        with m.If(self.ready & self.valid):
            m.d.sync += [
                self.tx.eq(0),                    # start bit, immediately
                shreg.eq(Cat(self.data, 1)),
                bits.eq(10),
                timer.eq(self.divisor - 1),
            ]
        with m.Elif(bits != 0):
            with m.If(timer == 0):
                m.d.sync += [bits.eq(bits - 1), timer.eq(self.divisor - 1)]
                with m.If(bits != 1):             # bits==1: stop period just finished
                    m.d.sync += [self.tx.eq(shreg[0]), shreg.eq(shreg[1:])]
            with m.Else():
                m.d.sync += timer.eq(timer - 1)
        return m


class UartRx(wiring.Component):
    rx: In(1, init=1)
    data: Out(8)
    valid: Out(1)  # strobes for one cycle per good frame; framing errors drop silently

    def __init__(self, divisor):
        self.divisor = divisor
        super().__init__()

    def elaborate(self, platform):
        m = Module()
        rx_sync = Signal(init=1)
        m.submodules.sync_rx = FFSynchronizer(self.rx, rx_sync, init=1)

        timer = Signal(range(self.divisor + self.divisor // 2))
        bits = Signal(range(9))
        shreg = Signal(8)

        m.d.sync += self.valid.eq(0)

        with m.FSM():
            with m.State("IDLE"):
                with m.If(~rx_sync):              # falling edge: candidate start bit
                    m.d.sync += timer.eq(self.divisor // 2 - 1)
                    m.next = "START"
            with m.State("START"):                # sample mid-start to reject glitches
                with m.If(timer == 0):
                    with m.If(~rx_sync):
                        m.d.sync += [timer.eq(self.divisor - 1), bits.eq(8)]
                        m.next = "DATA"
                    with m.Else():
                        m.next = "IDLE"
                with m.Else():
                    m.d.sync += timer.eq(timer - 1)
            with m.State("DATA"):                 # sample mid-bit, LSB arrives first
                with m.If(timer == 0):
                    m.d.sync += [
                        shreg.eq(Cat(shreg[1:], rx_sync)),
                        bits.eq(bits - 1),
                        timer.eq(self.divisor - 1),
                    ]
                    with m.If(bits == 1):
                        m.next = "STOP"
                with m.Else():
                    m.d.sync += timer.eq(timer - 1)
            with m.State("STOP"):                 # stop bit must be high, else drop frame
                with m.If(timer == 0):
                    with m.If(rx_sync):
                        m.d.sync += [self.data.eq(shreg), self.valid.eq(1)]
                    m.next = "IDLE"
                with m.Else():
                    m.d.sync += timer.eq(timer - 1)
        return m
