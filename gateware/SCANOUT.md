# SCANOUT — HUB75 BCM engine design notes

Code: `scanout.py` (`Hub75Core`). Verified by `tests/test_scanout.py` (golden model:
per-pixel lit-time over a full frame == `unit * lut[source]`, exact). Status: **v1,
sequential** — shift, latch, display, never overlapped. The overlap upgrade is v2
(ROADMAP Phase 3) and roughly doubles attainable refresh.

## Data path

```
FB bank per (chain, half)          gamma LUT (256 x B, CIE1931)      plane bit-select
EBR, RGB888, [addr*W + x]  ──►  3 read ports per bank (R,G,B)  ──►  rgb[6N] pins
```

- Storing **raw RGB888** keeps the framebuffer format identical to the future DPI wire
  format (INTERFACE-CONTRACT §3) and leaves gamma where the contract puts it: here.
- LUT-at-readout costs read ports (3 per bank; synth replicates the ROM) but keeps the
  FB at 24 bpp — at 384x128 that's what makes double-buffering fit in EBR.
- Each FB bank is dual-port: scan-out owns one port, the Phase 2 DPI ingest gets the other.

## Read pipeline (why PRELOAD is 2 cycles)

FB and LUT are both synchronous-read: FB addr presented in cycle t → FB data at t+1 →
LUT data at t+2. A pixel slot is 2 cycles (CLK low with fresh data, then CLK high), so
the pipeline depth exactly equals one slot: PRELOAD primes x=0 for 2 cycles, then SHIFT
slot x issues the read for x+1. Data changes only on CLK-low edges — half a slot of
setup before the panel's rising-edge capture.

## FSM and BCM timing

Per row address, for each plane b in 0..B-1: PRELOAD (2) → SHIFT (2W) → LATCH (1) →
DISPLAY (U·2^b, blank de-asserted). So:

    t_row   = B·(2W + 3) + U·(2^B − 1)      [cycles]
    refresh = f_clk / (scan · t_row)
    duty    = U·(2^B − 1) / t_row

| Config | f_clk | t_row | refresh | duty |
|---|---|---|---|---|
| Bench: W=64, B=10, U=4 (`top_hub75`) | 12 MHz | 5,402 | **139 Hz** | 76 % |
| Bench in the 60 MHz PLL domain | 60 MHz | 5,402 | 694 Hz | 76 % |
| Wall v1-style: W=384, B=10, U=8 | 60 MHz | 15,894 | 236 Hz | 51 % |
| Wall + v2 overlap (shift hidden) | 60 MHz | ~8,200 | ~457 Hz | ~100 % |

`unit` (U) is the brightness/refresh trade — the direct descendant of rayglow's
`OE_GAIN`. Global brightness control later = scaling U or gating OE.

## v2 upgrades (recorded, not yet built)
1. Overlap: shift plane b+1 while displaying plane b (two coupled FSMs, latch handshake).
2. Address set-ahead + blanking guard interval (ghosting control at high refresh).
3. Brightness register; per-plane OE trim if the panel needs it.

## Bench wiring: J32 ↔ one P6-3528 64x32 panel (INPUT connector)

FPGA drives 3.3 V unbuffered (v1-wall precedent: clean over 4 panels); SLEWRATE=SLOW,
DRIVE=8 on purpose. Shift clock is 6 MHz (12 MHz / 2-cycle slots).

| Signal | J32 pin | Ball | HUB75 pin | | Signal | J32 pin | Ball | HUB75 pin |
|---|---|---|---|---|---|---|---|---|
| R1 | 5 | A5 | 1 | | A | 17 | B3 | 9 |
| G1 | 6 | A4 | 2 | | B | 18 | A3 | 10 |
| B1 | 9 | C5 | 3 | | C | 21 | D5 | 11 |
| R2 | 10 | B5 | 5 | | D | 22 | E4 | 12 |
| G2 | 13 | B4 | 6 | | CLK | 25 | D3 | 13 |
| B2 | 14 | C4 | 7 | | LAT | 26 | C3 | 14 |
| | | | | | OE | 29 | E3 | 15 |

**Grounds (do not skimp):** HUB75 pins 4, 8, 16 → J32 GND pins (3/4, 11/12, 27/28 are
adjacent to the signal groups). Run at least three returns, one beside CLK. The HUB75
"E" pin (8) is ground on 1/16-scan panels.

**Power:** panel 5 V from a bench PSU direct to the panel's power lug — never from the
EVN. Bond PSU(−) to EVN ground (the signal returns above + one dedicated wire) — single
star point, per rayglow POWER-AND-GROUNDING.md. One 64x32 P6 at full white is ~2 A-ish
at these duty cycles; the 150 W supply loafs.

**Expected image (`top_hub75`):** R ramps left→right, G top→bottom, B right→left;
corners: white TL, red TR, green BL, blue BR — any flip/rotation is immediately visible.
LED D12 flickers at frame rate (~139 Hz, looks dimly lit).
