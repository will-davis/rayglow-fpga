# SWITCHES-AND-LEDS — operator reference for the wall bitstream

What every user switch and indicator LED on the ECP5-EVN means while `top_wall.py` (the
production gateware) is running. Board sources: LEDs = UG Table 7.4, SW5 DIP = Table 7.1
/ Fig A.10, SW4 button = Table 7.3 (FPGA-EB-02017-1.3, `.reference/ecp5-evn/`).
Amaranth `led`/`switch` resource index *i* ↔ board designator D(5+*i*) / SW5 position
(*i*+1).

## SW5 — 8-position DIP

**Positions 1–4 = the hardware brightness knob**, read as a 4-bit code (position 1 =
LSB, ON = 1). All OFF selects the default `unit=8`; any other pattern selects `unit` =
the code value 1–15 directly. `unit` is the BCM LSB display time, so it scales the
lit-time of every plane linearly — and because shorter displays also shorten the scan
frame, **dimmer settings refresh faster**. The code is FF-synchronized into the scan
domain; flipping it live is safe and takes effect at the next plane latch (no glitch,
no reload).

Positions **5–8: unused** — no effect. **SW4 (push button): unused.** (SW1 is NOT a
user switch — it selects the flash-boot CFGMDN mode, MSPI = pos2 ON / pos3 OFF /
pos4 ON; leave it alone. See ROADMAP Phase 4.)

Numbers below are for the production config (48 MHz scan, B=11, guard=40, MSB splits
{9:2, 10:4}). Brightness is relative to the default. Drop rate = fraction of source
frames the skip-gated handoff sits out (`double_buffer.py`; they drop cleanly — never
tearing); at the 61 Hz source mode every setting is drop-free.

| unit | SW5 ON (1234) | Refresh | Brightness | Drops @122 Hz src |
|---|---|---|---|---|
| 8 (dflt) | ····  (all OFF) | 140.4 Hz | 100 % | 15 % |
| 1 | 1··· | 246.6 Hz | 22 % | 0 |
| 2 | ·2·· | 246.6 Hz | 44 % | 0 |
| 3 | 12·· | 246.6 Hz | 66 % | 0 |
| 4 | ··3· | 215.2 Hz | 77 % | 0 |
| 5 | 1·3· | 190.7 Hz | 85 % | 0 |
| **6** | **·23·** | **171.2 Hz** | **91 %** | **0 ← 122 Hz sweet spot** |
| 7 | 123· | 154.3 Hz | 96 % | 7 % |
| 9 | 1··4 | 128.8 Hz | 103 % | 22 % |
| 10 | ·2·4 | 119.0 Hz | 106 % | 28 % |
| 11 | 12·4 | 110.6 Hz | 108 % | 33 % |
| 12 | ··34 | 103.3 Hz | 110 % | 37 % |
| 13 | 1·34 | 96.7 Hz | 112 % | 41 % |
| 14 | ·234 | 90.9 Hz | 113 % | 45 % |
| 15 | 1234 | 85.7 Hz | 115 % | 48 % |

Why the shape: units 1–3 are shift-bound (every plane's display hides under the
770-cycle shift, so refresh pegs at the 246.6 Hz floor while brightness scales); above
that, display time dominates and refresh falls as brightness climbs. Zero drops at a
122 Hz source needs refresh > 165.1 Hz (scan sweep shorter than the 6.06 ms handoff
budget) → **unit ≤ 6**. Above default, brightness buys little (+15 % at unit=15) and
costs cadence at 122 Hz — those settings exist for the 61 Hz mode.

## User LEDs D5–D12 (red row, bank 1, active-low)

| LED | Signal | Meaning |
|---|---|---|
| D5–D7 | — | Unused (not driven by the wall bitstream). |
| D8 | `skip_blink` | **Source-frame drops.** Stretched ~0.17 s pulse per DPI frame the writer sat out because the scan hadn't consumed the previous one. Dark = every source frame reaches the panel. Steady/solid = routine dropping — expected at 122 Hz with unit ≥ 7, never at 61 Hz. |
| D9 | `err_blink` | **Capture-error rate.** Stretched ~0.3 s pulse per malformed line — occasional blink = rare glitch, solid = ongoing capture trouble. Armed only after the first VSYNC (ignores the startup partial line). |
| D10 | `err_short` | **Latch: a SHORT line happened** (< 384 px — DE glitch / missed clocks class). Stays lit until reconfigure; dark since arming = zero events, ever. |
| D11 | `err_long` | **Latch: a LONG line happened** (> 384 px — PCLK ringing / double-count class). Same latch semantics. |
| D12 | `frame` | Scan-frame pulse (~140 Hz at default unit) — looks dimly lit. Proof the scan engine is sweeping; brightness tracks refresh rate. |

Reading the cluster: **D10/D11 dark = the capture path has been perfect since config**
— any streaking you can see is therefore presentation physics, not data corruption (the
2026-07-30 reclassification). D8 tells you the cadence story; D9 the error *rate* when
D10/D11 do latch.

## Board status LEDs (not gateware-driven)

| LED | Meaning |
|---|---|
| D4 (green, DONE) | FPGA configured — lights ~1 s after power with flash boot, or after any `openFPGALoader` load. Dark = blank FPGA (floating pins look like broken wiring — reload first, debug second). |
| D26 (blue, 12VIN GOOD) | 12 V barrel input present (J37). |
| D25 (green, +3.3V) | Main 3.3 V rail up (derived from 12 V — both this and D26 must be lit for the FT2232H to enumerate). |
