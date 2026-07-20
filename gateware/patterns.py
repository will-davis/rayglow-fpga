"""Test-pattern images and framebuffer-bank packing (pure Python, no Amaranth).

An "image" is a list of rows, each row a list of 24-bit packed pixels (R<<16|G<<8|B),
sized (2*scan) rows x width columns — one chain's electrical strip. `banks_from_image`
splits it into the two per-half bank init lists the scan-out core's EBRs consume:
bank word at [addr*width + x] is the pixel lit while the row address lines equal `addr`
(top half rows 0..scan-1 on R1G1B1, bottom half rows scan..2*scan-1 on R2G2B2).
"""


def rgb(r, g, b):
    return ((r & 0xFF) << 16) | ((g & 0xFF) << 8) | (b & 0xFF)


def gradient(width, height):
    """R ramps left-to-right, G top-to-bottom, B counter-ramps — plus orientation
    corners: white top-left, red top-right, green bottom-left, blue bottom-right."""
    img = [
        [rgb(x * 255 // (width - 1), y * 255 // (height - 1), 255 - x * 255 // (width - 1))
         for x in range(width)]
        for y in range(height)
    ]
    img[0][0] = rgb(255, 255, 255)
    img[0][-1] = rgb(255, 0, 0)
    img[-1][0] = rgb(0, 255, 0)
    img[-1][-1] = rgb(0, 0, 255)
    return img


def counting(width, height):
    """Deterministic every-pixel-distinct-ish pattern for golden-model tests."""
    return [
        [rgb((x * 37 + y * 61) % 256, (x * 11 + y * 199) % 256, (x * 151 + y * 7) % 256)
         for x in range(width)]
        for y in range(height)
    ]


def color_bars_fade(width, height):
    """8 pure-hue vertical bars (crosstalk test: adjacent saturated channels) that fade
    top=full to bottom=off (dark-region test: does each hue stay true as it dims?).
    Bar order R G B C M Y W black — black is the leakage/ghost reference (should stay off).
    """
    hues = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (0, 255, 255),
            (255, 0, 255), (255, 255, 0), (255, 255, 255), (0, 0, 0)]
    bar = max(1, width // len(hues))
    img = []
    for y in range(height):
        f = (height - 1 - y)
        row = []
        for x in range(width):
            r, g, b = hues[min(x // bar, len(hues) - 1)]
            row.append(rgb(r * f // (height - 1), g * f // (height - 1), b * f // (height - 1)))
        img.append(row)
    return img


def banks_from_image(img, width, scan):
    """Split a (2*scan x width) image into [top_init, bottom_init] bank word lists."""
    assert len(img) == 2 * scan and all(len(row) == width for row in img), "image/geometry mismatch"
    top = [img[addr][x] for addr in range(scan) for x in range(width)]
    bottom = [img[addr + scan][x] for addr in range(scan) for x in range(width)]
    return [top, bottom]


def cie1931_lut(bits):
    """Perceptual (CIE 1931 lightness) 8-bit code -> `bits`-bit linear duty. The standard
    LED-wall gamma: equal code steps look like equal brightness steps to the eye."""
    out = []
    for v in range(256):
        lightness = v * 100.0 / 255.0
        y = lightness / 903.3 if lightness <= 8.0 else ((lightness + 16.0) / 116.0) ** 3
        out.append(round(y * ((1 << bits) - 1)))
    return out
