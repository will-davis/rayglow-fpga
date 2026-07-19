"""UART round-trip: TX wired to RX in sim, bytes must survive, back-to-back included.

Also bit-samples the TX line against the expected 8N1 frame — the golden-model habit:
don't just test that our RX likes our TX, test the wire format itself.
"""

from amaranth import Module
from amaranth.sim import Simulator

from gateware.uart import UartRx, UartTx

DIVISOR = 8
TEST_BYTES = [0x55, 0x00, 0xFF, 0x72, 0x01]  # alternating, all-low, all-high, 'r', lonely LSB


def _frame(byte):
    return [0] + [(byte >> i) & 1 for i in range(8)] + [1]  # start, LSB-first, stop


def test_tx_wire_format():
    tx = UartTx(divisor=DIVISOR)
    sim = Simulator(tx)
    sim.add_clock(1e-6)

    async def bench(ctx):
        ctx.set(tx.data, 0x72)
        ctx.set(tx.valid, 1)
        await ctx.tick()
        ctx.set(tx.valid, 0)
        seen = []
        for _ in range(10):  # sample mid-bit: tx changes on load/expiry, hold divisor cycles
            for _ in range(DIVISOR // 2):
                await ctx.tick()
            seen.append(ctx.get(tx.tx))
            for _ in range(DIVISOR - DIVISOR // 2):
                await ctx.tick()
        assert seen == _frame(0x72), f"wire format {seen}"

    sim.add_testbench(bench)
    sim.run()


def test_roundtrip_back_to_back():
    m = Module()
    m.submodules.tx = tx = UartTx(divisor=DIVISOR)
    m.submodules.rx = rx = UartRx(divisor=DIVISOR)
    m.d.comb += rx.rx.eq(tx.tx)

    sim = Simulator(m)
    sim.add_clock(1e-6)

    async def bench(ctx):
        for byte in TEST_BYTES:
            while not ctx.get(tx.ready):
                await ctx.tick()
            ctx.set(tx.data, byte)
            ctx.set(tx.valid, 1)
            await ctx.tick()
            ctx.set(tx.valid, 0)
            for _ in range(DIVISOR * 14):
                await ctx.tick()
                if ctx.get(rx.valid):
                    assert ctx.get(rx.data) == byte, f"got {ctx.get(rx.data):#x}, sent {byte:#x}"
                    break
            else:
                raise AssertionError(f"timeout waiting for {byte:#x}")

    sim.add_testbench(bench)
    sim.run()
