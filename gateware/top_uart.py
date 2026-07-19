"""Phase 0 UART milestone: echo console + beacon + ASCII on the LEDs.

Sends '.' every ~2.8 s (proves TX alone, even if RX wiring is bad). Every byte received
is echoed back (proves RX) and its bit pattern is shown on the 8 LEDs. 115,200 baud 8N1
on PMOD J31: pin 1 = FPGA TX, pin 2 = FPGA RX, pin 5 = GND.

Build + load:
    uv run python -m gateware.top_uart
    openFPGALoader -b ecp5_evn build/top.bit
"""

from amaranth import Cat, Elaboratable, Module, Signal

from .platform import ECP5EVNPlatform
from .uart import UartRx, UartTx

BAUD_DIVISOR = 104  # 12 MHz / 104 = 115,385 baud (+0.16 % vs 115,200)


class Top(Elaboratable):
    def elaborate(self, platform):
        m = Module()
        pins = platform.request("uart", 0)
        m.submodules.tx = tx = UartTx(divisor=BAUD_DIVISOR)
        m.submodules.rx = rx = UartRx(divisor=BAUD_DIVISOR)
        m.d.comb += [pins.tx.o.eq(tx.tx), rx.rx.eq(pins.rx.i)]

        last = Signal(8)
        leds = Cat(platform.request("led", i).o for i in range(8))
        m.d.comb += leds.eq(last)

        beat = Signal(25)  # bit 24 rises every ~2.8 s at 12 MHz
        beat_prev = Signal()
        m.d.sync += [beat.eq(beat + 1), beat_prev.eq(beat[-1])]

        pend_echo = Signal()
        pend_beacon = Signal()

        with m.If(tx.ready):  # echo has priority over the beacon
            with m.If(pend_echo):
                m.d.comb += [tx.data.eq(last), tx.valid.eq(1)]
                m.d.sync += pend_echo.eq(0)
            with m.Elif(pend_beacon):
                m.d.comb += [tx.data.eq(ord(".")), tx.valid.eq(1)]
                m.d.sync += pend_beacon.eq(0)

        # These come AFTER the consumers so a same-cycle set wins over the clear.
        with m.If(beat[-1] & ~beat_prev):
            m.d.sync += pend_beacon.eq(1)
        with m.If(rx.valid):
            m.d.sync += [last.eq(rx.data), pend_echo.eq(1)]
        return m


if __name__ == "__main__":
    ECP5EVNPlatform().build(Top(), do_program=False)
