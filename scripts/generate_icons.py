"""Generate PWA PNG icons (no external design assets required)."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parents[1] / "frontend" / "public" / "icons"
OUT.mkdir(parents=True, exist_ok=True)


def font(size: int):
    for candidate in (r"C:\Windows\Fonts\arialbd.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def make(size: int, maskable: bool = False) -> None:
    image = Image.new("RGB", (size, size), "#eef2ff")
    draw = ImageDraw.Draw(image)
    pad = int(size * (0.18 if maskable else 0.08))
    draw.rounded_rectangle(
        [pad, pad, size - pad, size - pad],
        radius=int(size * 0.22),
        fill="#4f46e5",
    )
    # Simple book + spark motif drawn with primitives (stable across platforms).
    cx, cy = size // 2, size // 2
    bw, bh = int(size * 0.34), int(size * 0.24)
    draw.rounded_rectangle([cx - bw, cy - bh // 2, cx - 4, cy + bh], radius=int(size * 0.02), fill="white")
    draw.rounded_rectangle([cx + 4, cy - bh // 2, cx + bw, cy + bh], radius=int(size * 0.02), fill="#c7d2fe")
    draw.line([cx, cy - bh // 2, cx, cy + bh], fill="#312e81", width=max(2, size // 128))
    text = "PLI"
    f = font(max(12, int(size * 0.11)))
    box = draw.textbbox((0, 0), text, font=f)
    draw.text(
        (cx - (box[2] - box[0]) / 2, cy + int(size * 0.16)),
        text,
        font=f,
        fill="#e0e7ff",
    )
    image.save(OUT / f"icon-{size}.png")


def main() -> None:
    make(192)
    make(512)
    img = Image.new("RGB", (512, 512), "#4f46e5")
    source = Image.open(OUT / "icon-512.png").convert("RGB").resize((400, 400))
    img.paste(source, (56, 56))
    img.save(OUT / "icon-maskable-512.png")
    print(f"Icons written to {OUT}")


if __name__ == "__main__":
    main()
