# Attribution

This project is original work (MIT licensed — see LICENSE), but it stands on open
tools, open silicon documentation, and prior art whose ideas shaped the design. No
third-party code is vendored in this repository.

## Dependencies

- **[Amaranth HDL](https://github.com/amaranth-lang/amaranth)** (BSD-2-Clause) — the
  hardware description language everything in `gateware/` is written in, including its
  pure-Python simulator that made the sim-first workflow possible.

## Toolchain (build-time, not distributed)

- **[Yosys](https://github.com/YosysHQ/yosys)** (ISC) — synthesis
- **[nextpnr](https://github.com/YosysHQ/nextpnr)** (ISC) — place and route
- **[Project Trellis](https://github.com/YosysHQ/prjtrellis)** (ISC) — the ECP5
  bitstream documentation that makes the fully open flow possible, plus `ecppack`/`ecppll`
- **[openFPGALoader](https://github.com/trabucayre/openFPGALoader)** (Apache-2.0) —
  JTAG/SPI-flash programming
- Distributed together as the **[OSS CAD Suite](https://github.com/YosysHQ/oss-cad-suite-build)**

## Prior art & concepts (no code copied)

- **[hzeller/rpi-rgb-led-matrix](https://github.com/hzeller/rpi-rgb-led-matrix)** — the
  canonical HUB75 reference: binary-coded modulation, CIE1931 luminance correction, and
  the OE-time brightness trade all follow its playbook.
- **[kjagiello/hub75-pio-rs](https://github.com/kjagiello/hub75-pio)** — the RP2350
  scan-out engine used by this project's sister repo (rayglow), whose proven timing
  numbers served as the golden reference during bring-up.
- **[chubby75](https://github.com/q3k/chubby75)** — the Colorlight receiver-card
  reverse-engineering project; informative background on commercial LED-wall
  architecture (Ethernet ingest, subfield techniques).
- **Lattice Semiconductor** documentation: ECP5/ECP5-5G family datasheet
  (FPGA-DS-02012), ECP5 Evaluation Board guide (FPGA-EB-02017), sysCONFIG usage guide
  (FPGA-TN-02039). Datasheets are not redistributed here (`.reference/` is git-ignored).
- **Raspberry Pi** documentation for the RP1 DPI interface and the
  `vc4-kms-dpi-generic` overlay.

## Sister project

- **[rayglow](https://github.com/will-davis)** — the renderer/firmware/HAT project this
  translator plugs into. The cross-repo boundary is INTERFACE-CONTRACT.md in this repo.

## Development

Designed and built by Will Davis with Claude (Anthropic) as pair engineer. The complete
(lightly censored) development transcript lives in
`docs/design-history/2026-08-01-claude-session-fpga-wall-build.md` — from toolchain
install to the final signal-integrity characterization, bugs and dead ends included.
