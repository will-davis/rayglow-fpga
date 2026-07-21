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

- [ ] Pi 5: `vc4-kms-dpi-generic` overlay, rgb888, modeline per INTERFACE-CONTRACT.md;
      verify PCLK/DE/sync on the scope before the FPGA ever sees them
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
- [ ] **Pi config fix (found 2026-07-20):** `dtoverlay=uart3` (GPIO8/9) + `dtparam=spi=on`
      (GPIO7-11) collide with DPI's GPIO0-27 → DPI driver bailed ("Error applying setting,
      reverse things back", no DRM connector). Comment both out + reboot. Then verify DPI
      connector appears + `pinctrl` shows GPIO0-27 in alt (DPI) function.
- [ ] Load `top.bit`, confirm the panel shows the Pi console crop; pin the RGB swizzle.
- [ ] Milestone: **the panel shows the Pi's Linux console** — no rayglow code involved
- [ ] Verify Pi 5 DPI color order (known quirk, raspberrypi/linux#6505); pin the swizzle
      in the contract
- [ ] rayglow repo: additive `--output kms` (render → DRM dumb-buffer blit on the DPI
      connector first; direct GPU scan-out later). PIO path untouched
- [ ] Cross-check: rayglow dry-run GIF vs FPGA-sim golden model on the same frame

**Accept:** a rayglow shader at 60 fps on bench panel(s) over DPI, no tearing, gamma per
contract; RP2350 path still fully operational.

### Notes for the Phase 3 wall build
- **LUT replication scales with chains:** the gamma ROM has 3 read ports per chain-half
  (24 at 4 chains). Cheap now (256×B), but if EBR gets tight, force it to LUTRAM/distributed
  (`ram_style`) or time-multiplex — frees ~12–24 EBR.
- **Full-wall `synth_ecp5` is slow** on the flattened design (stalls minutes in
  MEMORY_LIBMAP with 16 wide dual-clock memories). Fine for a one-off bitstream build; if
  it bites, synthesize per-chain or keep the framebuffer as a hierarchical black box.

## Phase 3 — Scale to the wall + wing boards

Concepts: I/O banks, drive strength/slew, SI at 25–30 MHz, PCB design (KiCad + kicad-mcp,
SKiDL flow proven on the rayglow HAT).

- [ ] Re-cable wall 2×12 serpentine → **4 chains × 6** (chain k = tile row k, no fold)
- [ ] Wing board rev A per hardware/WING-BOARD.md (2 identical boards = 4 chains; two more
      of the same board = 8 chains later). Validate one full 6-panel chain on proto-area
      shifters *before* ordering PCBs
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

- [ ] B=10–12 BCM + brightness control (global OE scale)
- [ ] Bitstream in SPI flash (MSPI boot via CFGMDN switches) — wall works at power-on
- [ ] EVN mini-USB → Pi USB: reflash over SSH (`openFPGALoader` on the Pi)
- [ ] Optional: 120 Hz DPI mode; temporal dithering; per-chain diagnostics counters
      readable over the debug UART/I²C

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
