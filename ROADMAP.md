# ROADMAP — rayglow-fpga

Living plan. Phases complete top-to-bottom; each has acceptance criteria. Superseded
versions go to `docs/design-history/`. Decisions log: README.md. Contract:
INTERFACE-CONTRACT.md.

## The numbers that shape the design

| Quantity | Value | Notes |
|---|---|---|
| Wall | 384×128 = 49,152 px (6×4 tiles of 64×32, P4, 1/16 scan) | rayglow `config.py` |
| Framebuffer | 1.13 Mbit @ 24 bpp; **2.25 Mbit double-buffered** | fits 3.74 Mbit EBR |
| FB in EBR **blocks** (empirical) | 9 DP16KD per 6144×24 true-dual-port bank × 16 banks = **144** + LUT ~12–24 ≈ **156–168 of 208 (75–81 %)** | measured 2026-07-20 (`synth_ecp5` on one bank); packing, not raw bits, is the real limit — and it fits |
| Future 512×128 | ~3.0 Mbit; block-packed est. ~192 | TIGHT (≈92 %) but likely fits; re-measure before committing |
| DPI pixel clock | ~3.5 MHz (416×140 total @ 60 Hz) | scope-visible (<10 MHz); 120 Hz = ~7 MHz |
| Chain strip | 384×32, shift = 384 clk = 15.4 µs @ 25 MHz | vs 768-wide/30.7 µs today |
| Refresh floor (shift-bound, conservative) | ≈ 1/(16 rows × B planes × t_shift): **B=8 → ~509 Hz, B=10 → ~407 Hz** | today: 143 Hz @ B=8; MSB planes exceed shift time so real numbers land higher |
| FPGA pins for 4 chains | 2 boards × (12 data + CLK) + 6 shared (A–D, LAT, OE) = **32** | = exactly J32+J33; 8 chains = 58 ≤ J32+J33+J39+J40 (~81) |

## Phase 0 — Toolchain + board alive

Concepts: LUT/FF/EBR/PLL, constraints, timing reports, the build pipeline.

- [x] OSS CAD Suite (2026-07-18 nightly) → `~/opt/oss-cad-suite`, PATH appended via
      `fish_add_path` (yosys 0.67, nextpnr-ecp5 0.10, ecppack 1.4, openFPGALoader 1.1.1)
- [x] udev rule for the FT2232H (0403:6010, `TAG+="uaccess"`) — `/etc/udev/rules.d/99-ecp5-evn.rules`
- [x] `uv run python -m gateware.top_blinky` builds: 25 FF / 32 comb of 83,640 (0 %),
      Fmax 589 MHz against the 12 MHz constraint. Artifacts worth reading in `build/`:
      `top.debug.v` (the Verilog Amaranth generated), `top.lpf`, `top.tim`
- [x] `openFPGALoader --detect` → LFE5UM5G-85 (0x81113043); SRAM-load blinks LED (D5) at
      1.4 Hz, DONE (D4) green — confirmed on hardware 2026-07-18
- [x] Button → LED + DIP switches → LEDs (`top_phase0.py`) — confirmed on hardware
- [x] PLL: 12 MHz × EHXPLLL → 60 MHz `fast` domain (`gateware/pll.py`, params from
      `ecppll -i 12 -o 60`: VCO 600 MHz, CLKFB_DIV 5, CLKOP_DIV 10), lock-gated reset,
      `DomainRenamer` demo + multi-clock sim (`tests/test_domains.py`). Timing: both
      domains PASS (fast_clk Fmax 491 MHz vs 60 required). The X2 200 MHz path (Y19/W20,
      external 100 Ω term per Fig A.6) deferred to Phase 4 (standalone/flash boot only)
- [x] Debug UART on PMOD J31 — via the **Pico debugprobe** UART bridge instead of the
      Waveshare (probe GP4→J31.2, GP5←J31.1, GND→J31.5; `/dev/ttyACM0` @ 115200).
      Beacon + byte-perfect echo verified live 2026-07-19. Bring-up tools kept in
      `gateware/`: `top_pmod_diag` (edge-latch pin finder), `top_wire_loop` (loopback)
