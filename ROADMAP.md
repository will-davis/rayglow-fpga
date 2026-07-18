# ROADMAP — rayglow-fpga

Living plan. Phases complete top-to-bottom; each has acceptance criteria. Superseded
versions go to `docs/design-history/`. Decisions log: README.md. Contract:
INTERFACE-CONTRACT.md.

## The numbers that shape the design

| Quantity | Value | Notes |
|---|---|---|
| Wall | 384×128 = 49,152 px (6×4 tiles of 64×32, P4, 1/16 scan) | rayglow `config.py` |
| Framebuffer | 1.13 Mbit @ 24 bpp; **2.25 Mbit double-buffered** | fits 3.74 Mbit EBR, ~60 % |
| Future 512×128 | 3.0 Mbit double-buffered | still fits — no external RAM ever needed |
| DPI pixel clock | ~3.5 MHz (416×140 total @ 60 Hz) | scope-visible (<10 MHz); 120 Hz = ~7 MHz |
| Chain strip | 384×32, shift = 384 clk = 15.4 µs @ 25 MHz | vs 768-wide/30.7 µs today |
| Refresh floor (shift-bound, conservative) | ≈ 1/(16 rows × B planes × t_shift): **B=8 → ~509 Hz, B=10 → ~407 Hz** | today: 143 Hz @ B=8; MSB planes exceed shift time so real numbers land higher |
| FPGA pins for 4 chains | 2 boards × (12 data + CLK) + 6 shared (A–D, LAT, OE) = **32** | = exactly J32+J33; 8 chains = 58 ≤ J32+J33+J39+J40 (~81) |

## Phase 0 — Toolchain + board alive

Concepts: LUT/FF/EBR/PLL, constraints, timing reports, the build pipeline.

- [ ] OSS CAD Suite (yosys, nextpnr-ecp5, ecppack, openFPGALoader, waveform viewers) into
      `~/opt/oss-cad-suite`, PATH via fish `fish_add_path`; udev rule for the FT2232H
- [ ] `openFPGALoader --detect` sees the board; `uv run python -m gateware.top_blinky`
      builds; SRAM-load blinks LED0 (12 MHz clock: USB plugged + JP2 installed, JP1 off)
- [ ] Button → LED; DIP switches read; then PLL from the X2 200 MHz oscillator (JP9 open,
      verify VCCIO/IO_TYPE for Y19/W20) — the standalone clock all later phases use
- [ ] Debug UART out PMOD J31 → Waveshare USB-UART bridge (FTDI UART path is DNI — R34/R35)
- [ ] Skim: ECP5 sysMEM/EBR + EHXPLLL sections of the family datasheet (`.reference/ecp5/`)

**Accept:** blinky + button + UART hello, built and loaded from the desktop CLI only.

## Phase 1 — HUB75 core, one bench panel

The heart of the project. Bench mule = a **retired P6 panel** (`.reference/P6-...`), so the
live wall and its RP2350 driver are never touched. Concepts: FSMs, dual-port EBR, CDC-free
single-domain design, BCM timing, timing closure.

- [ ] Scan-out engine in Amaranth, **parametric from day one**: chains N, panels/chain M,
      scan 1/16, BCM depth B. Structure: row FSM (addr A–D, LAT) + shifter (RGB×N, CLK) +
      BCM OE scheduler (binary-weighted intervals, hzeller-style)
- [ ] Pytest sims: waveform-level assertions (LAT never during shift; OE intervals binary;
      addr sequence) + a Python golden model that reconstructs the displayed image from
      simulated pin wiggles and compares to the source pattern, `tools/verify.py`-style
- [ ] EBR test-pattern ROM (gradients, checkerboard, single-pixel walk) → panel
- [ ] First light **direct 3.3 V** (v1 precedent: clean over 4 panels), short ribbon,
      ~10 MHz; then '245s on the EVN prototype area → 25 MHz
- [ ] Gamma LUT (8-bit in → 12-bit BCM weights, CIE-ish) in EBR
- [ ] Measure refresh vs the table above; PicoScope on OE/LAT (slow enough to see)

**Accept:** static + animated ROM patterns on the P6 panel at B≥8, measured refresh
matching prediction ±10 %, all sims green.

## Phase 2 — DPI ingest (the translation layer proper)

Concepts: clock-domain crossing, async handshakes, video timing.

- [ ] Pi 5: `vc4-kms-dpi-generic` overlay, rgb888, modeline per INTERFACE-CONTRACT.md;
      verify PCLK/DE/sync on the scope before the FPGA ever sees them
- [ ] DPI capture in the PCLK domain → double-buffered EBR framebuffer, swap on VSYNC;
      scan-out reads the inactive buffer (tear-free, ≤1 frame latency)
- [ ] Milestone: **the panel shows the Pi's Linux console** — no rayglow code involved
- [ ] Verify Pi 5 DPI color order (known quirk, raspberrypi/linux#6505); pin the swizzle
      in the contract
- [ ] rayglow repo: additive `--output kms` (render → DRM dumb-buffer blit on the DPI
      connector first; direct GPU scan-out later). PIO path untouched
- [ ] Cross-check: rayglow dry-run GIF vs FPGA-sim golden model on the same frame

**Accept:** a rayglow shader at 60 fps on bench panel(s) over DPI, no tearing, gamma per
contract; RP2350 path still fully operational.

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

## Parked / rejected (with reasons, so they stay decided)
- **Ethernet ingest** (KSZ9031 stash, `.reference/ethernet-adapter/`): Pi stays regardless;
  RGMII bring-up blind on a 10 MHz scope; zero benefit over JP8. Revisit only if "wall
  without a Pi" becomes real — then compare against a Colorlight 5A-75B first (its 25F has
  1.0 Mbit EBR, would need its SDRAM).
- **HDMI/TMDS RX**: same endgame as DPI, 10× the first-project risk, no connector on the
  EVN. Possible gateware v2.
- **Multi-RP2350**: solved problem, no learning, SRAM-capped, more protocol plumbing.
