"""فحوص ذاتية لمسند أبي يعلى (abuyala) ومسند البزار (bazzar) بعد الاستخراج.
الاستعمال: python -I check_ab_bz.py abuyala [witness-181] | bazzar"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "base" / "shamela").is_dir())
sys.stdout.reconfigure(encoding="utf-8")


def main(col, stem=None):
    path = ROOT / "text" / col / f"{stem or col}.jsonl"
    rs = [json.loads(x) for x in path.open(encoding="utf-8")]
    by = Counter(r["type"] for r in rs)
    print(path.relative_to(ROOT).as_posix(), dict(by))
    h = [r for r in rs if r["type"] == "hadith"]
    bad = Counter()
    for r in h:
        t = r["text"]
        if re.search(r"(?:^|\n)\s*[٠-٩]+\s*-\s", t):
            bad["line_start_number_in_text"] += 1
        if "حكم" in t and re.search(r"\[حكم|إسناده (?:صحيح|ضعيف|حسن)", t):
            bad["grade_in_text"] += 1
        if not t and not r.get("editor_omitted"):
            bad["empty"] += 1
        if len(t) > 6000:
            bad["very_long(>6000)"] += 1
        if len(t) < 40:
            bad["very_short(<40)"] += 1
    g = Counter(k for r in h for k in r.get("grades", {}))
    print("hadith", len(h), "grades", dict(g), "with_notes", sum(1 for r in h if r.get("notes")),
          "printed_as", sum(1 for r in h if "printed_as" in r["numbers"]),
          "unnumbered", sum(1 for r in h if r["numbers"].get("unnumbered")))
    print("suspects", dict(bad))
    oth = [r for r in rs if r["type"] == "other"]
    for r in oth[:int(sys.argv[3]) if len(sys.argv) > 3 else 8]:
        print("  other", r["source"]["entry"], r["text"][:120].replace("\n", " / "))
    lens = sorted(len(r["text"]) for r in h)
    if lens:
        print("len p50/p99/max", lens[len(lens) // 2], lens[int(len(lens) * .99)], lens[-1])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] != "-" else None)
