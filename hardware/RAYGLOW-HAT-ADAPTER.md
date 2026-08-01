# RAYGLOW-HAT-ADAPTER — driving the RP2350 HATs from the ECP5 (Phase 3 intermediate)

Reuse Will's existing **RP2350-HUB75-HAT** boards (`~/Projects/rayglow/hardware`) as the
4-chain level-shifting layer for the FPGA wall, before designing custom wing boards. One
HAT buffers 2 chains; two HATs = the 4-chain 384×128 wall. Passive wiring only.

## No chip-select needed (the caveat, resolved)

The HAT's 4× `SN74AHCT245` are wired **DIR→5 V, /OE→GND** (NET-SPEC §3) — permanently
enabled, unidirectional 3.3→5 V buffers. There is no chip-select on the HUB75 side and
none is wanted (an LED wall scans continuously). The "CS" in the RayGLow design was the
**Pi→RP2350 link's** framing signal (NET-SPEC §6, GP21/GP25) — part of the transport the
FPGA replaces. So: **nothing to hand-build; just wire the ECP5 outputs to each HAT's J1.**

## Physical approach

The HAT's `J1` is a 2×20 **female** socket (it normally receives the RP2350-PiZero). Drive
it from the ECP5 with jumpers — easiest is a 2×20 **male** header seated in J1 with
jumpers landing on its pins, or male-ended jumpers straight into the socket. The FPGA only
needs to drive the 19 signal pins below per HAT; the HAT's own 5 V rail comes from its J5.

## Wiring — Stage 1: one HAT, 2 chains (384×64, top two wall rows)

`top_wall.py` with `NUM_CHAINS=2`. HAT chain A = wall chain 0 (top row), chain B = chain 1.
Each row is ONE 6-panel daisy-chain (decouple the serpentine). ECP5 balls are bank 7 on
J32/J33 (3.3 V); AHCT TTL inputs accept 3.3 V fine.

| Signal | ECP5 ball | ECP5 hdr pin | → HAT J1 pin |
|---|---|---|---|
| **chain 0** R1 | A5 | J32.5  | 27 |
| chain 0 G1 | A4 | J32.6  | 28 |
| chain 0 B1 | C5 | J32.9  | 3  |
| chain 0 R2 | B5 | J32.10 | 5  |
| chain 0 G2 | B4 | J32.13 | 8  |
| chain 0 B2 | C4 | J32.14 | 10 |
| **chain 1** R1 | B3 | J32.17 | 31 |
| chain 1 G1 | A3 | J32.18 | 26 |
| chain 1 B1 | D5 | J32.21 | 24 |
| chain 1 R2 | E4 | J32.22 | 32 |
| chain 1 G2 | D3 | J32.25 | 23 |
| chain 1 B2 | C3 | J32.26 | 19 |
| **addr A** | G5 | J33.17 | 21 |
| addr B | H4 | J33.18 | 33 |
| addr C | H3 | J33.21 | 7  |
| addr D | H5 | J33.22 | 29 |
| **CLK** | F3 | J33.25 | 36 |
| **LAT** | G3 | J33.26 | 11 |
| **OE**  | E2 | J33.29 | 12 |

(The J1-pin column comes from NET-SPEC §3 × the transposed PiZero header pinout, so it
already accounts for the GPIO4↔14 / 5↔15 / 9↔12 / 10↔11 swaps — just follow the table.)

**Ground:** run several jumpers from ECP5 J32/J33 GND pins to HAT J1 GND pins
(9,14,20,25,30,34,39) AND tie in the panel-PSU (−). Single star, same discipline as
POWER-AND-GROUNDING.md — the level shift references this common ground.

**HAT 5 V rail:** feed the HAT's **J5** screw terminal from the panel 5 V supply (this is
the '245 VCC — ratiometric with the panels, per the original design). NOT from the ECP5.

## Stage 2: second HAT, 4 chains (384×128, full wall)