- [x] Skim: ECP5 sysMEM/EBR + EHXPLLL sections of the family datasheet (Will, 2026-07-19)

**Accept: MET 2026-07-19** — blinky + button + UART echo, built and loaded from the CLI.

**Lesson learned:** SRAM configuration is volatile — any board power cycle blanks the
FPGA (floating pins, dead console). After a power cycle: `openFPGALoader -b ecp5_evn
build/top.bit`. Flash boot (Phase 4) exists for exactly this reason.

## Phase 1 — HUB75 core, one bench panel

The heart of the project. Bench mule = a **retired P6 panel** (`.reference/P6-...`), so the
live wall and its RP2350 driver are never touched. Concepts: FSMs, dual-port EBR, CDC-free
single-domain design, BCM timing, timing closure.

- [x] Scan-out engine (`gateware/scanout.py`, 2026-07-19): parametric N/M/scan/B/U,
      sequential v1 (shift→latch→display; overlap = recorded v2). Banked RGB888 EBR
      framebuffer + CIE1931 gamma LUT at readout + plane bit-select. Bench build:
      4 EBR, 91 FF, Fmax 172 MHz @ 12 MHz constraint
- [x] Pytest sims (`tests/test_scanout.py`): golden model reconstructs the frame from
      pin wiggles — per-pixel lit-time == U·lut[src] exact, 1- and 2-chain; structural
      asserts (LAT only blanked, no shift-while-display); real-geometry row smoke
- [x] EBR test pattern → bitstream (`top_hub75`: gradient + orientation corners, 64×32,
      B=10, U=4 → 139 Hz @ 76 % duty in the 12 MHz domain; math in gateware/SCANOUT.md)
- [x] **First light** on a retired P6 panel, direct 3.3 V, 6 MHz shift (2026-07-20):
      gradient + orientation corners correct, shift pixel-accurate, no flip/rotation.
      Root cause of the initial garble + tint was **flaky OE and GND solder joints**
      (confirmed: touching wires snapped it into place) — NOT short-pulse nonlinearity
      (that theory was a symptom of the bad OE/GND). `top_hub75_diag` (color bars + fade,
      live unit A/B on SW5-1) built and kept as a bring-up tool.
- [ ] **Redo the OE/GND solder joints** (the marginal ones), then buffer via the Adafruit
      RGB Matrix HAT (5 V, pre-soldered) or '245s on the EVN proto area. Then scope OE/CLK
      to measure refresh. Known residual to re-check after this: end-of-line skew on rows
      14–19 (17 worst) — likely OE/SI; gateware fallback if it survives = blanking-guard
      interval (SCANOUT.md v2). **Parked — physical-layer track, runs parallel to Phase 2.**
- [x] Gamma LUT (8-bit → B-bit CIE1931) in the scan-out path
- [ ] Measure refresh vs the table (PicoScope on OE/LAT — both well under 10 MHz)

**Accept:** static + animated ROM patterns on the P6 panel at B≥8, measured refresh
matching prediction ±10 %, all sims green.

## Phase 2 — DPI ingest (the translation layer proper)

Concepts: clock-domain crossing, async handshakes, video timing.

- [x] Pi 5: `vc4-kms-dpi-generic` overlay, rgb888, modeline per INTERFACE-CONTRACT.md.
      DPI connector up (`card0-DPI-1: connected`), PLL locked at 3.5 MHz, polarities
      `+V+DE+CK` match the gateware.
- [x] DPI timing decoder (`gateware/dpi.py`, `DpiIn`): DE/VSYNC → (x,y)/valid/frame_start
      in the PCLK domain, modeline-agnostic, both sync polarities. Sim-verified over 2
      frames (`tests/test_dpi.py`) — caught + fixed an active-low first-frame edge bug.
