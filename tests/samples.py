"""Reproducible artwork fixtures, also installed into samples/ for manual use."""
import io
import math
from pathlib import Path
from PIL import Image, ImageDraw


def cookie(kind='smile', antialias=False):
    factor = 3 if antialias else 1
    image = Image.new('RGB', (256, 256), 'white')
    d = ImageDraw.Draw(image)
    if kind == 'star':
        points = [(128 + (110 if i % 2 == 0 else 54) * math.sin(i * math.pi / 5),
                   128 - (110 if i % 2 == 0 else 54) * math.cos(i * math.pi / 5)) for i in range(10)]
        d.polygon(points, fill='blue', outline='red', width=5)
        d.ellipse((111, 110, 145, 144), fill='lime')
    else:
        d.ellipse((20, 20, 236, 236), fill='blue', outline='red', width=5)
        d.ellipse((76, 78, 93, 100), fill='lime')
        d.ellipse((164, 78, 181, 100), fill='lime')
        d.arc((72, 91, 184, 188), 10, 170, fill='lime', width=7)
        if kind == 'open':
            d.rectangle((119, 10, 136, 31), fill='white')
        if kind == 'outside':
            d.ellipse((240, 100, 253, 130), fill='lime')
        if kind == 'loop':
            d.ellipse((102, 110, 154, 160), outline='lime', width=8)
    if factor > 1:
        # Deliberately resample to create antialias blends without altering layout.
        image = image.resize((256 * factor, 256 * factor)).resize((256, 256), Image.Resampling.LANCZOS)
    return image


def roller(kind='diagonal'):
    image = Image.new('RGB', (128, 96), 'white')
    d = ImageDraw.Draw(image)
    if kind == 'diagonal':
        for x in range(-100, 220, 24):
            d.line((x, 0, x + 96, 96), fill='black', width=7)
    elif kind == 'squares':
        for y in range(8, 96, 24):
            for x in range(8, 128, 24):
                d.rectangle((x, y, x + 10, y + 10), fill='black')
    elif kind == 'seam':
        d.rectangle((0, 25, 18, 65), fill='black')
        d.rectangle((109, 25, 127, 65), fill='black')
    elif kind == 'grayscale':
        # Smooth, periodic waves with white crests and black troughs.
        for x in range(128):
            for y in range(96):
                value = round(127.5 * (1 + math.cos(4 * math.pi * x / 127) * math.cos(2 * math.pi * y / 95)))
                image.putpixel((x, y), (value, value, value))
    return image


def encoded(image):
    stream = io.BytesIO()
    image.save(stream, format='PNG')
    return stream.getvalue()


def write_samples():
    target = Path(__file__).resolve().parents[1] / 'samples'
    target.mkdir(exist_ok=True)
    for kind in ['smile', 'star', 'open', 'outside', 'loop']:
        cookie(kind).save(target / f'cookie_{kind}.png')
    cookie(antialias=True).save(target / 'cookie_antialiased.png')
    for kind in ['diagonal', 'squares', 'seam', 'grayscale']:
        roller(kind).save(target / f'roller_{kind}.png')


if __name__ == '__main__':
    write_samples()
