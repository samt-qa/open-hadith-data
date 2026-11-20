"""مقابلة الطبعة الأساس بطبعة شاملة ثانية (الشاهد الثاني).

الاستعمال: python -I scripts/compare_witness.py <collection> <witness_shamela_id> [--whole] [--no-key] [--base-range=LO-HI]

المدخلات:
  text/<c>/<c>.jsonl            الأساس (B)
  text/<c>/witness-<id>.jsonl   الشاهد، مستخرَج بـ extract_shamela.py <c> <id> --witness
المخرجات (tag = W<id>):
  work/compare/<c>-W<id>.jsonl و -stats.json
  review/<c>-W<id>-queue.jsonl
  text/<c>/<c>-W<id>-variants.jsonl

يُحاذى بالمحاذاة نفسها التي في compare_ab.py. المفتاح المشترك رقم الحديث المطبوع (أو رقم عبد الباقي في مسلم)
إلا مع --no-key (ترقيمان مختلفان: المحاذاة بالنص وحده). --whole: الكتاب كاملًا كتلةً واحدة
(يُفترض حين تختلف حدود الكتب بين الطبعتين). القاعدة: نص الأساس هو المعتمد، وقراءة الشاهد علامة.
--kitab-by-title: كتب الشاهد تُنسب إلى كتب الأساس بعناوينها (ترتيب الكتب مختلف)؛ ومع --whole يُرتَّب الشاهد بترتيب كتب الأساس.
--shingle-key: مفاتيح المراسي شرائح نصية فريدة في الطبعتين (ترقيمان مختلفان وزيادات كثيرة في الشاهد).
مثال: مصنف عبد الرزاق ← compare_witness.py abdurrazzaq 84 --whole --no-key --kitab-by-title --shingle-key
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compare_ab as C  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main(argv) -> int:
    coll, wid = argv[0], argv[1]
    whole = "--whole" in argv
    no_key = "--no-key" in argv
    base = [json.loads(x) for x in (ROOT / "text" / coll / f"{coll}.jsonl").open(encoding="utf-8")]
    wit = [json.loads(x) for x in (ROOT / "text" / coll / f"witness-{wid}.jsonl").open(encoding="utf-8")]
    rng = next((a.split("=", 1)[1] for a in argv if a.startswith("--base-range=")), None)
    if rng:
        # شاهد ناقص (مسند أحمد ت شاكر: ١–٨٧٨٢ فقط): يُقصر الأساس على ما يقابله بترتيب الملف، من أول سجل برقم lo
        # إلى آخر سجل برقم hi، لئلا يُغرق الباقي «only_in_B»
        lo, hi = map(int, rng.split("-"))
        nums = [(r.get("numbers") or {}).get("printed") or [None] for r in base]
        first = next(i for i, n in enumerate(nums) if n[0] == lo)
        last = max(i for i, n in enumerate(nums) if n[0] == hi)
        base = base[first:last + 1]
    if "--kitab-by-title" in argv:
        # ترتيب الكتب مختلف بين الطبعتين (مصنف عبد الرزاق ط التأصيل 84: الولاء قبل الأيمان، والفرائض بعد الولاء)
        # ← يُنسب كل كتاب في الشاهد إلى كتاب الأساس الذي يطابقه عنوانه (بلا رقم ولا تشكيل)، ويُقابَل كتابًا كتابًا؛
        # وما لا نظير له في الأساس (كتاب الجامع) يُعطى رقمًا فوق ١٠٠ فيبقى «only_in_A»
        norm = lambda t: re.sub(r"[ً-ْٰ\s]|[٠-٩]+\s*-", "", t or "").replace("الأولمن", "")
        bt = {r["kitab"]["n"]: norm(r["kitab"]["title"]) for r in base if r.get("kitab") and r["kitab"]["n"]}
        wt = {}
        for r in wit:
            if r.get("kitab") and r["kitab"]["n"] not in wt:
                wt[r["kitab"]["n"]] = norm(r["kitab"]["title"])
        wmap = {}
        for rule in (lambda x, t: x == t, lambda x, t: bool(x and t and (x in t or t in x))):
            for wn, t in wt.items():
                if wn not in wmap:
                    n = next((n for n, x in bt.items() if n not in wmap.values() and rule(x, t)), None)
                    if n is not None:
                        wmap[wn] = n
        for wn, t in wt.items():  # «كتاب العيدين» ↔ «كتاب صلاة العيدين»: أقرب عنوان لم يُنسب بعد
            if wn not in wmap:
                best = max(((C.sim(x, t), n) for n, x in bt.items() if n not in wmap.values()), default=(0, None))
                wmap[wn] = best[1] if best[0] >= 0.8 else 100 + wn
        for r in wit:
            if r.get("kitab"):
                r["kitab"] = dict(r["kitab"], n=wmap.get(r["kitab"]["n"], r["kitab"]["n"]))
        print("kitab map (witness → base):", json.dumps(wmap), file=sys.stderr)
    B = C.shamela_items(coll, base, no_key=no_key)
    A = C.shamela_items(coll, wit, no_key=no_key)
    if "--shingle-key" in argv:
        # ترقيمان مختلفان وفي الشاهد زيادات كثيرة (التأصيل: «المناسك الكبير» ~ألف رواية) ← مراسٍ بالنص:
        # مفتاح كل حديث شرائح من ست كلمات (هيكل الحروف) لا تقع إلا مرة واحدة في كل طبعة، ثم LIS كالمعتاد
        def shingles(x):
            s = x["skel"]
            return {" ".join(s[i:i + 6]) for i in range(max(0, len(s) - 5))}
        ca, cb = Counter(), Counter()
        for side, cnt in ((A, ca), (B, cb)):
            for k in side:
                for x in side[k]:
                    cnt.update(shingles(x))
        for side in (A, B):
            for k in side:
                for x in side[k]:
                    x["key"] = {h for h in shingles(x) if ca[h] == 1 and cb[h] == 1}
    # --key-from <حقل>: مفتاح الشاهد من حقل فيه يحمل رقم الأساس، لا من رقمه المطبوع
    # (الدارمي 36114: concordance.د = رقم طبعة الداراني = ت حسين أسد، الأساس)
    key_from = argv[argv.index("--key-from") + 1] if "--key-from" in argv else None
    by_seq = {r["seq"]: r for r in wit}
    for k in A:  # ترتيب الشاهد في ملفه (لا برقمه) عند المحاذاة كاملًا
        for x in A[k]:
            # مع --kitab-by-title: بترتيب كتب الأساس ثم ترتيب الشاهد في ملفه (حدود الكتب المتجاورة قد تختلف بينهما)
            x["order"] = (x["book"], x["seq"]) if "--kitab-by-title" in argv else x["seq"]
            if key_from:
                field, sig = key_from.split(".")
                x["key"] = {c[sig] for c in by_seq[x["seq"]].get(field, []) if sig in c}
            if "--order-by-key" in argv:
                # شاهد بترتيب مختلف (ابن حبان 537 «التقاسيم» مقابل «الإحسان» 1729): يُرتَّب بمفتاحه = رقم الأساس
                x["order"] = min(x["key"]) if x.get("key") else 10 ** 9 + x["seq"]
    if "--text-key" in argv:
        # --text-key (مع --no-key): لا رقم مشترك، فمفتاح المرساة بصمةُ النص: أول عشر كلمات (هيكلًا) بعد حذف
        # صيغ التحديث وكنية المصنف («حدثنا أبو بكر قال: نا…» تختلف بين الطبعتين)، إن تفرّدت في الطرفين.
        # بلا مراسٍ تضلّ المحاذاة الجشعة عند فجوة أوسع من نافذتها (مصنف ابن أبي شيبة: الشثري 333 / الحوت 9944)
        stop = {"حدثنا", "نا", "ثنا", "اخبرنا", "أخبرنا", "انا", "أنا", "قال", "ابو", "أبو", "بكر"}

        def sig(x):
            words = [s for s in x["skel"] if s not in stop]
            return " ".join(words[:10]) if len(words) >= 6 else None
        for side in (A, B):
            cnt = Counter(sig(x) for k in side for x in side[k])
            for k in side:
                for x in side[k]:
                    s = sig(x)
                    x["sig"] = s if s and cnt[s] == 1 else None
        sa = {x["sig"] for k in A for x in A[k] if x["sig"]}
        sb = {x["sig"] for k in B for x in B[k] if x["sig"]}
        for side in (A, B):
            for k in side:
                for x in side[k]:
                    x["key"] = {x["sig"]} if x["sig"] in sa and x["sig"] in sb else set()
    a_empty = [r["numbers"].get("printed") for r in wit if r["type"] == "hadith" and not r["text"]]
    return C.run(coll, A, B, a_empty, tag=f"W{wid}", witness=f"shamela-{wid}",
                 whole_book=whole, allah_flag=False, decision=C.WITNESS_DECISION)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
