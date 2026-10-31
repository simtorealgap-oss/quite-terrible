#!/usr/bin/env python3
"""Draw static/og.png, the 1200x630 social preview. Run on macOS (uses Apple SD Gothic Neo)."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONT = '/System/Library/Fonts/AppleSDGothicNeo.ttc'
BG, INK, MUTED, BRAND = (242, 241, 238), (20, 20, 20), (110, 112, 118), (232, 72, 60)


def font(size, index=6):  # 6 = Bold, 2 = Medium in Apple SD Gothic Neo
    return ImageFont.truetype(FONT, size, index=index)


def ram_stick(width):
    """The hero's RAM stick, pixelated the same way the site draws it."""
    w, h = 1000, 360
    im = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle((24, 250, 976, 294), fill=(47, 107, 58))
    d.rounded_rectangle((16, 20, 984, 266), 16, fill=(29, 32, 39))
    for x in range(-200, w, 46):
        d.polygon([(x, 266), (x + 120, 54), (x + 138, 54), (x + 18, 266)], fill=(42, 46, 55))
    d.rounded_rectangle((16, 20, 984, 54), 16, fill=BRAND)
    d.rectangle((16, 38, 984, 54), fill=BRAND)
    d.text((64, 70), 'DDR5', font=font(128), fill=(242, 239, 232))
    d.rounded_rectangle((664, 96, 944, 224), 10, fill=(242, 239, 232))
    d.text((692, 112), 'CL30', font=font(34), fill=(20, 22, 27))
    d.text((692, 162), 'PRICE ↑↑↑', font=font(30), fill=BRAND)
    for x in range(36, 968, 13):
        if x < 548 or x > 584:
            d.rectangle((x, 294, x + 8, 340), fill=(216, 169, 68))
    step = 4
    small = im.resize((w // step, h // step), Image.NEAREST)
    big = small.resize((width, int(width * h / w)), Image.NEAREST)
    return big


def main():
    img = Image.new('RGB', (1200, 630), BG)
    d = ImageDraw.Draw(img)
    d.text((600, 210), 'DRAM', font=font(330), fill=(232, 231, 228), anchor='mm')
    stick = ram_stick(760)
    img.paste(stick, ((1200 - stick.width) // 2, 70), stick)
    d.text((70, 430), 'Quite Terrible', font=font(64), fill=INK)
    d.text((72, 512), '램·그래픽카드 가격, 매일 오전 9시', font=font(36, 2), fill=MUTED)
    d.text((72, 560), 'RAM & GPU prices, checked daily', font=font(30, 2), fill=MUTED)
    d.text((1130, 560), '“quite terrible.”', font=font(34), fill=BRAND, anchor='rs')
    img.save(ROOT / 'static/og.png', optimize=True)
    print(ROOT / 'static/og.png')


if __name__ == '__main__':
    main()
