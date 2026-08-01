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

from amaranth import Array, Elaboratable, Module, Signal
from amaranth.lib.memory import Memory

from .patterns import cie1931_lut


class Hub75Core(Elaboratable):
    def __init__(self, *, width, scan=16, chains=1, planes=10, unit=4, unit_max=None,
                 guard=0, overlap=False, splits=None, banks_init=None, lut_init=None,
                 external_fb=False):
        self.width = width
        self.scan = scan
        self.chains = chains
        self.planes = planes
        self.guard = guard            # blanked settle cycles between LATCH and DISPLAY
        self.overlap = overlap        # v2 engine: shift plane b+1 WHILE displaying plane b
        # splits: {plane: n} subdivides plane's display into n equal sub-slots (n a power
        # of two, n <= 2**plane) spread across the sweep — subfield splitting. Each row's
        # light in that plane arrives n times per frame instead of once, multiplying the
        # perceived motion-sampling rate of the brightest content at ~zero time cost
        # (display-bound slots only pay the extra latch+guard). Overlap engine only.
        self.splits = splits or {}
        assert not self.splits or overlap, "splits requires the overlap engine"
        for p, n in self.splits.items():
            assert n & (n - 1) == 0 and n <= (1 << p), f"split {n} of plane {p} invalid"
        self.schedule = self._build_schedule(planes, self.splits)
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

    @staticmethod
    def _build_schedule(planes, splits):
        """Slot list [(plane, dur_shift)] with duration = unit << dur_shift, ordered so
        repeated sub-slots spread across the sweep. Sub-slot i of an n-way split sits at
        fractional position (i+0.5)/n; unsplit plane p at (p+0.5)/planes — merging the
        two orderings interleaves LSB singles between the recurring MSB sub-slots."""
        slots = []
        for p in range(planes):
            n = splits.get(p, 1)
            shift = p - (n.bit_length() - 1)          # duration 2^p split n ways
            for i in range(n):
                pos = (i + 0.5) / n if n > 1 else (p + 0.5) / planes
                slots.append((pos, p, shift))
        slots.sort()
        return [(p, sh) for _, p, sh in slots]

    def elaborate(self, platform):
        m = Module()
        W, S, N, B, UM = self.width, self.scan, self.chains, self.planes, self._unit_max

        plane = Signal(range(B))
        x_read = Signal(range(W))
        # The read path (FB row + LUT plane bit) belongs to the SHIFT side; the panel
        # addr pins + OE duration belong to the DISPLAY side. Sequential mode keeps them
        # equal; overlap mode splits them (shift row/plane runs one latch ahead).
        read_row = Signal(range(S))
        sel_plane = Signal(range(B))
        read_addr = Signal(range(W * S))
        m.d.comb += read_addr.eq(read_row * W + x_read)

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

        # Gamma ROM: ONE small memory per (chain-half, channel) read, not one shared
        # memory with 2N*3 read ports. A single many-read-port memory makes yosys's
        # MEMORY_LIBMAP pass explode (fine at 2 chains / 12 ports, OOMs at 4 / 24) — a
        # pile of independent 1-read ROMs maps trivially instead. Identical gamma; sims
        # unchanged. Each is 256xB, so yosys packs them into LUTRAM or one EBR each.
        for i, data in enumerate(fb_data_sigs):
            half, chain = i % 2, i // 2
            for ch, sl in enumerate([data[16:24], data[8:16], data[0:8]]):
                lut = Memory(shape=B, depth=256, init=self.lut_init)
                m.submodules[f"lut_{i}_{ch}"] = lut
                port = lut.read_port()
                m.d.comb += [
                    port.en.eq(1),
                    port.addr.eq(sl),
                    self.rgb[chain * 6 + half * 3 + ch].eq(
                        port.data.bit_select(sel_plane, 1)),
                ]

        phase = Signal()                          # pixel slot half: 0=data, 1=CLK high
        xo = Signal(range(W))                     # output slot index
        disp = Signal(range((UM << (B - 1)) + 1))  # countdown; +1: overlap loads unit<<p
        if self.guard:
            guard_cnt = Signal(range(self.guard))

        m.d.comb += self.blank.eq(1)              # blanked except while displaying
        m.d.sync += self.frame.eq(0)

        if self.overlap:
            return self._elaborate_overlap(m, disp, guard_cnt if self.guard else None,
                                           read_row, sel_plane, x_read)

        m.d.comb += [read_row.eq(self.addr), sel_plane.eq(plane)]
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
                if self.guard:
                    m.d.sync += guard_cnt.eq(self.guard - 1)
                    m.next = "GUARD"
                else:
                    m.next = "DISPLAY"
            if self.guard:
                with m.State("GUARD"):            # blanked settle: latch -> driver output
                    with m.If(guard_cnt == 0):
                        m.next = "DISPLAY"
                    with m.Else():
                        m.d.sync += guard_cnt.eq(guard_cnt - 1)
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

    def _elaborate_overlap(self, m, disp, guard_cnt, read_row, sel_plane, x_read):
        """v2 engine: the panel's input shift register is loaded with plane b+1 WHILE the
        output latches display plane b — per plane the row costs max(shift, display)
        instead of shift + display. LSB planes hide entirely under the shift; MSB planes
        hide the shift entirely: at W=384/B=10/U=16/guard=40 that's 24478 -> ~20390
        cycles/row = 122.6 Hz at 80.3 % duty (was 102.1 Hz at 66.9 %).

        Split state: (s_row, s_plane) is what the shifter is loading (drives the FB read
        row + LUT bit-select); (addr pins, d_plane) is what the latches are displaying.
        LATCH promotes shift->display, advances the shift pointer, and pulses `frame`
        when the shifter wraps to (0,0) — i.e. while the LAST plane still displays, so
        the double buffer swaps before the next frame's first FB read (the guard cycles
        guarantee the gap). Cold start: disp_valid=0 blanks the first RUN (shift only).
        """
        W, S, B = self.width, self.scan, self.planes
        sched = self.schedule                          # [(plane, dur_shift)] slot list
        L = len(sched)
        SCHED_PLANE = Array(p for p, _ in sched)
        SCHED_SHIFT = Array(sh for _, sh in sched)

        s_row = Signal(range(S))      # shift side: row being loaded
        s_idx = Signal(range(L))      # shift side: schedule slot being loaded
        disp_valid = Signal()         # latches hold real data (0 only at cold start)
        shifting = Signal(init=1)     # cold start: shift (0,0) first, never latch garbage
        sc = Signal(range(2 * W + 2))                 # 2 prime cycles + 2W slot cycles
        rel = Signal(range(2 * W))

        m.d.comb += [read_row.eq(s_row), sel_plane.eq(SCHED_PLANE[s_idx]), rel.eq(sc - 2)]
        shift_done_now = shifting & (sc == 2 * W + 1)

        with m.FSM():
            with m.State("RUN"):
                # -- shifter: 2-cycle pipeline prime, then W slots of 2 cycles --
                with m.If(shifting):
                    m.d.sync += sc.eq(sc + 1)
                    with m.If(sc >= 2):
                        m.d.comb += [x_read.eq(rel[1:] + 1), self.clk.eq(rel[0])]
                    with m.If(shift_done_now):
                        m.d.sync += shifting.eq(0)
                # -- display: OE active while the countdown runs --
                with m.If(disp_valid & (disp != 0)):
                    m.d.comb += self.blank.eq(0)
                    m.d.sync += disp.eq(disp - 1)
                # -- both sides idle: latch the freshly-shifted plane --
                done_shift = ~shifting | shift_done_now
                done_disp = ~disp_valid | (disp == 0)
                with m.If(done_shift & done_disp):
                    m.next = "LATCH"
            with m.State("LATCH"):                    # 1 cycle: inputs -> output latches
                m.d.comb += self.lat.eq(1)
                m.d.sync += [
                    self.addr.eq(s_row),              # display row follows (blanked now)
                    disp_valid.eq(1),
                    disp.eq(self.unit << SCHED_SHIFT[s_idx]),  # just-latched slot's length
                    sc.eq(0),
                    shifting.eq(1),                   # next slot's shift starts post-guard
                ]
                # Advance SLOT-MAJOR over the schedule (all rows at slot k, then all rows
                # at k+1): plane-distribution + MSB subfield splitting — each row's light
                # arrives once per schedule slot instead of one burst per sweep. Same
                # total time and lit-time per pixel (golden sims are order-agnostic); the
                # win is perceptual: flicker/tracking shear drops with slot rate. Frame
                # pulse as the shifter wraps to (0,0) — the double buffer swaps while the
                # old frame's last slot displays.
                with m.If(s_row == S - 1):
                    m.d.sync += s_row.eq(0)
                    with m.If(s_idx == L - 1):
                        m.d.sync += [s_idx.eq(0), self.frame.eq(1)]
                    with m.Else():
                        m.d.sync += s_idx.eq(s_idx + 1)
                with m.Else():
                    m.d.sync += s_row.eq(s_row + 1)
                if self.guard:
                    m.d.sync += guard_cnt.eq(self.guard - 1)
                    m.next = "GUARD"
                else:
                    m.next = "RUN"
            if self.guard:
                with m.State("GUARD"):                # blanked settle, shifter held
                    with m.If(guard_cnt == 0):
                        m.next = "RUN"
                    with m.Else():
                        m.d.sync += guard_cnt.eq(guard_cnt - 1)
        return m
