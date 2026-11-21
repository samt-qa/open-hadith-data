"""معرّفات ثابتة لسجلات الأحاديث، مشتركة بين التصدير والفهارس.

المعرّف: "<collection>:<n>" حيث n أول رقم مطبوع للحديث.
- إن تكرر الرقم نفسه في الكتاب: الأول "<col>:<n>"، والتالي "<col>:<n>.2" ثم ".3"…
- إن لم يكن للحديث رقم: "<col>:u<seq>".
الترتيب ترتيب الملف (seq)، فالمعرّف ثابت ما دام الاستخراج ثابتًا (يحرسه tests/regression.sh).
"""
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

COLLECTIONS = [
    "bukhari", "muslim", "abudawud", "tirmidhi", "nasai", "ibnmajah", "malik", "darimi", "ahmad",
    "tabaranikabir", "tabaraniawsat", "tabaranisaghir", "tayalisi", "humaydi", "ibnjarud", "adabmufrad",
    "tahawi", "nasaikubra", "ibnabishaybah", "hakim", "daraqutni", "ibnkhuzaymah", "ibnhibban",
    "abdurrazzaq", "bayhaqi", "abuyala", "bazzar",
]


def assign_ids(records, collection):
    """يضيف الحقل "id" لكل سجل hadith (يعدّل السجلات في مكانها) ويعيدها."""
    seen = Counter()
    for r in records:
        if r.get("type") != "hadith":
            continue
        printed = (r.get("numbers") or {}).get("printed") or []
        if not printed:
            r["id"] = f"{collection}:u{r['seq']}"
            continue
        n = printed[0]
        seen[n] += 1
        r["id"] = f"{collection}:{n}" if seen[n] == 1 else f"{collection}:{n}.{seen[n]}"
    return records


def load(collection, root=ROOT):
    """يقرأ text/<col>/<col>.jsonl ويعيد السجلات كلها (لا الأحاديث وحدها) مع المعرّفات."""
    path = Path(root) / "text" / collection / f"{collection}.jsonl"
    with open(path, encoding="utf-8") as f:
        recs = [json.loads(line) for line in f]
    return assign_ids(recs, collection)
