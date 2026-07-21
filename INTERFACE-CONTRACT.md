# INTERFACE-CONTRACT — rayglow ↔ rayglow-fpga

**v0.1 (draft, 2026-07-18).** Single source of truth for the boundary between the Pi 5
(rayglow renderer) and the FPGA (this repo). rayglow references this file by version;
changes bump the version and are noted in both repos' status logs. Items marked
⚠ VERIFY are provisional until bring-up pins them.

## 1. Physical link
- Pi 5 40-pin header ↔ ECP5-EVN **JP8**, short 40-pin ribbon (all 28 GPIOs land in FPGA
  bank 3, 3.3 V — UG Table 5.7). No power sharing: Pi, EVN (12 V), and wall PSUs are
  independent; **grounds bonded** via the ribbon + star scheme (rayglow
  POWER-AND-GROUNDING.md).
- Signaling: 3.3 V CMOS, Pi RP1 DPI mode `rgb888` on GPIO0–27:
  PCLK = GPIO0, **DE = GPIO1 (RP1 requires DE here)**, VSYNC = GPIO2, HSYNC = GPIO3,
  D0–D23 = GPIO4–27. ⚠ VERIFY channel order (Pi 5 color-order quirk,
  raspberrypi/linux#6505) — the compensating swizzle becomes a named constant in gateware
  and is recorded here.

## 2. Video timing (modeline)
- Active 384×128 @ 60 Hz. Provisional blanking: htotal 416 (hfp 8, hsync 16, hbp 8),
  vtotal 140 (vfp 4, vsync 4, vbp 4) → PCLK = 416·140·60 ≈ **3.494 MHz**. ⚠ VERIFY the
  exact PCLK the RP1 divider achieves; contract pins the *geometry*, tolerates PCLK drift.
- Pi config (`/boot/firmware/config.txt`):
  `dtoverlay=vc4-kms-dpi-generic,rgb888,clock-frequency=3500000,hactive=384,hfp=8,hsync=16,hbp=8,vactive=128,vfp=4,vsync=4,vbp=4`
- FPGA captures on PCLK rising edge, qualifies with DE; frame boundary = VSYNC. Buffer
  swap on VSYNC ⇒ latency ≤ 1 frame, no tearing. 120 Hz is a future minor bump.

## 3. Pixel format & gamma ownership
- Pi sends **display-referred 8-bit/channel RGB** — exactly what a monitor would get. In
  DPI mode rayglow does **not** bake `PACK_GAMMA` into the resolve pass (that baking is the
  RP2350-path behavior); `hub75.pack()` is not in this path at all.
- **The FPGA owns gamma**: per-channel 256-entry LUT → 12-bit linear BCM weights (CIE-ish
  curve, hzeller-style). Brightness = global OE scaling in the FPGA, not a Pi-side rescale.

## 4. Wall geometry
- Logical origin top-left, x right, y down — matches the renderer's resolve output.
- **Chain k = tile row k** (k = 0..3, top→bottom), 6 panels left→right, **no serpentine**:
  each chain is one 384×32 strip, 1/16 scan (addr A–D), R1G1B1/R2G2B2 = rows y and y+16
  within the strip.
- Panel tile: P4-2121-64×32. Bench mule: P6-3528-64×32 (electrically equivalent HUB75).

## 4a. JP8 pin map (ECP5 balls) — provisional, from UG Table 5.7

DPI GPIO → Pi 40-pin → RASP signal → ECP5 ball (bank 3, 3.3 V, no series R):

| DPI | GPIO | ball | | DPI | GPIO | ball | | DPI | GPIO | ball |
|---|---|---|---|---|---|---|---|---|---|---|
| **PCLK** | 0 | **L18** (ID_SD) | | D4 | 8 | U19 | | D14 | 18 | T16 |
| **DE** | 1 | **L17** (ID_SC) | | D5 | 9 | T19 | | D15 | 19 | R17 |
| VSYNC | 2 | T17 | | D6 | 10 | U20 | | D16 | 20 | P16 |
| HSYNC | 3 | U16 | | D7 | 11 | R20 | | D17 | 21 | R16 |
| D0 | 4 | U17 | | D8 | 12 | T20 | | D18 | 22 | N17 |
| D1 | 5 | U18 | | D9 | 13 | P20 | | D19 | 23 | P17 |
| D2 | 6 | T18 | | D10 | 14 | P18 | | D20 | 24 | M17 |
| D3 | 7 | R18 | | D11 | 15 | N20 | | D21 | 25 | N18 |
| | | | | D12 | 16 | P19 | | D22 | 26 | N16 |
| | | | | D13 | 17 | N19 | | D23 | 27 | M18 |

✅ **Clock-routing risk RESOLVED (2026-07-20):** PCLK on L18 (a general I/O) is auto-promoted
by nextpnr to a global clock net (DCCA) — log: "promoting clock net dpi_0__pclk__i to global
network", routes on global 0. Both domains pass timing with margin; CDC paths report as
`<async>`. No PLL needed. `top_translator.py` builds clean.

⚠ **Color order:** DPI `rgb888` line-to-color order (which of D0–D23 is R7..B0) is not yet
confirmed on Pi 5 (raspberrypi/linux#6505). The gateware forms `pixel = {R,G,B}` via a
named swizzle constant, resolved by eye at first console-on-panel and pinned here.

## 5. Out of scope (explicitly)
- Audio/feature packets (UDP :5005) and the control plane (TCP :5006) terminate at the Pi
  renderer, exactly as today. The FPGA sees only video.
- The RP2350 4-lane PIO link contract (rayglow CLAUDE.md) is unchanged and remains the
  fallback transport; nothing here supersedes it.
