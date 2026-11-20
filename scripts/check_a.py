"""الخطوة 1: فحص سلامة الشاهد A مقابل القيم المتوقعة في القسم 3 من الوثيقة.

يطبع أعدادًا فقط، ولا يطبع شيئًا من نصوص الأحاديث (حفاظًا على القراءة العمياء).
"""
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "base" / "fawazahmed0" / "ara-bukhari.json"

EXPECTED = {
    "records": 7589,
    "sections": 98,
    "with_tashkeel": 7580,
    "empty_text": 9,
    "min_number": 1,
    "max_number": 7563,
    "fractional_numbers": 26,
}


def has_tashkeel(s: str) -> bool:
    return any("ً" <= c <= "ْ" for c in s)


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    doc = json.loads(SRC.read_text(encoding="utf-8"))
    hadiths = doc["hadiths"]
    meta = doc["metadata"]
    nums = [h["hadithnumber"] for h in hadiths]
    sections = meta.get("sections", {})
    got = {
        "records": len(hadiths),
        "sections": len(sections),
        "with_tashkeel": sum(1 for h in hadiths if has_tashkeel(h.get("text", ""))),
        "empty_text": sum(1 for h in hadiths if not h.get("text", "").strip()),
        "min_number": min(nums),
        "max_number": max(nums),
        "fractional_numbers": sum(1 for n in nums if float(n) != int(n)),
    }
    ok = True
    for k, exp in EXPECTED.items():
        mark = "OK " if got[k] == exp else "DIFF"
        ok &= got[k] == exp
        print(f"{mark} {k}: got={got[k]} expected={exp}")
    print("top-level keys:", sorted(doc.keys()))
    print("metadata keys:", sorted(meta.keys()))
    print("hadith keys:", sorted(hadiths[0].keys()))
    print("empty-text numbers:", [h["hadithnumber"] for h in hadiths if not h.get("text", "").strip()])
    print("RESULT:", "all expected values match" if ok else "SOURCE DIFFERS FROM SPEC - record in report")
    return 0


if __name__ == "__main__":
    sys.exit(main())
