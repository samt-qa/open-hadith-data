"""جرد كتب epub التي وضعها المالك: يقرأ بطاقة كل كتاب (content.opf) فقط، لا نصّه.

المخرج: work/epub-inventory.tsv
"""
import csv
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "work" / "epub-inventory.tsv"
SKIP = {"base", "sources", "work", "review", "text", "reports", "scripts", "Docs", ".git"}


def tag(opf: str, name: str) -> str:
    m = re.search(rf"<dc:{name}[^>]*>(.*?)</dc:{name}>", opf, re.S)
    return m.group(1).strip() if m else ""


def main() -> int:
    rows = []
    for top in sorted(p for p in ROOT.iterdir() if p.is_dir() and p.name not in SKIP):
        for f in sorted(top.rglob("*.epub")):
            row = {"folder": top.name, "file": str(f.relative_to(ROOT)), "mb": f"{f.stat().st_size/1e6:.1f}"}
            try:
                with zipfile.ZipFile(f) as z:
                    names = z.namelist()
                    opfn = next(n for n in names if n.endswith(".opf"))
                    opf = z.read(opfn).decode("utf-8", "replace")
                    row["pages"] = sum(1 for n in names if "/text/" in n)
                    info = next((n for n in names if n.endswith("info.xhtml")), None)
                    row["matches_print"] = ""
                    if info:
                        row["matches_print"] = "yes" if "موافق للمطبوع" in z.read(info).decode("utf-8", "replace") else "no"
                row["shamela_id"] = tag(opf, "identifier").replace("urn:shamela:", "")
                row["title"] = tag(opf, "title")
                row["author"] = tag(opf, "creator")
                row["publisher"] = tag(opf, "publisher")
                m = re.search(r'schema:bookEdition">(.*?)<', opf)
                row["edition"] = m.group(1) if m else ""
                row["source"] = tag(opf, "source")
            except Exception as e:  # ملف تالف: يُسجَّل ولا يوقف الجرد
                row["title"] = f"ERROR: {e}"
            rows.append(row)
    cols = ["folder", "shamela_id", "title", "author", "publisher", "edition", "pages", "matches_print", "mb", "source", "file"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, cols, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(len(rows), "epubs ->", OUT.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
