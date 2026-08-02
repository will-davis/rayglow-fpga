"""DpiToHub75 — the whole translation layer: Pi DPI video in, HUB75 scan-out out.

    de/vsync/pixel_in (pix domain)          rgb/addr/clk/lat/blank (sync domain)
            │                                          ▲
         DpiIn ──► DoubleBuffer (pix write / sync read) ──► Hub75Core(external_fb)
        (pix)          swap on core.frame                      (sync)

Two clock domains meet inside DoubleBuffer; everything upstream of it is `pix` (the Pi's
pixel clock), everything downstream is `sync` (the scan-out clock). This is the Phase 2
top-level; a board top wraps it with the DPI input pins (JP8) and the HUB75 output pins.
"""

from amaranth import DomainRenamer, Elaboratable, Module, Signal

from .double_buffer import DoubleBuffer
from .dpi import DpiIn
from .scanout import Hub75Core


class DpiToHub75(Elaboratable):
    def __init__(self, *, width, scan=16, chains=1, planes=10, unit=4, unit_max=None,
                 guard=0, overlap=False, splits=None, lut_init=None, vsync_active=1,
                 max_w=512, max_h=256, expect_dpi_w=None):
        self.width = width
        self.scan = scan
        self.chains = chains
        self.planes = planes
        self._unit_init = unit        # constructor int (self.unit is the runtime Signal)
        self.unit_max = unit_max
        self.guard = guard
        self.overlap = overlap
        self.splits = splits
        self.lut_init = lut_init
        self.vsync_active = vsync_active
        self.max_w = max_w
        self.max_h = max_h
        self.expect_dpi_w = expect_dpi_w   # DPI mode's hactive (None = check off)

        # DPI in (pix domain)
        self.de = Signal()
        self.vsync = Signal()
        self.pixel_in = Signal(24)
        # Runtime brightness (scan domain): passthrough of Hub75Core.unit — the LSB
        # display time; scales all BCM planes linearly. Undriven = constructor default.
        um = unit_max if unit_max is not None else unit
        self.unit = Signal(range(um + 1), init=unit)
        # HUB75 out (sync domain)
        self.clk = Signal()
        self.lat = Signal()
        self.blank = Signal(init=1)
        self.addr = Signal(range(scan))
        self.rgb = Signal(6 * chains)
        self.frame = Signal()
        # Diagnostics (pix domain), armed after the first VSYNC:
        self.err_short = Signal()   # latch: some line captured SHORT (DE glitch class)
        self.err_long = Signal()    # latch: some line captured LONG (PCLK-ringing class)
        self.err_blink = Signal()   # ~0.4 s pulse per bad line (error-rate visibility)
        self.skip_blink = Signal()  # stretched pulse per DROPPED source frame (reader
                                    # behind — expected duty cycle of the 120 Hz modes)

    def elaborate(self, platform):
        m = Module()
        m.submodules.dpi = dpi = DomainRenamer("pix")(
            DpiIn(max_w=self.max_w, max_h=self.max_h, vsync_active=self.vsync_active,
                  expect_w=self.expect_dpi_w))
        with m.If(dpi.line_short):
            m.d.pix += self.err_short.eq(1)
        with m.If(dpi.line_long):
            m.d.pix += self.err_long.eq(1)
        blink = Signal(23)                        # ~0.4 s at a 12.5 MHz pixel clock
        with m.If(dpi.line_short | dpi.line_long):
            m.d.pix += blink.eq(2**23 - 1)
        with m.Elif(blink != 0):
            m.d.pix += blink.eq(blink - 1)
        m.d.comb += self.err_blink.eq(blink != 0)
        m.submodules.db = db = DoubleBuffer(
            width=self.width, scan=self.scan, chains=self.chains)
        # Same stretch for dropped source frames (~0.17 s at 25 MHz): dark = the scan is
        # consuming every source frame; solid = steady dropping (normal at ~122 Hz DPI,
        # where the handoff budget predicts ~15 % skips — see double_buffer's docstring).
        skip_stretch = Signal(22)
        with m.If(db.skip):
            m.d.pix += skip_stretch.eq(2**22 - 1)
        with m.Elif(skip_stretch != 0):
            m.d.pix += skip_stretch.eq(skip_stretch - 1)
        m.d.comb += self.skip_blink.eq(skip_stretch != 0)
        m.submodules.core = core = Hub75Core(
            width=self.width, scan=self.scan, chains=self.chains, planes=self.planes,
            unit=self._unit_init, unit_max=self.unit_max, guard=self.guard,
            overlap=self.overlap, splits=self.splits, lut_init=self.lut_init,
            external_fb=True)

        m.d.comb += [dpi.de.eq(self.de), dpi.vsync.eq(self.vsync),
                     dpi.pixel_in.eq(self.pixel_in)]
        m.d.comb += [db.wr_x.eq(dpi.x), db.wr_y.eq(dpi.y), db.wr_pixel.eq(dpi.pixel),
                     db.wr_valid.eq(dpi.valid), db.wr_frame_start.eq(dpi.frame_start)]
        m.d.comb += [db.rd_addr.eq(core.fb_addr), core.unit.eq(self.unit)]
        for i in range(2 * self.chains):
            m.d.comb += core.fb_data[i].eq(db.rd_data[i])
        m.d.comb += db.rd_frame_end.eq(core.frame)
        m.d.comb += [self.clk.eq(core.clk), self.lat.eq(core.lat), self.blank.eq(core.blank),
                     self.addr.eq(core.addr), self.rgb.eq(core.rgb), self.frame.eq(core.frame)]
        return m
