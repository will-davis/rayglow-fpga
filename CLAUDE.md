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
- **Board needs BOTH 12 V barrel (J37) AND mini-USB (J2) to enumerate/program.** The
  FT2232H runs off the +3.3 V rail, which is derived from 12 V (Fig A.3 + A.12), not USB.
  If `lsusb` lacks 0403:6010 / `openFPGALoader --detect` says "device not found": reseat
  the mini-USB and confirm 12 V (blue D26 "12VIN GOOD" + green D25 "+3.3V" LEDs lit).
  Seen 2026-07-20 — a nudged mini-USB looked exactly like broken panel wiring.
- **UART-to-FTDI is NOT populated** (R34/R35 DNI, UG §6.2) — the debug console is PMOD
  J31 ↔ **Pico debugprobe** UART bridge (probe GP4→J31.2/C7, GP5←J31.1/C6, GND→J31.5;
  `/dev/ttyACM0` @ 115200). FTDI I²C to bank 0 *is* wired.
- **SRAM config is volatile** — after any power cycle, reload the bitstream before
  trusting any test result (a blank FPGA floats its pins and looks like broken wiring).
- 8 LEDs bank 1 active-low (Table 7.4); SW4 = user button P4 active-low (Table 7.3).
- HUB75 out: J32 (18 GPIO) + J33 (14 GPIO), both bank 7 / VCCIO7 = 3.3 V (JP11 default);
  expansion: Versa J39 (~19) / J40 (~30). Signal plan: hardware/WING-BOARD.md.

## Current state
ECP5 FPGA translation layer for the rayglow LED wall (Pi 5 DPI in → HUB75 out).
**Phase 0 complete 2026-07-19**: toolchain (OSS CAD Suite in `~/opt`), blinky, button/DIP,
PLL 12→60 MHz two-domain design, UART echo console via Pico debugprobe — all verified on
hardware, all sims green. Next: **Phase 1** — the HUB75 BCM scan-out engine, sim-first,
then first light on a retired P6 bench panel (wall v2 stays on the RP2350 path meanwhile).
