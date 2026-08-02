# INTERFACE-CONTRACT — rayglow ↔ rayglow-fpga

**v0.1 (draft, 2026-07-18).** Single source of truth for the boundary between the Pi 5
(rayglow renderer) and the FPGA (this repo). rayglow references this file by version;
changes bump the version and are noted in both repos' status logs. Items marked
⚠ VERIFY are provisional until bring-up pins them.

**v0.2-exp (2026-08-02, branch `exp/120hz-dpi`).** Adds §2a: the as-built 60 Hz mode and
the experimental ≥100 Hz DPI modes. Gateware guarantee strengthened: the framebuffer
handoff is now skip-gated — tear-free at ANY modeline; a scan too slow for the source
drops whole source frames instead (EVN LED D8 lights per drop). Ratifies to v0.2 when
the experiment lands on main.

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
- FPGA captures on the PCLK **falling** edge (mid-eye at ≥12.5 MHz; the RP1 drives on the
  rising edge), qualifies with DE; frame boundary = VSYNC. Double-buffer handoff is
  skip-gated (§2a) ⇒ latency ≤ 1 source frame, tearing structurally impossible.

## 2a. As-built + high-rate modes (v0.2-exp)

The RP1-DPI/KMS driver clamps `vactive` to 480 (asked 128, got 384×480) — the FPGA
captures rows 0–127 and drops the rest, which conveniently makes capture a small slice
of the frame. Geometry as driven: htotal 416 (384 + 8/16/8), vtotal 492 (480 + 4/4/4).
The contract pins geometry; the FPGA is modeline-agnostic (DE/VSYNC-derived), so mode
changes are **config.txt-only** — same gateware bitstream throughout.

| Mode | `clock-frequency=` | Source rate | At scan 140.4 Hz (SW5 dflt u=8) |
|---|---|---|---|
| Production 60 Hz | 12500000 | 61.07 Hz | zero drops (budget 12.1 ms ≫ 7.1 ms sweep) |
| **~122 Hz (experiment)** | 25000000 | 122.14 Hz | ~15 % drops → ~104 unique fps shown |
| ~100 Hz (zero-drop fallback) | 20500000 | 100.2 Hz | zero drops at full brightness |
| True 120 Hz (SI experiment) | 45100000 + vfp=416 | 120.0 Hz | zero drops; PCLK 45 MHz on the ribbon — unverified SI |

Drop math (gateware `double_buffer.py`): a source frame is consumed iff the scan sweep
ends within `DPI_period − capture_time` of the previous consumption; capture_time =
128·htotal/PCLK (2.13 ms at 25 MHz). Sweep = 1/refresh. The SW5 brightness knob also
scales refresh, so it doubles as the cadence knob at 122 Hz: **SW5=6 → 171.2 Hz scan,
sweep 5.84 ms < 6.06 ms budget → ZERO drops at 91.5 % of default brightness** (dimmer
u is faster; duty falls slower than u). SW5=8 keeps full brightness and accepts ~15 %
irregular drops. Every displayed sweep is always exactly one source frame regardless.
- The renderer needs no changes: `drm_out` paces on page-flip events, so it follows
  whatever rate the mode advertises (122 fps render ≈ 0.2 ms/frame, trivial).

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

✅ **Color order CONFIRMED (2026-07-20):** no swizzle needed. Framebuffer XRGB8888
(0xFF0000 red / 0x00FF00 green / 0x0000FF blue) painted into fb0 came out RED/GREEN/BLUE
on the panel in order. So `pixel_in[23:16]=R, [15:8]=G, [7:0]=B` (data lines D0..D23 =
GPIO4..27 straight through). rgb888, not bgr888.

## 5. Out of scope (explicitly)
- Audio/feature packets (UDP :5005) and the control plane (TCP :5006) terminate at the Pi
  renderer, exactly as today. The FPGA sees only video.
- The RP2350 4-lane PIO link contract (rayglow CLAUDE.md) is unchanged and remains the
  fallback transport; nothing here supersedes it.
