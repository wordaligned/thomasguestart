#!/usr/bin/env python3
from pathlib import Path
import re
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
POSTS_DIR = ROOT / 'posts'
IMAGES_DIR = ROOT.parent / 'images'
WATERMARK_DIR = IMAGES_DIR / 'watermarked'
SEPARATOR_RE = re.compile(r"^-{5,}\s*$", re.MULTILINE)
INLINE_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(/images/([^)]+)\)")

posts = []
for path in sorted(POSTS_DIR.iterdir()):
    if not path.is_file():
        continue
    if path.name.endswith("~"):
        continue
    slug = path.name
    raw = path.read_text(encoding='utf-8')
    # parse header
    lines = raw.splitlines()
    separator_index = None
    header = {}
    for i, line in enumerate(lines):
        if SEPARATOR_RE.match(line):
            separator_index = i
            break
        if ':' in line:
            k, v = line.split(':', 1)
            header[k.strip().lower()] = v.strip()
    if separator_index is None:
        continue
    body_md = "\n".join(lines[separator_index+1:])
    images = []
    hero = f"{slug}.jpg"
    images.append(hero)
    for m in INLINE_IMAGE_RE.findall(body_md):
        if m not in images:
            images.append(m)
    posts.append((slug, images))

problems = []

for slug, images in posts:
    sizes = []
    for img in images:
        # prefer watermarked
        wpath = WATERMARK_DIR / img
        if wpath.exists():
            p = wpath
        else:
            p = IMAGES_DIR / img
        if not p.exists():
            sizes.append((img, None))
            continue
        try:
            with Image.open(p) as im:
                sizes.append((img, im.size))
        except Exception as e:
            sizes.append((img, f"error: {e}"))
    # determine aspect ratios
    numeric = [s for s in sizes if isinstance(s[1], tuple)]
    ratios = []
    for _, (w,h) in numeric:
        ratios.append(round(w/ h if h else 0, 3))
    ok = True
    if len(ratios) > 1:
        first = ratios[0]
        for r in ratios[1:]:
            if abs(r - first) > 0.01:
                ok = False
                break
    elif len(ratios) <= 1:
        ok = True
    if not ok:
        problems.append((slug, sizes))

# report
print(f"Checked {len(posts)} post(s). Found {len(problems)} post(s) with mismatched aspect ratios.")
for slug, sizes in problems:
    print(f"\nPost: {slug}")
    for img, size in sizes:
        print(f"  {img}: {size}")
