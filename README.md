# rayglow-fpga

#### ECP5 FPGA translation layer for the rayglow LED wall

This project was built separate from, but in addition to the rayglow project. This was an 
exercise to learn about interacting with, programming, and implementing FPGAs. I have always
wanted to learn more about these cool gizmos and finally had the perfect excuse to do so.
This was a project to learn, but may include worthwhile code or information that can
be used by others if they are interested in the similar setups.

---

Raspberry Pi 5 **DPI video in**,
parallel **HUB75 BCM scan-out** to the 24-panel (384×128) wall v2. The Pi treats the wall
as a monitor and the FPGA turns a video signal into panel drive. Sister project to
`~/Projects/rayglow` (renderer + RP2350 path, which keeps working untouched); the boundary
between the two repos is INTERFACE-CONTRACT.md.

```
pc-desktop ──UDP :5005 (audio features, unchanged)──▶
Pi 5: rayglow renderer (GLSL/EGL, unchanged) ──▶ KMS DPI out, GPIO0–27
        RGB888 + PCLK/DE/syncs, custom modeline 12.5 MHz @ 60 Hz
                     │ 40-pin ribbon to JP8
ECP5-EVN (LFE5UM5G-85F): DPI capture ─▶ double-buffered EBR framebuffer
        swap on VSYNC ─▶ gamma LUT 8→12-bit ─▶ BCM scan-out engine
                     │ 2× RayGLow RP2350 HATs, 74AHCT245 (3.3→5 V)
4 chains × 6 panels (384×32 strips) — HUB75 1/16 scan, no serpentine
```

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

## License

MIT — see [LICENSE](LICENSE). Tooling and prior art credits: [ATTRIBUTION.md](ATTRIBUTION.md).
Vendor datasheets are not redistributed (`.reference/` is git-ignored); sources are cited
in ATTRIBUTION.md.
