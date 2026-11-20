"""تنزيل كتب الشاملة من تراث (بإذن المالك، 2026-11-20).

الاستعمال:
  python scripts/fetch_turath.py core          الكتب التسعة (epub + json الخام)
  python scripts/fetch_turath.py cat 6         كل كتب تصنيف (epub فقط)، يتخطى الموجود محليًا

- الوجهة: base/shamela/<id>/<id>.epub و <id>.json ؛ لا يُعاد تنزيل ملف موجود.
- مهلة ثانية بين الطلبات، وثلاث محاولات للملف.
- كل ملف يُسجَّل في base/shamela/MANIFEST.tsv (المعرّف، الاسم، التصنيف، الحجم، sha256، التاريخ).
"""
import csv
import datetime
import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "base" / "shamela"
CATALOG = ROOT / "work" / "turath" / "data-v3.json"
INVENTORY = ROOT / "work" / "epub-inventory.tsv"
MANIFEST = DEST / "MANIFEST.tsv"
UA = {"User-Agent": "open-hadith-text-pilot"}
EPUB = "https://files.turath.io/epub/{id}.epub"
JSON = "https://files.turath.io/books-v3/{id}.json"

# الكتب التسعة وطبعاتها البديلة المهمة
CORE = {
    "1681": "bukhari", "1727": "muslim", "711": "muslim-turkiyya",
    "1726": "abudawud", "1435": "tirmidhi-shakir", "7895": "tirmidhi-bashar",
    "829": "nasai-misriyya", "1339": "nasai-risala", "1198": "ibnmajah",
    "21795": "darimi", "1699": "malik", "25794": "ahmad",
}


def fetch(url: str) -> bytes:
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            if attempt == 2:
                raise
            print("  retry", url, e, flush=True)
            time.sleep(5 * (attempt + 1))
    raise RuntimeError("unreachable")


def log(row: dict) -> None:
    new = not MANIFEST.exists()
    with MANIFEST.open("a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, ["id", "kind", "name", "cat", "bytes", "sha256", "url", "fetched_at"], delimiter="\t")
        if new:
            w.writeheader()
        w.writerow(row)


def get_one(book_id: str, kinds, books) -> None:
    b = books.get(book_id, {})
    for kind in kinds:
        out = DEST / book_id / f"{book_id}.{kind}"
        if out.exists():
            continue
        url = (EPUB if kind == "epub" else JSON).format(id=book_id)
        try:
            data = fetch(url)
        except Exception as e:  # noqa: BLE001
            print(f"FAIL {book_id} {kind}: {e}", flush=True)
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        log({"id": book_id, "kind": kind, "name": b.get("name", ""), "cat": b.get("cat_id", ""),
             "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "url": url,
             "fetched_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds")})
        print(f"ok {book_id} {kind} {len(data)/1e6:.1f}MB {b.get('name', '')}", flush=True)
        time.sleep(1)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # طرفية ويندوز cp1256 لا تطبع كل الحروف
    books = json.loads(CATALOG.read_text(encoding="utf-8"))["books"]
    if sys.argv[1] == "core":
        for i in CORE:
            get_one(i, ["epub", "json"], books)
    elif sys.argv[1] == "ids":  # قائمة معرّفات بعينها: epub + json
        for i in sys.argv[2:]:
            get_one(i, ["epub", "json"], books)
    elif sys.argv[1] == "cat":
        cats = json.loads(CATALOG.read_text(encoding="utf-8"))["cats"]
        local = set()
        if INVENTORY.exists():
            local = {r["shamela_id"] for r in csv.DictReader(INVENTORY.open(encoding="utf-8-sig"), delimiter="\t")}
        ids = [str(i) for c in sys.argv[2:] for i in cats[c]["books"]]
        todo = [i for i in ids if i not in local]
        print(f"{len(ids)} in categories, {len(ids) - len(todo)} already local, {len(todo)} to fetch", flush=True)
        for n, i in enumerate(todo, 1):
            get_one(i, ["epub"], books)
            if n % 50 == 0:
                print(f"-- {n}/{len(todo)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