- [x] Framebuffer write path + double-buffer + **CDC** (`gateware/double_buffer.py`):
      2 buffers, geometry fold on write (pix domain), front-select on read (sync domain);
      one toggle bit crosses via FFSynchronizer, swap at scan frame boundary (tear-free);
      strict buffer alternation keeps writer/reader disjoint. Hub75Core `external_fb`
      hook. Full translator `gateware/translator.py` (`DpiToHub75`).
- [x] Capstone sim (`tests/test_translator.py`): DPI video in `pix` → byte-exact panel
      out in `sync`, across two clocks; caught a frame-split + a measurement-window bug.
      13/13 sims green. JP8 pin map + PCLK-clock-routing risk recorded in the contract.
- [x] Board top `top_translator.py`: DPI in on JP8, HUB75 out on J32; builds clean (8 EBR,
      2 clock buffers). PCLK-on-L18 auto-promotes to a global clock (risk retired). Bench
      crop: Pi at 384×128, translator at 64×32/1-chain, DoubleBuffer capture-bounds gate
      shows the top-left 64×32 of the Pi's frame on the one bench panel.
- [x] **Pi config fix (2026-07-20):** `dtoverlay=uart3` (GPIO8/9) + `dtparam=spi=on`
      (GPIO7-11) collided with DPI's GPIO0-27 → DPI driver bailed ("reverse things back",
      no connector). Commented both out + reboot → GPIO0-27 now in DPI alt-function.
- [x] **Milestone MET 2026-07-20 — the panel shows the Pi's Linux console** (top-left
      64×32 crop), no rayglow code involved. Pure white text, serifs, zero artifacts,
      no tearing. The wall is a monitor.
- [x] RGB channel order CONFIRMED correct (fb0 XRGB8888 → panel R/G/B in order, 2026-07-20).
      No swizzle. Pinned in INTERFACE-CONTRACT §4a. rgb888, not bgr888.
- [x] Boundary-row dimming FIXED with a blanking-guard interval (`guard=8`, ~667 ns settle
      between LATCH and OE-enable). Root cause was the 1-cycle latch→driver gap; the rest
      of the loop already blanks heavily. Confirmed "crystal clear, no flicker" on hardware
      2026-07-20. Sim-proven BCM lit-time unchanged. Refresh cost negligible (139→137 Hz).
- [x] Refresh (computed, deterministic FSM): bench 64×32 B=10 U=4 guard=8 = 137 Hz @ 12 MHz.
      The **overlap** upgrade (shift-under-display) is the ~2× lever if ever needed
      (SCANOUT.md) — deferred; 137 Hz is already flicker-free.
- [ ] **Open: driver clamps `vactive` to 480** (asked 128, got 384×480 @ 16.8 Hz). Fine
      for the crop; the wall needs true 384×128. Investigate the RP1-DPI/KMS minimum-height
      path (panel-simple bridge / custom mode) before Phase 3.
- [x] **rayglow `--output kms` IMPLEMENTED (2026-07-21, branch `feat/output-kms`).**
      `kms_out.py` mmaps /dev/fb0 + blits the resolved RGB frame; `run_kms` mirrors the
      live loop minus fold/pack/transport; forces resolve gamma=1.0 (FPGA owns gamma).
      On hardware: renderer → fb0 → FPGA → panel at 64×32, 119 fps render, blit ~0 ms.
      DPI clock bumped 3.5→12.5 MHz for 60 Hz (smooth) — driver still clamps to 384×480.
- [x] **V3D restored (2026-07-21).** Root cause: the `dtoverlay=vc4-kms-v3d` +
      `max_framebuffers=2` lines were accidentally overwritten when the DPI overlay was
      added — so the V3D *3D* driver never loaded (DPI display still worked via the
      separate RP1-DPI driver, hence the confusion). Re-added them before the DPI overlay;
      render dropped 7.5 ms (llvmpipe) → **0.2 ms (V3D 7.1.7)**. **Gotcha for the clone's
      config.txt: keep `vc4-kms-v3d` — the dpi-generic overlay documents it as required.**
      Note: DPI moved to card1, HDMI card2 (disconnected → no fb renumber, fb0 still DPI);
      `--fbdev` added to `run_kms` as insurance if HDMI is ever plugged.
