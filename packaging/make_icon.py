"""Erzeugt packaging/ai_coach.ico (Verlauf im App-Akzent + Pulslinie). Benoetigt Pillow."""

from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 256
HERE = Path(__file__).resolve().parent


def make() -> Image.Image:
    # Diagonaler Verlauf hsl(175,75%,48%) → hsl(200,85%,55%)
    start, end = (31, 214, 192), (40, 170, 235)
    grad = Image.new("RGB", (SIZE, SIZE))
    px = grad.load()
    for y in range(SIZE):
        for x in range(SIZE):
            t = (x + y) / (2 * (SIZE - 1))
            px[x, y] = tuple(round(a + (b - a) * t) for a, b in zip(start, end))

    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle((8, 8, SIZE - 8, SIZE - 8), radius=56, fill=255)
    icon = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    icon.paste(grad, (0, 0), mask)

    # Pulslinie (Training) in dunkler App-Hintergrundfarbe
    pulse = [(44, 140), (92, 140), (112, 92), (140, 186), (164, 116), (178, 140), (212, 140)]
    ImageDraw.Draw(icon).line(pulse, fill=(14, 18, 28, 255), width=18, joint="curve")
    return icon


if __name__ == "__main__":
    out = HERE / "ai_coach.ico"
    make().save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    make().save(HERE.parent / "frontend" / "favicon.png")
    print(f"Icon geschrieben: {out}")
