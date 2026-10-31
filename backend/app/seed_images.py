"""Render simple synthetic product photos so the seed ships image samples (no downloads).

Two renders of the SAME story share shape + colour but differ in background, rotation,
size and position, like two different phone photos of one object."""
import random

from PIL import Image, ImageDraw, ImageFilter

from .seed_data import RGB

SIZE = 256


def _shade(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c)


def render(shape: str, color: str, rng: random.Random) -> Image.Image:
    base = RGB.get(color, (120, 120, 120))
    bg_tone = rng.choice([(236, 232, 224), (205, 215, 225), (90, 95, 105), (224, 214, 196), (170, 160, 150)])
    img = Image.new("RGB", (SIZE, SIZE), bg_tone)
    d = ImageDraw.Draw(img)
    for y in range(0, SIZE, 4):                              # soft gradient background
        d.line([(0, y), (SIZE, y)], fill=_shade(bg_tone, 0.92 + 0.12 * y / SIZE))
    layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    g = ImageDraw.Draw(layer)
    main, dark, light = base, _shade(base, 0.6), _shade(base, 1.25)
    cx, cy, s = SIZE // 2, SIZE // 2, rng.uniform(0.85, 1.1)

    def rr(x0, y0, x1, y1, r=14, fill=main, outline=dark):
        g.rounded_rectangle([cx + x0 * s, cy + y0 * s, cx + x1 * s, cy + y1 * s], radius=r, fill=fill, outline=outline, width=3)

    if shape == "phone":
        rr(-45, -85, 45, 85, 18); rr(-37, -70, 37, 66, 8, fill=(15, 20, 30), outline=dark)
    elif shape == "laptop":
        rr(-85, -60, 85, 30, 8); rr(-75, -50, 75, 22, 4, fill=(20, 25, 35), outline=dark); rr(-100, 30, 100, 44, 6, fill=light)
    elif shape == "earbuds":
        rr(-55, -35, 55, 40, 26); g.line([(cx, cy - 35), (cx, cy + 40)], fill=dark, width=3)
    elif shape == "headphones":
        g.arc([cx - 70 * s, cy - 80 * s, cx + 70 * s, cy + 60 * s], 180, 360, fill=dark, width=12)
        g.ellipse([cx - 85 * s, cy - 5 * s, cx - 45 * s, cy + 55 * s], fill=main, outline=dark, width=3)
        g.ellipse([cx + 45 * s, cy - 5 * s, cx + 85 * s, cy + 55 * s], fill=main, outline=dark, width=3)
    elif shape == "calculator":
        rr(-45, -75, 45, 75, 10); rr(-35, -65, 35, -35, 3, fill=(170, 200, 170))
        for r_ in range(4):
            for c_ in range(3):
                g.rectangle([cx + (-33 + c_ * 24) * s, cy + (-22 + r_ * 24) * s, cx + (-15 + c_ * 24) * s, cy + (-8 + r_ * 24) * s], fill=light)
    elif shape == "watch":
        rr(-18, -95, 18, 95, 8, fill=_shade(main, 0.8)); g.ellipse([cx - 48 * s, cy - 48 * s, cx + 48 * s, cy + 48 * s], fill=light, outline=dark, width=5)
        g.line([(cx, cy), (cx, cy - 28 * s)], fill=dark, width=4); g.line([(cx, cy), (cx + 20 * s, cy + 6 * s)], fill=dark, width=3)
    elif shape == "box":
        rr(-70, -45, 70, 45, 10); rr(-55, -30, 55, -10, 4, fill=light)
    elif shape == "wallet":
        rr(-80, -52, 80, 52, 14); g.line([(cx - 80 * s, cy), (cx + 80 * s, cy)], fill=dark, width=3)
        for i in range(-70, 71, 14):
            g.line([(cx + i * s, cy - 46 * s), (cx + (i + 6) * s, cy - 46 * s)], fill=light, width=2)
        rr(40, -10, 62, 10, 4, fill=light)
    elif shape == "backpack":
        rr(-60, -75, 60, 85, 32); rr(-42, -5, 42, 50, 10, fill=_shade(main, 0.85))
        g.arc([cx - 30 * s, cy - 105 * s, cx + 30 * s, cy - 55 * s], 180, 360, fill=dark, width=8)
        g.line([(cx - 60 * s, cy - 30 * s), (cx - 78 * s, cy + 40 * s)], fill=dark, width=8)
        g.line([(cx + 60 * s, cy - 30 * s), (cx + 78 * s, cy + 40 * s)], fill=dark, width=8)
    elif shape == "handbag":
        g.arc([cx - 50 * s, cy - 95 * s, cx + 50 * s, cy - 10 * s], 180, 360, fill=dark, width=8); rr(-75, -20, 75, 70, 18)
        rr(-12, -20, 12, -2, 3, fill=light)
    elif shape == "key":
        g.ellipse([cx - 80 * s, cy - 30 * s, cx - 20 * s, cy + 30 * s], outline=dark, width=10, fill=None)
        rr(-30, -8, 85, 8, 4, fill=light); [g.rectangle([cx + (45 + 14 * i) * s, cy + 8 * s, cx + (53 + 14 * i) * s, cy + 28 * s], fill=light) for i in range(3)]
    elif shape == "card":
        rr(-90, -57, 90, 57, 10, fill=main); g.rectangle([cx - 90 * s, cy - 30 * s, cx + 90 * s, cy - 8 * s], fill=_shade(main, 0.55))
        rr(-76, 4, -24, 46, 4, fill=light)
        for i in range(3):
            g.line([(cx - 8 * s, cy + (12 + 12 * i) * s), (cx + 70 * s, cy + (12 + 12 * i) * s)], fill=dark, width=3)
    elif shape == "jacket":
        g.polygon([(cx - 40 * s, cy - 80 * s), (cx + 40 * s, cy - 80 * s), (cx + 95 * s, cy - 30 * s), (cx + 80 * s, cy + 80 * s),
                   (cx - 80 * s, cy + 80 * s), (cx - 95 * s, cy - 30 * s)], fill=main, outline=dark)
        g.line([(cx, cy - 80 * s), (cx, cy + 80 * s)], fill=dark, width=4)
    elif shape == "scarf":
        g.polygon([(cx - 90 * s, cy - 30 * s), (cx + 90 * s, cy - 30 * s), (cx + 90 * s, cy + 15 * s), (cx - 90 * s, cy + 15 * s)], fill=main, outline=dark)
        for i in range(-80, 81, 16):
            g.line([(cx + i * s, cy + 15 * s), (cx + i * s, cy + 40 * s)], fill=dark, width=3)
        for i in range(-90, 91, 22):
            g.line([(cx + i * s, cy - 30 * s), (cx + (i + 10) * s, cy + 15 * s)], fill=light, width=3)
    elif shape == "ring":
        g.ellipse([cx - 60 * s, cy - 40 * s, cx + 60 * s, cy + 70 * s], outline=main, width=14); g.polygon(
            [(cx, cy - 75 * s), (cx + 22 * s, cy - 48 * s), (cx, cy - 25 * s), (cx - 22 * s, cy - 48 * s)], fill=(120, 190, 240), outline=dark)
    elif shape == "book":
        rr(-60, -80, 60, 80, 6); g.rectangle([cx - 60 * s, cy - 80 * s, cx - 48 * s, cy + 80 * s], fill=dark); rr(-35, -55, 45, -25, 3, fill=light)
    elif shape == "bottle":
        rr(-26, -60, 26, 85, 20); rr(-16, -85, 16, -58, 5, fill=dark); g.rectangle([cx - 26 * s, cy - 10 * s, cx + 26 * s, cy + 12 * s], fill=light)
    elif shape == "umbrella":
        g.pieslice([cx - 95 * s, cy - 85 * s, cx + 95 * s, cy + 55 * s], 180, 360, fill=main, outline=dark)
        g.line([(cx, cy - 15 * s), (cx, cy + 75 * s)], fill=dark, width=6); g.arc([cx, cy + 55 * s, cx + 36 * s, cy + 95 * s], 0, 180, fill=dark, width=6)
    elif shape == "glasses":
        g.ellipse([cx - 80 * s, cy - 28 * s, cx - 10 * s, cy + 36 * s], outline=dark, fill=(150, 170, 190), width=7)
        g.ellipse([cx + 10 * s, cy - 28 * s, cx + 80 * s, cy + 36 * s], outline=dark, fill=(150, 170, 190), width=7)
        g.line([(cx - 10 * s, cy), (cx + 10 * s, cy)], fill=dark, width=6)
    elif shape == "helmet":
        g.pieslice([cx - 85 * s, cy - 75 * s, cx + 85 * s, cy + 85 * s], 180, 360, fill=main, outline=dark)
        for i in range(-3, 4):
            g.line([(cx + i * 20 * s, cy - 70 * s), (cx + i * 14 * s, cy + 5 * s)], fill=dark, width=3)
    else:
        rr(-50, -50, 50, 50, 14)
    layer = layer.rotate(rng.uniform(-18, 18), resample=Image.BICUBIC, center=(cx, cy))
    shadow = layer.filter(ImageFilter.GaussianBlur(6))
    img.paste((0, 0, 0), (6, 8), shadow.split()[3].point(lambda a: a // 3))
    img.paste(layer, (0, 0), layer)
    px = img.load()                                          # light sensor noise
    for _ in range(600):
        x, y = rng.randrange(SIZE), rng.randrange(SIZE)
        v = px[x, y]
        px[x, y] = tuple(max(0, min(255, c + rng.randint(-14, 14))) for c in v)
    return img