- [x] **Full-width demo on the 6× single chain (384×32) — DONE 2026-07-21.** FPGA
      translator width=384/chains=1, scan-out in a 40 MHz PLL `scan` domain (20 MHz shift)
      via DomainRenamer sync→scan; Pi renders 384×32 over kms. `will-voidrainbow` spans all
      six panels as one coherent frame, ~102 Hz. SI note: 30 MHz shift bled color toward
      white per panel (data lines not settling over the 6-deep chain; shapes/clock stayed
      clean) — dropped to 20 MHz shift and it cleared. `PLL12to30` (15 MHz) staged if a
      longer/faster chain ever needs it. **This validates the parametric engine + PLL for
      the Phase 3 wall.**
- [ ] Cross-check: rayglow dry-run GIF vs FPGA-sim golden model on the same frame

**Accept:** a rayglow shader at 60 fps on bench panel(s) over DPI, no tearing, gamma per
contract; RP2350 path still fully operational.

### Notes for the Phase 3 wall build
- **Gamma LUT is now one ROM per read port** (`scanout.py`), not one shared many-port
  memory — the shared version OOM-killed yosys MEMORY_LIBMAP at 24 ports (4 chains). Costs
  24 EBR at 4 chains (in the 80% total). If EBR ever gets tight (e.g. 512×128), force these
  to LUTRAM (`ram_style="distributed"`) to reclaim them, or move gamma to the DPI-write
  side (3 ports total, wider framebuffer).
- **Heavy builds need the sandbox off:** the 4-chain synth peaks past the Bash sandbox's
  memory cgroup — build with `dangerouslyDisableSandbox` (the machine has 251 GB; it's a
  trusted local tool). The failure looks like SIGKILL/137.

## Phase 3 — Scale to the wall + wing boards

Concepts: I/O banks, drive strength/slew, SI at 25–30 MHz, PCB design (KiCad + kicad-mcp,
SKiDL flow proven on the rayglow HAT).

