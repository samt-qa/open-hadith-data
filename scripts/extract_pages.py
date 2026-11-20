"""الخطوة 3: استخراج صور الصفحات من مصوّرة PDF بالمكتبة القياسية فقط.

المصوّرة تخزّن كل صفحة صورة JPEG واحدة (DCTDecode)، فنستخرج بايتات الصورة الأصلية
كما هي بلا إعادة ضغط ولا تكبير. هذا أوثق من pdftoppm -r 300 لأن دقة المسح الأصلية
نحو 200 نقطة في البوصة، والتكبير لا يضيف معلومة.

الاستعمال: python scripts/extract_pages.py sources/bukhari/sultaniyya/j01.pdf work/pages/bukhari/j01
الملفات تُسمّى بترتيبها في PDF: i001.jpg ... ويُكتب manifest.json فيه sha256 والأبعاد.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

OBJ = re.compile(rb"(\d+) 0 obj\s*<<([^<>]*?/Subtype\s*/Image[^<>]*?)>>\s*stream\r?\n", re.S)


def main(pdf: str, out: str) -> int:
    data = Path(pdf).read_bytes()
    outdir = Path(out)
    outdir.mkdir(parents=True, exist_ok=True)
    # ترتيب الصفحات: كل كائن صفحة يشير إلى صورته في /XObject
    page_imgs = []
    for m in re.finditer(rb"<<[^<>]*?/Type\s*/Page\b(?!s)(.*?)endobj", data, re.S):
        refs = re.findall(rb"/XObject\s*<<\s*/\w+\s+(\d+) 0 R\s*>>", m.group(0))
        page_imgs.append(int(refs[0]) if len(refs) == 1 else None)
    images = {}
    for m in OBJ.finditer(data):
        d = m.group(2)
        if b"/DCTDecode" not in d:
            continue
        length = int(re.search(rb"/Length (\d+)", d).group(1))
        images[int(m.group(1))] = {
            "bytes": data[m.end(): m.end() + length],
            "width": int(re.search(rb"/Width (\d+)", d).group(1)),
            "height": int(re.search(rb"/Height (\d+)", d).group(1)),
        }
    by_file_order = list(images)
    if page_imgs and all(page_imgs) and len(page_imgs) == len(images):
        order, how = page_imgs, "page-objects"
    else:
        order, how = by_file_order, "file-order (page objects not resolved)"
    manifest = []
    for i, objnum in enumerate(order, 1):
        im = images[objnum]
        assert im["bytes"][:2] == b"\xff\xd8", f"obj {objnum} is not a JPEG"
        name = f"i{i:03d}.jpg"
        (outdir / name).write_bytes(im["bytes"])
        manifest.append({"pdf_index": i, "file": name, "width": im["width"], "height": im["height"],
                         "sha256": hashlib.sha256(im["bytes"]).hexdigest()})
    (outdir / "manifest.json").write_text(json.dumps(
        {"pdf": pdf, "pdf_sha256": hashlib.sha256(data).hexdigest(), "order_from": how, "pages": manifest},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(len(manifest), "pages;", "order:", how, "; same as file order:", order == by_file_order)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
