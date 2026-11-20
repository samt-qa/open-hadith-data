"""قصاصات أفقية من إطار المتن لتسهيل القراءة (ملفات عمل، لا تدخل المستودع).

يحتاج Pillow (حزمة خارجية، مستعملة هنا لملفات العمل فقط؛ انظر التقرير).
الاستعمال: python scripts/make_strips.py 6 25
المخرج: work/pages/bukhari/j01/strips/p0006_s01.png ... مكبّرة 1.5 مرة.
"""
import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
PAGES = ROOT / "work" / "pages" / "bukhari" / "j01"
OUT = PAGES / "strips"
STRIP_H, OVERLAP, SCALE = 440, 110, 1.5


def frame(im, page):
    """إطار المتن ثابت الموضع في المصوّرة بحسب زوجية الصفحة (قيس على ص 6-25 من الجزء الأول)."""
    return (340, 150, 1420, 1960) if page % 2 == 0 else (290, 150, 1375, 1960)


def main(first: int, last: int) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    index = {}
    for p in range(first, last + 1):
        im = Image.open(PAGES / f"i{p:03d}.jpg")
        x0, y0, x1, y1 = frame(im, p)
        y, n, names = y0, 0, []
        while y < y1 - OVERLAP:
            n += 1
            box = (x0, y, x1, min(y1, y + STRIP_H))
            s = im.crop(box)
            s = s.resize((int(s.width * SCALE), int(s.height * SCALE)), Image.LANCZOS)
            name = f"p{p:04d}_s{n:02d}.png"
            s.save(OUT / name)
            names.append({"file": name, "box": box})
            y += STRIP_H - OVERLAP
        index[p] = {"frame": [x0, y0, x1, y1], "strips": names}
        print(p, "frame", (x0, y0, x1, y1), "strips", n)
    (OUT / "index.json").write_text(json.dumps(index, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(int(sys.argv[1]), int(sys.argv[2])))
