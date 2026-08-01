# rayglow-fpga

> Read first — human orientation. Agent guidance is in CLAUDE.md.

ECP5 FPGA translation layer for the rayglow LED wall: Raspberry Pi 5 **DPI video in**,
parallel **HUB75 BCM scan-out** to the 24-panel (384×128) wall v2. The Pi treats the wall
as a monitor; the FPGA turns a video signal into panel drive. Sister project to
`~/Projects/rayglow` (renderer + RP2350 path, which keeps working untouched); the boundary
between the two repos is INTERFACE-CONTRACT.md, which lives here.

```
will-desktop ──UDP :5005 (audio features, unchanged)──▶
Pi 5: rayglow renderer (GLSL/EGL, unchanged) ──▶ KMS DPI out, GPIO0–27
        RGB888 + PCLK/DE/syncs, custom modeline 12.5 MHz @ 60 Hz
                     │ 40-pin ribbon to JP8
ECP5-EVN (LFE5UM5G-85F): DPI capture ─▶ double-buffered EBR framebuffer
        swap on VSYNC ─▶ gamma LUT 8→12-bit ─▶ BCM scan-out engine
                     │ 2× RayGLow RP2350 HATs, 74AHCT245 (3.3→5 V)
4 chains × 6 panels (384×32 strips) — HUB75 1/16 scan, no serpentine
```

**Why:** wall v2's 2×12-panel serpentine chains hit signal-integrity limits (only 4-deep
was ever validated). Shorter chains need more parallel outputs than an RP2350 has; the
FPGA provides them, deletes the readback→pack→transport pipeline entirely (rendering *is*
sending), and lifts the RP2350's SRAM ceiling — 384×128×24 bpp double-buffers in 2.25 Mbit
of the 85F's 3.74 Mbit EBR, no external RAM. And it's the excuse to finally learn FPGAs.

## Status
- **2026-08-01: COMPLETE — the wall is in production.** 384×128 across 24 panels, four
  chains, 140.4 Hz refresh (~560 Hz effective motion sampling via MSB subfield
  splitting), 11-bit BCM, hardware brightness knob, boots itself from SPI flash,
  reflashes over SSH. Phases 0–4 in 25 days; the full build story — including every bug,
  dead end, and the signal-integrity hunt — is in
  `docs/design-history/2026-08-01-claude-session-fpga-wall-build.md`.
- 2026-07-18: project created.

## Layout
- `gateware/` — Amaranth HDL (uv project, root pyproject.toml)
- `tests/` — simulation testbenches (`uv run pytest` — no system toolchain needed)
- `hardware/` — topic docs (current truth): HAT adapter wiring, wing-board design record
- `INTERFACE-CONTRACT.md` — the rayglow ↔ rayglow-fpga boundary (versioned)
- `ROADMAP.md` — phased plan with acceptance criteria
- `docs/design-history/` — superseded docs; current docs win
- `.reference/` — datasheets per component (git-ignored): `ecp5-evn/`, `ecp5/`, `rpi5/`,
  `P6-3528-64X32-16S-HL11/` (bench panel), `ethernet-adapter/` (parked parts stash)
- `will-notes.md` — Will's inbox to the agent
- `tools/` — verification scripts

## Quick start
```fish
uv sync
uv run pytest          # simulate — works today, zero system deps
```
Bitstream builds additionally need yosys/nextpnr-ecp5/ecppack/openFPGALoader on PATH
(OSS CAD Suite — ROADMAP Phase 0), then:
```fish
uv run python -m gateware.top_blinky
openFPGALoader -b ecp5_evn build/top.bit
```

## Design decisions
| Date | Decision | Why |
|---|---|---|
| 2026-07-18 | HDL = **Amaranth** | Python-native (uv, pytest sims, can cross-check against rayglow's numpy golden frames); transparent — emits RTLIL through yosys, generated Verilog inspectable; removes Verilog footguns while learning the same concepts |
| 2026-07-18 | Ingest = **Pi 5 DPI** via JP8, not HDMI/TMDS or the 4-lane PIO protocol | JP8 carries all 28 Pi GPIOs = the full DPI interface; deletes Pi-side readback/pack/transport; ~3.5 MHz PCLK is bench-scope-visible; TMDS RX is a poor first FPGA project. PIO protocol remains the fallback |
| 2026-07-18 | Topology = **4 chains × 6 panels**, chain count parametric in gateware | 384-px strips ≈ 500 Hz shift-bound refresh floor vs 143 Hz today; 6-deep ≈ the validated-SI regime; 8×3 is the escape hatch |
| 2026-07-18 | Level shifting on **identical, modular 2-chain wing boards** (build 2 now, 2 more = 8 chains) | PCB lead time; one design, reorder to expand. Rules + pin budget: hardware/WING-BOARD.md |
| 2026-07-18 | **Ethernet adapter parked** (KSZ9031 stash in `.reference/ethernet-adapter/`) | The Pi stays regardless (renderer + audio feed live there); hand-soldered RGMII debugged blind on a 10 MHz scope is a chore with zero benefit over the header that's already there |
| 2026-07-18 | Gamma owned by the **FPGA** (8-bit perceptual in → 12-bit BCM LUT) | Monitor semantics for the Pi; recovers the shadow resolution the 8-bit-baked-gamma path loses today |

## License

MIT — see [LICENSE](LICENSE). Tooling and prior art credits: [ATTRIBUTION.md](ATTRIBUTION.md).
Vendor datasheets are not redistributed (`.reference/` is git-ignored); sources are cited
in ATTRIBUTION.md.
