"""DPI video-timing decoder — the front of the Phase 2 ingest path.

The Pi 5 RP1 emits a parallel-RGB (DPI) stream: a pixel clock (PCLK), a data-enable
(DE, high exactly during active pixels), VSYNC/HSYNC, and RGB888 on 24 data lines
(INTERFACE-CONTRACT §1-2). This module runs in the PIXEL-CLOCK domain and derives the
active-region coordinate (x, y) of each incoming pixel purely from DE + VSYNC — no
dependence on the exact porch/modeline numbers, so it tolerates PCLK/blanking drift:

  x : column within the active line. 0 on the DE rising edge, +1 each active PCLK.
  y : active line within the frame. 0 at frame start, +1 at each DE falling edge.
  frame_start : 1-cycle strobe coincident with the very first active pixel after VSYNC.
  valid : this cycle's (x, y, pixel) is an active pixel to be written to the framebuffer.

DE/VSYNC/RGB are assumed already synchronized to PCLK by the input flip-flops in the
FPGA's I/O ring (they are, coming off registered DPI pins); this block adds only the
one-cycle edge history it needs. VSYNC polarity is a parameter.
"""

from amaranth import Module, Signal
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out


class DpiIn(wiring.Component):
    de: In(1)
    vsync: In(1)
    pixel_in: In(24)

    x: Out(16)
    y: Out(16)
    pixel: Out(24)
    valid: Out(1)
    frame_start: Out(1)

    def __init__(self, *, max_w=512, max_h=256, vsync_active=1):
        self.max_w = max_w
        self.max_h = max_h
        self.vsync_active = vsync_active
        super().__init__()

    def elaborate(self, platform):
        m = Module()

        # Normalize VSYNC to a level where 1 == active, and keep one cycle of history.
        # Both history regs reset to "inactive" so the first real edge is never masked
        # (the active-low first-frame bug the sim caught).
        vs_level = Signal()
        m.d.comb += vs_level.eq(self.vsync if self.vsync_active else ~self.vsync)
        vs_level_r = Signal()
        de_r = Signal()
        m.d.sync += [vs_level_r.eq(vs_level), de_r.eq(self.de)]

        vs_edge = vs_level & ~vs_level_r          # frame boundary
        de_rise = self.de & ~de_r                 # line starts (first active pixel)
        de_fall = ~self.de & de_r                 # line ends

        x = Signal(range(self.max_w))
        y = Signal(range(self.max_h))
        frame_pending = Signal()                  # armed by VSYNC, disarmed at first pixel

        with m.If(self.de):
            m.d.sync += x.eq(x + 1)               # advance for the next active PCLK
        with m.If(de_fall):
            m.d.sync += [x.eq(0), y.eq(y + 1)]    # rewind column, next line

        with m.If(vs_edge):
            m.d.sync += [y.eq(0), frame_pending.eq(1)]
        with m.If(de_rise & frame_pending):
            m.d.sync += frame_pending.eq(0)

        m.d.comb += [
            self.x.eq(x),
            self.y.eq(y),
            self.pixel.eq(self.pixel_in),
            self.valid.eq(self.de),
            self.frame_start.eq(de_rise & frame_pending),
        ]
        return m
