"""الخطوة 1: تنزيل الشاهد A (fawazahmed0/hadith-api) وتسجيل الإصدار.

الاستعمال: python scripts/fetch_a.py [bukhari|muslim|abudawud|...]   (الافتراضي bukhari)
لا يعيد التنزيل إن وُجد الملف (base/ للقراءة فقط بعد دخول الملف).
يطبع: معرّف commit للفرع 1، و sha256، والحجم.
"""
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
URL = "https://raw.githubusercontent.com/fawazahmed0/hadith-api/{ref}/editions/ara-{book}.json"
API = "https://api.github.com/repos/fawazahmed0/hadith-api/commits/1"
UA = {"User-Agent": "open-hadith-text-pilot"}


def get(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        return r.read()


def main() -> int:
    book = sys.argv[1] if len(sys.argv) > 1 else "bukhari"
    dest = ROOT / "base" / "fawazahmed0" / f"ara-{book}.json"
    commit = json.loads(get(API))["sha"]
    if dest.exists():
        data = dest.read_bytes()
        status = "exists"
    else:
        data = get(URL.format(ref=commit, book=book))  # مثبَّت على الـcommit لا على اسم الفرع
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        status = "downloaded"
    print(json.dumps({
        "book": book,
        "status": status,
        "branch_1_commit_now": commit,
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
