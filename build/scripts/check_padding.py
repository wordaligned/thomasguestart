from PIL import Image
from pathlib import Path

root = Path(__file__).resolve().parents[2]
images_dir = root / 'images'
flags = []
for p in sorted(images_dir.glob('*.jpg')):
    if p.name.startswith('watermarked'):
        continue
    try:
        im = Image.open(p).convert('RGB')
        w, h = im.size
        bw = max(1, int(w * 0.05))
        bh = max(1, int(h * 0.05))
        left = im.crop((0, 0, bw, h))
        right = im.crop((w - bw, 0, w, h))
        top = im.crop((0, 0, w, bh))
        bottom = im.crop((0, h - bh, w, h))
        def black_fraction(region):
            data = region.getdata()
            total = len(data)
            black = sum(1 for r, g, b in data if r < 20 and g < 20 and b < 20)
            return black / total
        bf = max(black_fraction(left), black_fraction(right), black_fraction(top), black_fraction(bottom))
        if bf > 0.2:
            flags.append((p.name, round(bf, 3)))
    except Exception as e:
        print('err', p, e)

print('flagged', len(flags))
for name, frac in flags:
    print(name, frac)
