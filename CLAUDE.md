# CLAUDE.md — rayglow-fpga

Agent guidance. Human orientation is README.md — read it first.

## Session start
Read `will-notes.md` — Will's inbox to you. Treat items as instructions, clear what you
resolve, never add your own notes there.

## Layout
- `gateware/` — Amaranth HDL. Root `pyproject.toml` is the uv project; **all Python via uv**.
- `tests/` — pytest simulation testbenches. Sim runs with zero system deps (amaranth-yosys
  wheel); only `platform.build()` needs the OSS CAD Suite on PATH.
- `hardware/` — topic docs, current truth (SHOUTING-KEBAB names, e.g. WING-BOARD.md).
- `docs/design-history/` — superseded docs, never current. Supersede by moving here (dated),
  never by silent deletion.
- `.reference/<component>/` — datasheets/pinouts per chip, git-ignored. Add a folder per part.
- `tools/` — verification scripts.

## Sister repo: ~/Projects/rayglow
The renderer/firmware/HAT project (RP2350 path — keep it working, changes there are
additive and flag-guarded only, e.g. the future `--output kms`). Both cwds share the same
memory pool (`~/.claude/projects/-home-will-Projects-rayglow/memory/`). The cross-repo
boundary is **INTERFACE-CONTRACT.md in this repo** — the single source of truth; version
bumps propagate to rayglow by reference, never by copying. Deep background lives in
rayglow's `ROADMAP.md` §5, `hardware/POWER-AND-GROUNDING.md`, and
`docs/design-history/2026-06-18-claude-session-PIO-BUS.md`.

## Conventions
- **Sim first.** Every gateware module lands with a pytest simulation; hardware is for
  confirming, not discovering. Golden-model checks may import rayglow's numpy reference
  logic where formats overlap.
- Cite datasheet section/page for electrical claims (board facts: UG = FPGA-EB-02017-1.3
  in `.reference/ecp5-evn/`).
- Check `~/.claude/reference/lab-inventory.md` before proposing purchases.
- Keep the **Current state** section below updated as phases complete.
- Commands for Will in fish syntax; git is agent-managed, small commits at checkpoints.

## Board facts (verified against UG 1.3)
- LFE5UM5G-85F-8BG381: 84k LUT, **3744 Kbit EBR** (208×18 Kb), 178 GPIO. nextpnr device
  `--um5g-85k`; `openFPGALoader -b ecp5_evn` (SRAM load; `-f` for MX25L12833F flash).
- **JP8** = 40-pin RPi header, all 28 GPIOs → bank 3, 3.3 V (UG Table 5.7). GPIO0/1 arrive
  as RASP_ID_SD (L18) / RASP_ID_SC (L17) — needed: DPI PCLK is GPIO0, DE **must** be GPIO1.
- Clocks (UG Table 4.1): 12 MHz FTDI (ball A10) — **only alive while USB plugged, JP2
  installed**; 200 MHz X2 (Y19/W20, JP9 open) is the standalone clock; X5 50 MHz DNI.
- **UART-to-FTDI is NOT populated** (R34/R35 DNI, UG §6.2) — debug console goes out PMOD
  J31 to the Waveshare USB-UART bridge instead. FTDI I²C to bank 0 *is* wired.
- 8 LEDs bank 1 active-low (Table 7.4); SW4 = user button P4 active-low (Table 7.3).
- HUB75 out: J32 (18 GPIO) + J33 (14 GPIO), both bank 7 / VCCIO7 = 3.3 V (JP11 default);
  expansion: Versa J39 (~19) / J40 (~30). Signal plan: hardware/WING-BOARD.md.

## Current state
ECP5 FPGA translation layer for the rayglow LED wall (Pi 5 DPI in → HUB75 out) —
scaffolded 2026-07-18. Plan + contract drafted; blinky sim green; **toolchain installed**
(OSS CAD Suite in `~/opt`, on fish PATH) and the blinky bitstream builds. Phase 0
remaining: udev rule (sudo), first board flash, button/UART/PLL milestones. Wall v2
meanwhile runs on the RP2350 path at reduced clock.
