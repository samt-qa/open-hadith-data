"""تطبيق قرارات المالك التي تأخذ قراءة A على نص الشاملة المستخرج.

الاستعمال: python scripts/apply_decisions.py abudawud      (بعد extract_shamela ثم compare_ab)

- يقرأ review/<c>-AB-queue.jsonl ويطبّق البنود التي decision.keep = "A" فقط.
- النوع المدعوم الآن: flag = B_missing_allah (سقوط لفظ الجلالة من ملف الشاملة): يُدرج لفظ الجلالة
  كما كتبه A في موضعه من نص B، ولا يُمسّ شيء آخر (تشكيل الكلمات المجاورة يبقى كما في B).
- السجل المصحَّح: text = النص بعد التصحيح، text_source = نص الشاملة الأصلي، corrections = قائمة بما تغيّر.
  compare_ab يقابل text_source لا text، فتبقى المقابلة قابلة للإعادة.
- ما لم يُعثر على موضعه بيقين (مطابقة واحدة) لا يُطبَّق ويُذكر في الإحصاء.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import textkeys as K  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
GAP = r"[^ء-ي]{1,20}?"  # ما بين كلمتين: مسافة، ترقيم، رموز، حركات شاردة


def base(w):
    return K.skel(K.PUNCT.sub("", w))


def word_rx(w):
    return K._loose(base(w))


def locate(text, before, span, after):
    """يعيد (بداية، نهاية) للكلمات span في النص بين سياقيها، بمطابقة واحدة فقط (يُقلَّص السياق تدريجًا).
    إن كان span فارغًا فالبداية = النهاية = موضع الإدراج (بعد كلمة السياق السابقة)."""
    for nb in range(min(3, len(before)), -1, -1):
        for na in range(min(2, len(after)), -1, -1):
            if not span and (nb == 0 or nb + na < 2):
                continue  # الإدراج يحتاج سياقًا سابقًا، وكلمتين على الأقل
            pre = GAP.join(word_rx(w) for w in before[-nb:]) if nb else ""
            post = GAP.join(word_rx(w) for w in after[:na]) if na else ""
            if span:
                mid = "(" + GAP.join(word_rx(w) for w in span) + ")"
                rx = (pre + GAP if pre else "") + mid + (GAP + post if post else "")
            else:
                rx = pre + "()" + (GAP + post if post else "")
            ms = list(re.finditer(rx, text))
            if len(ms) == 1:
                return ms[0].start(1), ms[0].end(1)
    return None


def main(coll: str) -> int:
    path = ROOT / "text" / coll / f"{coll}.jsonl"
    recs = [json.loads(x) for x in path.open(encoding="utf-8")]
    by_seq = {r["seq"]: r for r in recs}
    queue = [json.loads(x) for x in (ROOT / "review" / f"{coll}-AB-queue.jsonl").open(encoding="utf-8")]
    todo = [q for q in queue if (q.get("decision") or {}).get("keep") == "A"]
    st, failed = Counter(), []
    for r in recs:  # إعادة التطبيق من نص الشاملة الأصلي دائمًا
        if "text_source" in r:
            r["text"] = r.pop("text_source")
            r.pop("corrections", None)
    for q in todo:
        if q.get("flag") != "B_missing_allah" or len(q["B_seq"]) != 1:
            st["skipped_unsupported"] += 1; failed.append(q["diff_id"]); continue
        r = by_seq[q["B_seq"][0]]
        before = q["context_before"].split()
        after = q["context_after"].split()
        span = q["readings"]["B"].split()
        hit = locate(r["text"], before, span, after)
        if not hit:
            st["not_located"] += 1; failed.append(q["diff_id"]); continue
        s, e = hit
        # بناء البديل: كلمات B كما هي، ويُدرج لفظ الجلالة من A حيث يسقط
        a_words = q["readings"]["A"].split()
        b_words = r["text"][s:e].split() if span else []
        out, k = [], 0
        for w in a_words:
            if base(w) == "الله" and not (k < len(b_words) and base(b_words[k]) == "الله"):
                out.append(w)
            elif k < len(b_words):
                out.append(b_words[k]); k += 1
        out += b_words[k:]
        new = " ".join(out)
        if not span:  # إدراج بعد كلمة السياق السابقة
            new_text = r["text"][:s] + " " + new + r["text"][s:]
            old = ""
        else:
            new_text = r["text"][:s] + new + r["text"][e:]
            old = r["text"][s:e]
        r.setdefault("text_source", r["text"])
        r.setdefault("corrections", []).append({"diff_id": q["diff_id"], "from": old, "to": new,
                                                "source": "fawazahmed0", "decision": q["decision"]})
        r["text"] = new_text
        st["applied"] += 1
    # text_source بعد text في ترتيب الحقول
    with path.open("w", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    res = {"decisions_keep_A": len(todo), **st, "failed": failed,
           "records_corrected": sum(1 for r in recs if r.get("corrections"))}
    (ROOT / "text" / coll / "apply-stats.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
