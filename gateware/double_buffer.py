"""Double-buffered framebuffer + the pixel-clock <-> scan-out clock-domain crossing.

Two physical buffers, each a set of per-(chain,half) EBR banks. At any instant one buffer
is the DISPLAY buffer (scan-out reads it, `sync` domain) and the other is the CAPTURE
buffer (DPI writes it, `pix` domain) — they are never the same, which is what makes the
output tear-free.

Geometry fold (DPI raster (x,y) -> bank + address), matching patterns.banks_from_image
generalized to N stacked chains:
    chain = y // (2*scan)        # which HUB75 chain (tile row)
    half  = (y % (2*scan)) // scan   # 0 = R1G1B1 (top), 1 = R2G2B2 (bottom)
    addr  = y % scan             # row-address lines A..D
    waddr = addr * width + x

CDC — the crux. The writer strictly ALTERNATES its capture buffer every DPI frame and
raises a 1-bit toggle when a frame's capture COMPLETES (last captured row done). The
reader carries that toggle across with a 2-FF synchronizer, edge-detects it, and — only
at its OWN frame boundary (`rd_frame_end`, so no mid-scan switch) — flips `front`. Only
ONE bit crosses domains.

Disjointness (learned the hard way): the toggle must fire at capture COMPLETION, not at
the next frame's first pixel. The reader takes up to one scan frame to act on it; if the
writer is already filling the reader's front buffer during that window, the panel shows a
mix of two frames, striped at the 16-row scan structure (seen on the wall 2026-07-29 —
the sim missed it because the capstone fed identical frames). With completion-fired
toggles the reader swaps during the writer's idle tail; safe while
scan_frame_period < DPI_period − capture_time (9.8 ms < 12.4 ms today).
"""

from amaranth import Elaboratable, Module, Mux, Signal
from amaranth.lib.cdc import FFSynchronizer
from amaranth.lib.memory import Memory


class DoubleBuffer(Elaboratable):
    def __init__(self, *, width, scan, chains):
        self.width = width
        self.scan = scan
        self.chains = chains
        depth = width * scan

        # Write side (pix domain) — driven from DpiIn.
        self.wr_x = Signal(16)
        self.wr_y = Signal(16)
        self.wr_pixel = Signal(24)
        self.wr_valid = Signal()
        self.wr_frame_start = Signal()

        # Read side (sync / scan-out domain) — wired to Hub75Core's external fb.
        self.rd_addr = Signal(range(depth))
        self.rd_data = [Signal(24, name=f"rd_data_{i}") for i in range(2 * chains)]
        self.rd_frame_end = Signal()

    def elaborate(self, platform):
        m = Module()
        W, S, N = self.width, self.scan, self.chains
        depth = W * S

        mems = [[[Memory(shape=24, depth=depth, init=[]) for _ in range(2)]
                 for _ in range(N)] for _ in range(2)]
        for b in range(2):
            for c in range(N):
                for h in range(2):
                    m.submodules[f"buf{b}_{c}_{h}"] = mems[b][c][h]

        # --- Writer (pix domain): geometry fold + strict buffer alternation ---
        # `frame_start` coincides with a frame's FIRST pixel, so the buffer flip must take
        # effect for that pixel too, else the frame splits across both buffers. cap_buf is
        # the buffer this cycle's pixel lands in (already flipped on frame_start); wr_buf
        # holds it for the rest of the frame. Startup shows ~1 empty frame, then corrects.
        # Phase matters: the reader's front after k toggles is (k mod 2), so frame k must
        # land in buffer (k mod 2) for the reader to adopt the frame just completed.
        # wr_buf init=0 -> the frame_start flip puts frame 1 in buf1 while the reader
        # shows (zeroed) buf0; every later frame writes opposite the reader's front.
        wr_buf = Signal(init=0)              # capture buffer phase (see above)
        producer_toggle = Signal(init=0)     # flips when a frame's CAPTURE completes
        cap_buf = Signal()
        m.d.comb += cap_buf.eq(Mux(self.wr_frame_start, ~wr_buf, wr_buf))
        with m.If(self.wr_frame_start):
            m.d.pix += wr_buf.eq(~wr_buf)

        # Swap notice fires when the LAST CAPTURED ROW completes (wr_y rises past H-1) —
        # NOT at the next frame_start. The reader consumes it at its own frame boundary,
        # so it must have left the old front BEFORE the writer starts the next frame into
        # it: guaranteed iff scan_frame_period < DPI_period − capture_time. Wall today:
        # 9.8 ms < 16.7 − 4.3 ms ✓ (the 480-line mode idles ~73% of the frame after our
        # 128 rows). ⚠ A true vactive=128 mode leaves only the blanking as margin —
        # revisit this handoff if that ever lands. The original swap-on-frame_start
        # protocol displayed the buffer being overwritten for up to a scan frame every
        # DPI frame — the 16-row-banded tearing seen on the wall 2026-07-29.
        H = 2 * S * N
        y_done = Signal()
        y_done_r = Signal()
        m.d.comb += y_done.eq(self.wr_y >= H)
        m.d.pix += y_done_r.eq(y_done)
        with m.If(y_done & ~y_done_r):
            m.d.pix += producer_toggle.eq(~producer_toggle)

        chain = self.wr_y // (2 * S)
        half = (self.wr_y % (2 * S)) // S
        addr = self.wr_y % S
        waddr = Signal(range(depth))
        m.d.comb += waddr.eq(addr * W + self.wr_x)

        # Capture-bounds gate: ignore pixels outside this instance's WxH. Lets a small
        # panel show a crop of a larger DPI frame (bench: top-left 64x32 of the Pi's
        # 384x128). y-overflow is already dropped (no bank matches chain>=N); x needs an
        # explicit guard or waddr would wrap within the bank. In-bounds frames (all sims)
        # are unaffected since wr_x < W always holds there.
        in_bounds = self.wr_x < W
        for b in range(2):
            for c in range(N):
                for h in range(2):
                    wp = mems[b][c][h].write_port(domain="pix")
                    m.d.comb += [
                        wp.addr.eq(waddr),
                        wp.data.eq(self.wr_pixel),
                        wp.en.eq(self.wr_valid & in_bounds
                                 & (cap_buf == b) & (chain == c) & (half == h)),
                    ]

        # --- Reader (sync domain): read both buffers, output the front one ---
        front = Signal(init=0)
        rdata = [[[Signal(24) for _ in range(2)] for _ in range(N)] for _ in range(2)]
        for b in range(2):
            for c in range(N):
                for h in range(2):
                    rp = mems[b][c][h].read_port(domain="sync")
                    m.d.comb += [rp.en.eq(1), rp.addr.eq(self.rd_addr)]
                    m.d.comb += rdata[b][c][h].eq(rp.data)
        for c in range(N):
            for h in range(2):
                m.d.comb += self.rd_data[c * 2 + h].eq(
                    Mux(front, rdata[1][c][h], rdata[0][c][h]))

        # --- CDC: one toggle bit crosses; swap only at the reader's frame boundary ---
        tog_s = Signal()
        m.submodules.tog_sync = FFSynchronizer(producer_toggle, tog_s, o_domain="sync")
        tog_s_r = Signal()
        m.d.sync += tog_s_r.eq(tog_s)
        edge = tog_s ^ tog_s_r
        pending = Signal()
        with m.If(self.rd_frame_end & (pending | edge)):
            m.d.sync += [front.eq(~front), pending.eq(0)]
        with m.Elif(edge):
            m.d.sync += pending.eq(1)
        return m