- **Level shifting: reuse the 2 RP2350 HATs first (decided 2026-07-21).** No custom PCB
      needed to light the wall — each HAT's 4× '245 buffer 2 chains, always-enabled, NO
      chip-select (the "CS" was the Pi→RP2350 link's, which the FPGA removes). ECP5→HAT J1
      wiring map + power/ground in **hardware/RAYGLOW-HAT-ADAPTER.md**. `top_wall.py`
      (NUM_CHAINS 2→4). Custom wing boards (WING-BOARD.md) come AFTER the wall is proven —
      their only edge over the HAT is data-line series termination (higher shift clock).
- [ ] **Stage 1: 1 HAT, 2 chains (384×64).** `top_wall.py` NUM_CHAINS=2 built (scan Fmax
      79 MHz, 72 EBR). Re-cable top 2 rows as two 6-panel chains; wire per the adapter doc;
      Pi renders 384×64. Validates the RayGLow-HAT interfacing + multi-chain scan-out.
- [x] **Stage 2 bitstream BUILT + fits (2026-07-22).** `top_wall.py` NUM_CHAINS=4:
      168/208 EBR (80% = 144 framebuffer + 24 gamma ROMs), 1 PLL, both clocks pass timing
      (scan ~68-83 MHz vs 40). The full 384×128 wall is proven buildable on the 85F.
      **Fix applied:** the gamma LUT was one memory with 2N×3 read ports — yosys
      MEMORY_LIBMAP OOM-killed at 24 ports (fine at 12). Split into per-read-port ROMs
      (`scanout.py`) → maps trivially, sims unchanged. (Not a sandbox cap — real yosys
      blowup; retried unsandboxed first to rule that out.)
- [x] **Stage 2 bring-up COMPLETE (~2026-07-29): ALL FOUR CHAINS — THE FULL 384×128 WALL —
      RENDERING SHADERS OVER DPI.** Took Will ~a week of physical debugging: one chain dead,
      root cause a fried '245 on a HAT (found after probing every pin, two board rebuilds,
      three rewires; all four '245s on that HAT replaced with fresh stock). will-apollo.glsl
      at scale 1, ~120 fps render / 60 Hz DPI. Residuals at first light: tearing in fast
      motion (fixed — see Phase 4 vsync) + faint flicker (re-check post-vsync; overlap is
      the fix if it persists).
- [ ] **Wing boards: PARKED (Will, 2026-07-29).** The RayGLow HATs serve the role; revisit
      only for footprint/wiring consolidation, not function. (WING-BOARD.md kept as the
      design record.)
- [ ] Power: '245 VCC ratiometric from each chain's panel-PSU domain; star ground per
      rayglow POWER-AND-GROUNDING.md; wall split on the horizontal midline (PSU per 2 rows)
- [ ] SI validation at 25 MHz, series-R experiments (footprints on the wing board). Honest
      note: the 10 MHz PicoScope can't see these edges — mitigate with conservative
      clocking + the sim; the manifest's "used ≥100 MHz scope" gap applies here
- [ ] Full wall soak: worst-case patterns (all-white capped, single-pixel, high-frequency
      dither), thermal check on the '245s

**Accept:** full 384×128 wall from the Pi desktop at 60 fps input, ≥400 Hz refresh @ B≥8,
stable for hours, no visible SI artifacts at viewing distance.

## Phase 4 — Polish + headroom

- [x] **Tearing fixed (2026-07-29): vsync-paced blits.** `kms_out.py` gains `_VBlank` —
      `DRM_IOCTL_WAIT_VBLANK` on the DRM card backing the fbdev (matched via sysfs parent
      device, robust to card renumbering — it's moved card1→card0 across reboots). Every
      blit lands in vertical blanking; loop locks to 60 Hz. Root cause was the fbdev blit
      racing the DPI scanout at 120 fps — Pi-side, not the FPGA (its double-buffer swap
      was always tear-free).
- [x] **FPGA-side tearing fixed (2026-07-29): the 16-row-banded frame mixing** under fast
      motion (Will's rayballs photo) was the double-buffer CDC — toggle fired at next
      frame_start (reader displayed the buffer being overwritten for up to a scan frame),
      plus an off-by-one buffer phase once completion-fired. Fixed in `double_buffer.py`;
      regression sim feeds DISTINCT frames at the real timing ratio (the old capstone's
      identical frames masked this). Constraint recorded: scan_frame < DPI_period −
      capture_time (9.8 < 12.4 ms today; a true vactive=128 mode would break it).
- [x] **Overlap engine SHIPPED (2026-07-30)** — the scan-skew/judder mitigation: 102.1 Hz
      / 66.9 % duty → **122.6 Hz / 80.3 % duty** (faster AND brighter), and ≈2.04× the
      60 Hz source so nearly every frame displays exactly twice (even cadence). In SRAM +
      flash. Sequential engine kept behind `overlap=False`. 20/20 sims incl. overlap
      golden-frame + overlap-is-faster. Details: SCANOUT.md.
- [x] **Bitstream WRITTEN to SPI flash (2026-07-30). Root cause of the JEDEC=0xFF
      failures: the CFGMDN mode, not JP18** (which was correctly seated all along) —
      with SW1 in the old mode the config logic never routed the MSPI port to the flash;
      the moment Will set **SW1 to MSPI (pos2 ON, pos3 OFF, pos4 ON)**, JEDEC read
      0xC22018 (Macronix MX25L128) and the 4-chain wall bitstream wrote clean, 100 % +
      refresh. Lesson: flash access via JTAG passthrough requires the MSPI CFGMDN mode.
- [ ] **Flash-boot POWER-CYCLE TEST (Will, whenever ready):** power cycle the EVN →
      expect green DONE within ~1 s and the wall alive with NO host command. Keep the
      mini-USB plugged into a powered host (12 MHz FTDI clock = PLL ref). If no boot,
      the SW1 ON=0 polarity assumption flips. ⚠ True no-USB standalone still needs the
      X2 200 MHz migration (deferred).
- [x] **Second tearing layer root-caused + fixed (2026-07-29): /dev/fb0 is fbdev
      EMULATION** — a cached shadow whose kernel worker copies 4 KB (~2.7-row) chunks to
      scanout unsynced to vblank → the fine-band shear that survived both earlier fixes.
      rayglow now drives DRM directly (`drm_out.py`: dumb buffers + hardware PAGE_FLIP,
      event-paced, `--kms-backend auto`). Writes now hit real WC scanout memory; 0 missed
      flips. Bonus: fbcon's cursor no longer writes over the wall.
- [x] **Third "artifact" RECLASSIFIED (2026-07-30): presentation physics, not corruption.**
      Two independent proofs the data path is clean: (a) armed line-integrity checkers
      (D9 blink / D10 short / D11 long, arm after first VSYNC) stay dark indefinitely —
      every captured line is exactly 384 px; (b) Will's long-exposure photo integrates
      many refreshes and is flawless — the frame CONTENT is correct. The visible streaks
      under fast motion = multiplexed-scan physics: a camera exposure (or tracking eye)
      straddles two ~102 Hz scan frames showing two 60 Hz source frames, interleaved at
      the 16-row scan structure; worsened by the uneven 102/60 cadence (1-vs-2 scan
      frames per source frame). Same reason filming commercial LED walls needs shutter
      sync. Freeze test: pause content mid-motion → streaks vanish while scan continues.
      Falling-edge capture + PCLK/DE hysteresis retained (correct + margin for 120 Hz).
      **Mitigations = the roadmap: overlap upgrade (shrinks skew window, ~147 Hz @ HIGHER
      duty), tune `unit` for ~2× source cadence, and eventually 120 Hz DPI source.**
- [x] **EVN mini-USB → Pi USB (2026-07-30): the wall is self-contained.** openfpgaloader
      (apt, v0.13.1) + udev rule on the Pi; `--detect` clean; full reflash-over-SSH loop
      validated: build on desktop → `scp build/top.bit rpi5:/tmp/` →
      `ssh rpi5 "openFPGALoader -b ecp5_evn -f --unprotect-flash /tmp/top.bit"` — the
      trailing Refresh boots the new flash image automatically. Desktop JTAG retired.
- [x] **B=11 BCM + hardware brightness knob (2026-07-30).** 11 planes at default unit=8 =
      identical total brightness to B=10/unit=16 with 2× finer dark-end resolution;
      ~117.9 Hz / 77.2 % duty / ~1.97× source cadence (B=12 rejected: −4 % more refresh
      AND only 4 brightness steps below default). Runtime `unit` exposed through
      DpiToHub75 and wired to **SW5 positions 1–4** (4-bit, FFSync'd into scan domain):
      all OFF = default 8; else the value 1–15 directly (≈12 %–190 %; dimmer = faster
      refresh, brighter = slower, 71.8 Hz at 15). In SRAM + flash.
- [x] **SEAMS ELIMINATED — production config settled (2026-08-01):** 48 MHz scan
      (24 MHz shift) + overlap + MSB subfield splitting ({9:2, 10:4}) + B=11 + knob =
      **140.4 Hz refresh, ~560 Hz effective motion sampling, full brightness, clean end
      to end, "no streaking, looks great."** In flash; self-boots.
      **Shift-clock SI cliff MEASURED:** 24 MHz clean / 30 MHz cascades skew from ~panel
      3 on all chains; FAST vs SLOW slew = zero difference (head-end timing budget, not
      edge rate — Will's matched-jumper work holds the margin at 24). The A/B ran as
      SRAM loads (`/tmp/top_fast60.bit` vs `/tmp/top_slow50.bit` on the Pi). Going
      faster = interconnect work (terminated backplane/mezzanine HAT, the planned
      separate session), not settings. Note: ecppll "50 MHz" from a 12 MHz ref actually
      locks at 48 (integer feedback) — preset named PLL12to48 honestly.
- [x] **120 Hz DPI mode — CONFIRMED ON THE WALL 2026-08-02** ("end to end full
      rendering, looks fantastic" — Will; ~120 fps was the original target, pulled back
      only for SI, and the SI work since made it reachable). The blocker was the
      handoff constraint (scan_frame < DPI_period −
      capture_time: 7.1 ms vs ~6.1 ms at 122 Hz → the 16-row mixing would return). Fixed
      structurally in `double_buffer.py`: the reader's `front` crosses BACK to the writer
      (1 bit, FFSync — mirror of the forward toggle) and the writer captures only when
      the previous publication is consumed, else it SKIPS that source frame. Tear-free at
      any timing ratio; a too-slow scan now drops source frames instead — pulse on new
      LED **D8** (dark = consuming everything). Constraint note in double_buffer.py
      retired; sim `test_slow_reader_drops_frames_never_tears` locks the regime in.
      Pi-side is config.txt-only (same bitstream): `clock-frequency=25000000` → 122.14 Hz.
      Cadence table + knob interaction in INTERFACE-CONTRACT §2a (v0.2, ratified) and
      the full per-setting table in hardware/SWITCHES-AND-LEDS.md — headline: **SW5=6
      scans at 171.2 Hz and consumes all 122 fps with zero drops at 91.5 % brightness**;
      SW5=8 = full brightness, ~15 % irregular drops (~104 unique fps). Zero-drop
      alternates: ~100 Hz at 20.5 MHz, or true 120 Hz via padded vtotal (PCLK 45 MHz —
      SI experiment, matched-jumper margin unknown; FPGA pix timing already clears it,
      Fmax 85.6 MHz). ⚠ Until the new bitstream is in SPI flash, keep in mind a power
      cycle boots the OLD gateware into the 25 MHz mode → 16-row mixing returns until
      reflash (`openFPGALoader -b ecp5_evn -f --unprotect-flash`).
- [ ] Optional: temporal dithering; per-chain diagnostics counters readable over the
      debug UART/I²C

## Phase 5 (future, promising) — audio DSP on-chip

Will's idea (2026-07-18): mic → FPGA FFT, coexisting with the HUB75 role. Viable on this
one chip — the 85F has 156 sysDSP multipliers and the translator barely dents the LUT
budget; 48 kHz audio is glacial next to a 100 MHz butterfly engine. Architecture insight:
the *consumer* of audio features is the Pi renderer, so the FPGA would act as an alternate
**feed-v3 sender** — I2S MEMS mic on 3 GPIOs → window/FFT/band-fold in fabric → feature
packets up the already-planned EVN-USB↔Pi cable (FT2232H channel B UART). Same packet
contract, new producer; rayglow already treats senders as swappable. Sequenced after
Phase 2-3 (needs the same EBR/CDC/fixed-point skills those phases teach). Bonus mode:
standalone spectrum bars with no Pi at all — great bring-up diagnostic and demoscene flex.

## Parked / rejected (with reasons, so they stay decided)
- **Ethernet ingest** (KSZ9031 stash, `.reference/ethernet-adapter/`): Pi stays regardless;
  RGMII bring-up blind on a 10 MHz scope; zero benefit over JP8. Revisit only if "wall
  without a Pi" becomes real — then compare against a Colorlight 5A-75B first (its 25F has
  1.0 Mbit EBR, would need its SDRAM).
- **HDMI/TMDS RX**: same endgame as DPI, 10× the first-project risk, no connector on the
  EVN. Possible gateware v2.
- **Multi-RP2350**: solved problem, no learning, SRAM-capped, more protocol plumbing.
