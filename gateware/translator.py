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
                 guard=0, lut_init=None, vsync_active=1, max_w=512, max_h=256):
        self.width = width
        self.scan = scan
        self.chains = chains
        self.planes = planes
        self.unit = unit
        self.unit_max = unit_max
        self.guard = guard
        self.lut_init = lut_init
        self.vsync_active = vsync_active
        self.max_w = max_w
        self.max_h = max_h

        # DPI in (pix domain)
        self.de = Signal()
        self.vsync = Signal()
        self.pixel_in = Signal(24)
        # HUB75 out (sync domain)
        self.clk = Signal()
        self.lat = Signal()
        self.blank = Signal(init=1)
        self.addr = Signal(range(scan))
        self.rgb = Signal(6 * chains)
        self.frame = Signal()

    def elaborate(self, platform):
        m = Module()
        m.submodules.dpi = dpi = DomainRenamer("pix")(
            DpiIn(max_w=self.max_w, max_h=self.max_h, vsync_active=self.vsync_active))
        m.submodules.db = db = DoubleBuffer(
            width=self.width, scan=self.scan, chains=self.chains)
        m.submodules.core = core = Hub75Core(
            width=self.width, scan=self.scan, chains=self.chains, planes=self.planes,
            unit=self.unit, unit_max=self.unit_max, guard=self.guard,
            lut_init=self.lut_init, external_fb=True)

        m.d.comb += [dpi.de.eq(self.de), dpi.vsync.eq(self.vsync),
                     dpi.pixel_in.eq(self.pixel_in)]
        m.d.comb += [db.wr_x.eq(dpi.x), db.wr_y.eq(dpi.y), db.wr_pixel.eq(dpi.pixel),
                     db.wr_valid.eq(dpi.valid), db.wr_frame_start.eq(dpi.frame_start)]
        m.d.comb += db.rd_addr.eq(core.fb_addr)
        for i in range(2 * self.chains):
            m.d.comb += core.fb_data[i].eq(db.rd_data[i])
        m.d.comb += db.rd_frame_end.eq(core.frame)
        m.d.comb += [self.clk.eq(core.clk), self.lat.eq(core.lat), self.blank.eq(core.blank),
                     self.addr.eq(core.addr), self.rgb.eq(core.rgb), self.frame.eq(core.frame)]
        return m
