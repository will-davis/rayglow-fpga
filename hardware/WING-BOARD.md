# WING-BOARD — modular 2-chain level-shifter board

> **STATUS: PARKED (Will, 2026-07-29).** The full 4-chain wall runs on the two RayGLow
> RP2350 HATs (hardware/RAYGLOW-HAT-ADAPTER.md) — they serve the same role. Revisit only
> to consolidate footprint/wiring, or if a higher shift clock (needing data-line series
> termination) is ever wanted. Kept as the design record.

Design intent (2026-07-18, pre-PCB — Phase 3 executes this). One PCB design, built in
multiples: **each board drives exactly 2 complete chains**; 2 boards = today's 4×6 wall,
2 more of the *same board* = the 8×3 escape hatch. PCB lead time is why modularity wins.

## Rules that make modularity work
1. **A board owns complete chains — never split one chain's signals across boards.**
   Within-chain timing (CLK↔data↔LAT) stays on one board; board-to-board skew then can't
   matter.
2. **Boards attach by ribbon, not by stacking.** The board-side input is *our own* fixed
   connector (2×20 IDC-40); a per-position crimped harness maps whichever EVN header feeds
   that board. All EVN pinout irregularity is absorbed by harnesses; the PCB never changes.
3. **Fast signals point-to-point, slow signals bused.** Per board unique: 12 RGB data +
   1 CLK (13 FPGA pins). Shared across all boards via Y-harness: A B C D, LAT, OE (6 FPGA
   pins) — these change at row rate, not pixel rate, and two '245 input loads on a 3.3 V
   line are electrically trivial. All chains scan in lockstep by design (identical strips).

## Pin budget (why this scheme)
| Config | FPGA pins | Fits |
|---|---|---|
| 2 boards / 4 chains | 2×13 + 6 = **32** | = J32 (18) + J33 (14) exactly, both bank 7 @ 3.3 V |
| 4 boards / 8 chains | 4×13 + 6 = **58** | + Versa J39 (~19) / J40 (~30) — harness absorbs the different pinout |

## Per-board contents
- 3× 74AHCT245 (19 signals in: 12 data + CLK + A–D + LAT + OE → 24 channels, 5 spare).
  On hand: 10× SOIC-20W + VSSOP tape — covers 4 boards with spares.
- 2× IDC-16 shrouded HUB75 outputs (10 on hand per manifest §8).
- Series termination footprints (22–33 Ω, 0805 book) on CLK and data at the driver end —
  populate per SI findings; v1 precedent: 22 Ω on CLK only was enough at 4-deep.
- Input: 2×20 IDC-40 — 19 signals + interleaved grounds (J32/J33 are ~half GND pins, so
  harnesses carry real returns; the "missing shared-GND = complete noise" lesson is learned).
- Power: '245 VCC **ratiometric from that board's chains' panel-PSU domain** (screw
  terminal / faston from the panel 5 V, NOT from the EVN or a clean rail), 100 nF per IC +
  bulk. Board ↔ PSU-domain mapping: board 0 = tile rows 0–1 (top PSU), board 1 = rows 2–3
  (bottom PSU) — matches the wall's midline power split.
- LED on VCC (per PSU-domain presence check at a glance).

## Open questions for rev A (resolve before ordering)
- Exact harness pin maps J32→board0 / J33→board1 (write as a table here once gateware pins
  are frozen in the LPF/platform file).
- OE shared vs per-board: shared assumed (uniform brightness); if per-chain brightness
  compensation ever matters, rev B adds a jumper to split OE — cheap insurance, decide at
  layout.
- Mounting: wall-side (short panel ribbons, long harness) vs EVN-side (short harness, long
  panel ribbons). Leaning wall-side — panel ribbons are the SI-critical run.
- Whether board 0 also carries the DPI ribbon pass-through or JP8 mates directly (likely
  direct; mechanical check against the EVN's underside receptacle).