`NUM_CHAINS=4`. HAT #2 wires **identically** (its chain A = wall chain 2, chain B = wall
chain 3), driven from the ECP5's chain-2/3 RGB balls:
- chain 2 RGB = `E3 F4 F5 E5 B1 A2` (J32.29,30,33,34,37,38)
- chain 3 RGB = `C2 B2 D1 C1 E1 D2` (J33.5,6,9,10,13,14)

The **7 control signals (addr A-D, CLK, LAT, OE) are shared** across all chains, so they
fan out to BOTH HATs — run each control jumper to HAT #1 *and* HAT #2's matching J1 pin
(one ECP5 pin, two destinations; two AHCT loads is trivial). Full 4-chain fit: J32 = all
of chains 0-2 RGB (18), J33 = chain 3 RGB (6) + control (7).

## Shared-control fan-out (CLK/LAT/OE/addr → both HATs)

The 7 control signals drive both HATs, so each is a Y from one ECP5 pin to two J1 pins.
- **CLK** (20 MHz pixel rate) is the one worth a twisted pair: CAT6a signal+GND per branch,
  star-split at the ECP5 CLK pin, GND landing next to CLK at both the ECP5 and each J1
  (pin 36) end. Tight return = clean edges.
- **LAT/OE/addr change at row rate (~kHz)** — ~1000× slower than CLK; plain Y-jumpers are
  fine (twist LAT/OE too if convenient, skip for addr).
- J32/J33 are diff-pair headers with **DNI** termination footprints, so pins are plain
  single-ended today. If CLK rings after twisting: (1) 22–33 Ω series R at the ECP5 source
  before the split, then (2) populate a pair-termination footprint. Unlikely needed at 20 MHz.

## Commands (quick reference — Pi-hosted since 2026-07-30)

The EVN's mini-USB now plugs into the **Pi**; the board boots itself from flash (SW1 in
MSPI). Reflash with a new build (desktop → Pi → board; the trailing Refresh auto-boots):
```fish
scp ~/Projects/rayglow-fpga/build/top.bit rpi5:/tmp/top.bit
ssh rpi5 "openFPGALoader -b ecp5_evn -f --unprotect-flash /tmp/top.bit"
```
Volatile SRAM-only load (fast iteration, lost on power cycle):
```fish
ssh rpi5 "openFPGALoader -b ecp5_evn /tmp/top.bit"
```
Run the renderer on the Pi — height = 32×(#chains): 64 for 2 chains, 128 for 4:
```fish
cd ~/rayglow; and uv run python -m rayglow.render <shader.glsl> \
  --output kms --width 384 --height 128 --scale 1
```

## Hardware brightness knob (SW5 positions 1–4)

4-bit code, position 1 = LSB. **All OFF = default brightness (unit 8, 140.4 Hz at the
48 MHz production clock).** Any other pattern = `unit` 1–15 directly: 1 ≈ 12 %
(247 Hz) … 8 = 100 % (140 Hz) … 15 ≈ 190 % (86 Hz). Change anytime; takes effect
within a frame. Dimmer = faster refresh, brighter = slower.

## Shift-clock ceiling (measured 2026-08-01)

24 MHz shift (48 MHz scan) is clean end to end through jumpers → HATs → 6-panel
chains; 30 MHz cascades skew from ~panel 3 on every chain, and output slew rate makes
no difference (the head-end timing budget, not edge rate, is the limit). Pushing past
24 MHz requires interconnect work — terminated backplane/mezzanine — not settings.

## Bring-up notes

- Shift clock starts at **20 MHz** (`PLL12to40`) — the value that ran the 6-panel single
  chain clean. The HAT's 22 Ω CLK series term (R1/R2) may allow pushing higher; if the far
  panels stay clean you can try `PLL12to60` (30 MHz) for more refresh/brightness.
- Data lines are **not** series-terminated on this HAT (NET-SPEC §9 deferred it) — the
  colour-bleed-to-white failure mode over a long chain is the tell; drop the clock if seen.
- The custom wing board (WING-BOARD.md) is the eventual replacement — its value over the
  HAT is data-line series termination (higher clock) + a connector layout meant for the
  FPGA. Do it after the wall is proven on the HATs.
