"""HUB75 BCM scan-out engine, v1 (sequential: shift -> latch -> display).

Architecture (details + timing math: gateware/SCANOUT.md):

  FB banks (EBR, RGB888, one per chain-half) -> gamma LUT ROM (256 x B, CIE1931)
      -> plane bit-select -> RGB pins        FSM: PRELOAD -> SHIFT -> LATCH -> DISPLAY

Geometry is parametric: `width` pixels per row per chain, `scan` row addresses
(1/16 scan = 16; strip height = 2*scan), `chains` driven in lockstep with shared
ADDR/LAT/OE/CLK and 6 private RGB bits each. `planes` = BCM depth B; `unit` = U,
the LSB display time in clock cycles (plane b displays for U * 2**b cycles).

Per row: for each plane, shift `width` pixels (2 cycles each, CLK high in the
second — data crosses the panel's rising edge mid-slot), pulse LAT once, then
un-blank for the plane's weighted interval. v1 never overlaps shift with display —
simpler to verify; the overlap upgrade is the recorded v2 (ROADMAP Phase 3).

Read pipeline is 2 deep (FB rdata, then LUT rdata), exactly one pixel slot, so
PRELOAD is the 2-cycle pipeline prime and SHIFT slot x issues the read for x+1.

Pin polarity: `blank` drives the panel's OE pin directly (OE is active LOW:
blank=1 -> LEDs off). LED-on time is therefore the cycles blank==0.
"""

from amaranth import Elaboratable, Module, Signal
from amaranth.lib.memory import Memory

from .patterns import cie1931_lut


class Hub75Core(Elaboratable):
    def __init__(self, *, width, scan=16, chains=1, planes=10, unit=4, unit_max=None,
                 banks_init=None, lut_init=None, external_fb=False):
        self.width = width
        self.scan = scan
        self.chains = chains
        self.planes = planes
        self._unit_max = unit_max if unit_max is not None else unit
        self.banks_init = banks_init or [[[], []] for _ in range(chains)]
        self.lut_init = lut_init or cie1931_lut(planes)
        self.external_fb = external_fb

        # LSB display time in clocks — the brightness/refresh knob (rayglow's OE_GAIN).
        # Runtime input; undriven it holds `unit`, so fixed-unit tops/tests are unchanged.
        self.unit = Signal(range(self._unit_max + 1), init=unit)

        # External framebuffer hook (Phase 2): shared read address out, per chain-half
        # RGB888 data in (order [c0h0, c0h1, c1h0, ...]). All banks share one address
        # because scan-out reads the same (addr, x) index from every bank each cycle.
        if external_fb:
            self.fb_addr = Signal(range(width * scan))
            self.fb_data = [Signal(24, name=f"fb_data_{i}") for i in range(2 * chains)]

        self.clk = Signal()                  # panel shift clock
        self.lat = Signal()                  # row latch strobe
        self.blank = Signal(init=1)          # -> panel OE pin (active-low display)
        self.addr = Signal(range(scan))      # row address A..D
        self.rgb = Signal(6 * chains)        # per chain: [R1 G1 B1 R2 G2 B2]
        self.frame = Signal()                # 1-cycle pulse per completed frame

    def elaborate(self, platform):
        m = Module()
        W, S, N, B, UM = self.width, self.scan, self.chains, self.planes, self._unit_max

        plane = Signal(range(B))
        x_read = Signal(range(W))
        read_addr = Signal(range(W * S))
        m.d.comb += read_addr.eq(self.addr * W + x_read)

        # Framebuffer: raw RGB888 per (chain, half), read at [addr*W + x]. Either an
        # internal ROM (default, banks_init) or driven externally (Phase 2 double buffer).
        if self.external_fb:
            m.d.comb += self.fb_addr.eq(read_addr)
            fb_data_sigs = self.fb_data
        else:
            fb_data_sigs = []
            for c in range(N):
                for h in range(2):
                    mem = Memory(shape=24, depth=W * S, init=self.banks_init[c][h])
                    m.submodules[f"fb_{c}_{h}"] = mem
                    port = mem.read_port()
                    m.d.comb += [port.en.eq(1), port.addr.eq(read_addr)]
                    fb_data_sigs.append(port.data)

        # Gamma ROM: one logical Memory, 3 read ports per bank (R,G,B); the
        # synthesizer replicates the underlying EBR to satisfy the port count.
        lut = Memory(shape=B, depth=256, init=self.lut_init)
        m.submodules.lut = lut
        for i, data in enumerate(fb_data_sigs):
            half, chain = i % 2, i // 2
            for ch, sl in enumerate([data[16:24], data[8:16], data[0:8]]):
                port = lut.read_port()
                m.d.comb += [
                    port.en.eq(1),
                    port.addr.eq(sl),
                    self.rgb[chain * 6 + half * 3 + ch].eq(port.data.bit_select(plane, 1)),
                ]

        phase = Signal()                          # pixel slot half: 0=data, 1=CLK high
        xo = Signal(range(W))                     # output slot index
        disp = Signal(range(UM << (B - 1)))       # display countdown (sized for max unit)

        m.d.comb += self.blank.eq(1)              # blanked except in DISPLAY
        m.d.sync += self.frame.eq(0)

        with m.FSM():
            with m.State("PRELOAD"):              # 2 cycles: prime FB+LUT pipeline for x=0
                m.d.sync += phase.eq(~phase)
                with m.If(phase):
                    m.d.sync += xo.eq(0)
                    m.next = "SHIFT"
            with m.State("SHIFT"):
                m.d.comb += [x_read.eq(xo + 1), self.clk.eq(phase)]
                m.d.sync += phase.eq(~phase)
                with m.If(phase):                 # slot complete
                    with m.If(xo == W - 1):
                        m.next = "LATCH"
                    with m.Else():
                        m.d.sync += xo.eq(xo + 1)
            with m.State("LATCH"):                # 1 cycle, row data -> output latches
                m.d.comb += self.lat.eq(1)
                m.d.sync += disp.eq((self.unit << plane) - 1)
                m.next = "DISPLAY"
            with m.State("DISPLAY"):              # un-blank for U * 2**plane cycles
                m.d.comb += self.blank.eq(0)
                with m.If(disp == 0):
                    with m.If(plane == B - 1):
                        m.d.sync += plane.eq(0)
                        with m.If(self.addr == S - 1):
                            m.d.sync += [self.addr.eq(0), self.frame.eq(1)]
                        with m.Else():
                            m.d.sync += self.addr.eq(self.addr + 1)
                    with m.Else():
                        m.d.sync += plane.eq(plane + 1)
                    m.next = "PRELOAD"
                with m.Else():
                    m.d.sync += disp.eq(disp - 1)
        return m
