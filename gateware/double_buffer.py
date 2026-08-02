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

CDC — the crux. The writer raises a 1-bit toggle when a frame's capture COMPLETES (last
captured row done). The reader carries that toggle across with a 2-FF synchronizer,
edge-detects it, and — only at its OWN frame boundary (`rd_frame_end`, so no mid-scan
switch) — flips `front`. One bit crosses each way: the toggle forward, `front` back.

The back-crossing is what makes the handoff timing-ratio-proof (added for the 120 Hz DPI
experiment). The writer captures a DPI frame only if the reader has CONSUMED the previous
publication (front == producer_toggle at frame_start — they agree exactly when nothing is
pending, see the phase argument at the writer); otherwise it SKIPS the whole source frame
(`skip` pulses) and re-checks at the next one. A capture therefore only ever lands in the
buffer the reader is neither displaying nor about to display. Slow readers now DROP
frames instead of tearing.

History: the toggle must fire at capture COMPLETION, not at the next frame's first pixel
— the reader takes up to one scan frame to act, and a writer already filling the reader's
front buffer shows a mix of two frames, striped at the 16-row scan structure (seen on the
wall 2026-07-29; the sim missed it because the capstone fed identical frames). The
completion-fired toggle alone was safe only while scan_frame_period < DPI_period −
capture_time (9.8 < 12.4 ms at 60 Hz — but 7.1 vs ~6.1 ms at 122 Hz, hence the skip
gate). A stale `front` through the synchronizer can only cause a spurious skip, never a
spurious capture: front only ever equals producer_toggle after a real consumption.
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

        # Diagnostic (pix domain): 1-cycle pulse at a frame_start the writer sat out
        # because the reader hadn't consumed the previous frame yet (source frame drop).
        self.skip = Signal()

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

        # --- Writer (pix domain): capture opposite the reader's front, or skip ---
        # `front` lives in the sync domain (reader section below) and crosses back here
        # through its own 2-FF synchronizer. At frame_start the writer is caught up iff
        # front_pix == producer_toggle: front flips once per consumption, the toggle once
        # per publication, both start at 0, and the writer never runs more than one
        # publication ahead — so mod-2 equality means "everything published is consumed".
        # Caught up -> capture into ~front (the buffer the reader is NOT showing; it
        # cannot flip mid-capture because nothing is pending until THIS capture
        # completes). Behind -> the reader may adopt the other buffer at any moment, so
        # NEITHER buffer is safe for a whole frame: skip this source frame entirely.
        # Startup (all zeros) is caught up -> frame 1 lands in buf1 while the reader
        # shows zeroed buf0, same first-light behavior as the old strict alternation.
        #
        # `frame_start` coincides with a frame's FIRST pixel, so the capture decision
        # must take effect for that pixel too (comb Mux), else the frame splits across
        # buffers; wr_buf/cap_act hold it for the rest of the frame.
        front = Signal(init=0)               # reader's display buffer (sync domain)
        front_pix = Signal()
        m.submodules.front_sync = FFSynchronizer(front, front_pix, o_domain="pix")
        wr_buf = Signal(init=0)              # buffer this frame is captured into
        cap_active = Signal(init=0)          # 0 = this source frame is being skipped
        producer_toggle = Signal(init=0)     # flips when a frame's CAPTURE completes
        caught_up = Signal()
        cap_buf = Signal()
        cap_act = Signal()
        m.d.comb += [
            caught_up.eq(front_pix == producer_toggle),
            cap_buf.eq(Mux(self.wr_frame_start, ~front_pix, wr_buf)),
            cap_act.eq(Mux(self.wr_frame_start, caught_up, cap_active)),
            self.skip.eq(self.wr_frame_start & ~caught_up),
        ]
        with m.If(self.wr_frame_start):
            m.d.pix += [wr_buf.eq(~front_pix), cap_active.eq(caught_up)]

        # Swap notice fires when the LAST CAPTURED ROW completes (wr_y rises past H-1) —
        # NOT at the next frame_start — and only for frames actually captured. The
        # capture window [frame_start, row H) therefore always PRECEDES the publication,
        # so the reader's flip can never race an in-progress write. The reader consumes
        # at its own frame boundary, up to one scan frame later; with the skip gate that
        # latency costs dropped source frames when scan_frame_period > DPI_period −
        # capture_time (the 120 Hz modes), never a torn one. History: the original
        # swap-on-frame_start protocol displayed the buffer being overwritten for up to
        # a scan frame every DPI frame — the 16-row-banded tearing seen on the wall
        # 2026-07-29.
        H = 2 * S * N
        y_done = Signal()
        y_done_r = Signal()
        m.d.comb += y_done.eq(self.wr_y >= H)
        m.d.pix += y_done_r.eq(y_done)
        with m.If(y_done & ~y_done_r & cap_act):
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
                        wp.en.eq(self.wr_valid & in_bounds & cap_act
                                 & (cap_buf == b) & (chain == c) & (half == h)),
                    ]

        # --- Reader (sync domain): read both buffers, output the front one ---
        # (`front` itself is declared with the writer above — it crosses back there.)
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
