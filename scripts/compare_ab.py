"""مقابلة نص الشاملة المستخرج (B) بالمصدر المفتوح fawazahmed0 (A) آليًا.

الاستعمال: python scripts/compare_ab.py bukhari

- المحاذاة بالمحتوى داخل كل كتاب، لا بالرقم وحده، لأن تقسيم الأحاديث يختلف بين المصدرين:
  يُسمح بأن يقابل حديثٌ في أحدهما حديثين أو أكثر في الآخر، وبحديث بلا نظير.
- التصنيف بمستويات القسم 7 (دالة compare في align.py): L1 مسافات وصيغ صلاة، L2 إملاء،
  L3 تشكيل، L4 فرق في الحروف/الكلمات، L5 بلا نظير.
- لا يُحسم شيء: فروق L4 وL5 تذهب إلى review/<collection>-AB-queue.jsonl ليقضي فيها المالك.
- المخرجات: work/compare/<collection>-AB.jsonl (سطر لكل مجموعة متقابلة)، و-stats.json.
"""
import difflib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import textkeys as K  # noqa: E402
from align import compare  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
A_FILES = {"bukhari": "ara-bukhari.json", "muslim": "ara-muslim.json", "abudawud": "ara-abudawud.json",
           "tirmidhi": "ara-tirmidhi.json", "nasai": "ara-nasai.json", "malik": "ara-malik.json",
           "ibnmajah": "ara-ibnmajah.json"}
# كتب لا تتطابق حدود كتبها بين المصدرين (مسلم: A يفرد الكسوف والمساقاة؛ أبو داود: الشاملة تفرد «تفريع الأبواب»)
# فتُحاذى كاملةً كتلةً واحدة
WHOLE_BOOK = {"muslim", "abudawud", "tirmidhi", "nasai", "ibnmajah"}
# كتب لا رقم مشترك فيها بين المصدرين: الموطأ (A يرقّم تسلسليًّا ويعدّ ما لم يرقّمه عبد الباقي، وB برقم عبد الباقي في كل كتاب)
# ← تُحاذى بالنص وحده داخل كل كتاب
NO_KEY = {"malik"}
# ملفات شاملة ثبت فيها سقوط لفظ الجلالة من النص (تحقق 2026-11-20: أبو داود 1726 «رَسُولُ صَلَّى عَلَيْهِ وَسَلَّمَ»)
ALLAH_DEFECT = {"abudawud"}
REPAIR_WINDOW = 40  # الجولة الثانية لا تزوّج إلا ما تقارب موضعه
GOOD, MERGE_MIN, SKIP_MIN = 0.85, 0.6, 0.75
MAXN = 4
LOOKAHEAD = 30  # أقصى تخطٍّ للبحث عن نظير حين ينفرد أحد المصدرين بأحاديث متتالية
DECISION = {"keep": "B", "by": "owner", "date": "2026-11-20",
            "rule": "نص الشاملة هو المعتمد؛ قراءة A تُحفظ علامةً على موضع الخلاف"}
WITNESS_DECISION = {"keep": "B", "by": "owner", "date": "2026-11-20",
                    "rule": "نص الطبعة الأساس هو المعتمد؛ قراءة الطبعة الشاهدة تُحفظ علامةً على موضع الخلاف"}
# تصحيحات «الله» التي نقضها الشاهد الثاني (ت الأرنؤوط 117359 يوافق الشاملة: اسم لا سقوط) ← تبقى على نص الشاملة
# قرار المالك 2026-11-20 (موافقته على توصيات الشواهد الثانية)
OVERRULED = {"abudawud": {489, 684, 2193, 2398}}
OVERRULED_DECISION = {"keep": "B", "by": "owner", "date": "2026-11-20",
                      "rule": "نقضه الشاهد الثاني (ت الأرنؤوط 117359): يوافق نص الشاملة، فليس سقوطًا"}
OWNER_A = {"keep": "A", "by": "owner", "date": "2026-11-20",
           "rule": "سقوط لفظ الجلالة من ملف الشاملة: تُؤخذ قراءة A"}


def sim(a, b):
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def cat(items):
    return [s for it in items for s in it["skel"]]


def anchors(A, B):
    """مراسٍ: أزواج تشترك في الرقم (key) ويتشابه نصها، ثم أطول سلسلة متزايدة في الطرفين (LIS)."""
    pos = defaultdict(list)
    for i, a in enumerate(A):
        for k in a["key"]:
            pos[k].append(i)
    cand = []
    for j, b in enumerate(B):
        ids = sorted({i for k in b["key"] for i in pos.get(k, [])})[:8]
        if ids:
            s, i = max((sim(A[i]["skel"], b["skel"]), i) for i in ids)
            if s >= GOOD:
                cand.append((j, i))
    # LIS على i بترتيب j (تزايد صارم في الطرفين)
    import bisect
    tails, tail_idx, prev = [], [], [None] * len(cand)
    for n, (j, i) in enumerate(cand):
        p = bisect.bisect_left(tails, i)
        if p == len(tails):
            tails.append(i); tail_idx.append(n)
        else:
            tails[p] = i; tail_idx[p] = n
        prev[n] = tail_idx[p - 1] if p else None
    chain, n = [], tail_idx[-1] if tail_idx else None
    while n is not None:
        chain.append(cand[n]); n = prev[n]
    return [(i, j) for j, i in reversed(chain)]


def align_block(A, B):
    """محاذاة بالمراسي ثم جشعة بين كل مرساتين، ثم جولة إصلاح."""
    cuts = [(0, 0)] + [(i, j) for i, j in anchors(A, B) if (i, j) != (0, 0)] + [(len(A), len(B))]
    out = []
    for (i1, j1), (i2, j2) in zip(cuts, cuts[1:]):
        out.extend(greedy(A[i1:i2], B[j1:j2]))
    return repair(attach(out))


def attach(groups):
    """سجل بلا نظير يشترك في الرقم مع المجموعة المجاورة (رقم فرعي «م»، أو تتمة حديث مقسوم) يُضم إليها."""
    def keys(items):
        return set().union(*(x["key"] for x in items)) if items else set()
    out = []
    for g in groups:
        ga, gb, s = g[:3]
        if out and (not ga or not gb):
            pa, pb = out[-1][0], out[-1][1]
            single = ga or gb
            if pa and pb and keys(single) & (keys(pa) | keys(pb)):
                na, nb = pa + ga, pb + gb
                out[-1] = (na, nb, sim(cat(na), cat(nb)))
                continue
        out.append(g)
    # والعكس: سجل بلا نظير يسبق مجموعةً يشترك معها في الرقم
    res = []
    for g in reversed(out):
        ga, gb, s = g[:3]
        if res and (not ga or not gb):
            na_, nb_ = res[-1][0], res[-1][1]
            if na_ and nb_ and keys(ga or gb) & (keys(na_) | keys(nb_)):
                na, nb = ga + na_, gb + nb_
                res[-1] = (na, nb, sim(cat(na), cat(nb)))
                continue
        res.append(g)
    return list(reversed(res))


def greedy(A, B):
    """محاذاة جشعة رتيبة لقائمتين (كل عنصر له skel). يعيد [(قائمة A، قائمة B، النسبة)]."""
    out, i, j = [], 0, 0
    while i < len(A) or j < len(B):
        if i >= len(A):
            out.append(([], [B[j]], 0.0)); j += 1; continue
        if j >= len(B):
            out.append(([A[i]], [], 0.0)); i += 1; continue
        s11 = sim(A[i]["skel"], B[j]["skel"])
        if s11 >= GOOD:
            out.append(([A[i]], [B[j]], s11)); i += 1; j += 1; continue
        best = (s11, 1, 1)
        for n in range(2, MAXN + 1):
            if i + n <= len(A):
                s = sim(cat(A[i:i + n]), B[j]["skel"])
                if s > best[0]:
                    best = (s, n, 1)
            if j + n <= len(B):
                s = sim(A[i]["skel"], cat(B[j:j + n]))
                if s > best[0]:
                    best = (s, 1, n)
        s, na, nb = best
        if (na, nb) != (1, 1) and s >= MERGE_MIN and s > s11 + 0.05:
            out.append((A[i:i + na], B[j:j + nb], s)); i += na; j += nb; continue
        if s11 < MERGE_MIN:
            # بلا نظير؟ يُبحث عن نظير الحالي في الآخر ضمن نافذة، ويُتخطى الأقرب
            ka = next((k for k in range(1, LOOKAHEAD) if i + k < len(A)
                       and sim(A[i + k]["skel"], B[j]["skel"]) >= SKIP_MIN), None)
            kb = next((k for k in range(1, LOOKAHEAD) if j + k < len(B)
                       and sim(A[i]["skel"], B[j + k]["skel"]) >= SKIP_MIN), None)
            if ka or kb:
                if kb is None or (ka is not None and ka <= kb):
                    out.extend(([x], [], 0.0) for x in A[i:i + ka]); i += ka
                else:
                    out.extend(([], [x], 0.0) for x in B[j:j + kb]); j += kb
                continue
        out.append(([A[i]], [B[j]], s11)); i += 1; j += 1
    return out


def repair(groups):
    """جولة ثانية: ما بقي ضعيفًا أو بلا نظير (لاختلاف ترتيب الأحاديث بين المصدرين)
    يُعاد تزويجه بأفضل تطابق في المحتوى داخل الكتاب، بلا اشتراط الترتيب."""
    weak = [k for k, (ga, gb, s) in enumerate(groups) if s < MERGE_MIN]
    pa = [x for k in weak for x in groups[k][0]]
    pb = [x for k in weak for x in groups[k][1]]
    if not pa or not pb:
        return groups
    cand = sorted(((sim(a["skel"], b["skel"]), ia, ib) for ia, a in enumerate(pa) for ib, b in enumerate(pb)
                   if abs(ia - ib) <= REPAIR_WINDOW), key=lambda t: -t[0])
    ua, ub, pairs = set(), set(), []
    for s, ia, ib in cand:
        if s < MERGE_MIN:
            break
        if ia not in ua and ib not in ub:
            ua.add(ia); ub.add(ib); pairs.append(([pa[ia]], [pb[ib]], s, True))
    # ما بقي ويحمل الرقم نفسه في الطرفين يُقرن ضعيفًا (اختلاف تقسيم أو نص) ليراه المالك
    for ia, a in enumerate(pa):
        if ia in ua:
            continue
        for ib, b in enumerate(pb):
            if ib not in ub and a["key"] & b["key"] and abs(ia - ib) <= REPAIR_WINDOW:
                ua.add(ia); ub.add(ib)
                pairs.append(([a], [b], sim(a["skel"], b["skel"]), True))
                break
    keep = [g for k, g in enumerate(groups) if k not in set(weak)]
    rest = [([a], [], 0.0) for ia, a in enumerate(pa) if ia not in ua] + \
           [([], [b], 0.0) for ib, b in enumerate(pb) if ib not in ub]
    return keep + pairs + rest


def main(coll: str) -> int:
    a_json = json.loads((ROOT / "base" / "fawazahmed0" / A_FILES[coll]).read_text(encoding="utf-8"))
    recs = [json.loads(x) for x in (ROOT / "text" / coll / f"{coll}.jsonl").open(encoding="utf-8")]

    A, B = defaultdict(list), defaultdict(list)
    a_empty = []
    # بعض سجلات A مرجعها الكتاب 0؛ يُنسب كل سجل إلى كتابه بنطاقات الأرقام في section_details
    ranges = sorted((d["hadithnumber_first"], int(b)) for b, d in a_json["metadata"]["section_details"].items()
                    if int(b) > 0)

    def book_of(n):
        bk = ranges[0][1]
        for first, b in ranges:
            if n >= first:
                bk = b
        return bk

    for h in sorted(a_json["hadiths"], key=lambda h: h["hadithnumber"]):
        if not h["text"].strip():
            a_empty.append(h["hadithnumber"]); continue
        toks = K.tokens(h["text"])
        lst = A[book_of(h["hadithnumber"])]
        sk = [t["skel"] for t in toks]
        # A يكرر النص نفسه تحت كل رقم من أرقام الحديث المتعدد الأرقام: يُضم إلى سجل واحد
        # key: الرقم المشترك بين المصدرين (البخاري: الرقم نفسه؛ مسلم: رقم عبد الباقي في arabicnumber)
        if coll == "muslim":
            key = {int(float(h["arabicnumber"]))} if h.get("arabicnumber") else set()
        elif coll in NO_KEY:
            key = set()
        else:
            key = {h["hadithnumber"]}
        if lst and lst[-1]["skel"] == sk:
            lst[-1]["n"].append(h["hadithnumber"]); lst[-1]["key"] |= key; continue
        lst.append({"n": [h["hadithnumber"]], "key": key, "book": book_of(h["hadithnumber"]),
                    "text": h["text"], "tokens": toks, "skel": sk})
    B = shamela_items(coll, recs)
    return run(coll, A, B, a_empty, tag="AB", witness="fawazahmed0")


def shamela_items(coll, recs, no_key=None):
    """سجلات الحديث من مستخرَج الشاملة، مقسومة على الكتب: {رقم الكتاب: [عنصر]}."""
    no_key = coll in NO_KEY if no_key is None else no_key
    B = defaultdict(list)
    for r in recs:
        if r["type"] != "hadith" or r.get("editor_omitted"):  # ما أخرجه المحقق إلى الحاشية لا يُقابَل
            continue
        btext = r.get("text_source", r["text"])  # بعد apply_decisions: يُقابَل نص الشاملة الأصلي
        toks = K.tokens(btext)
        nb = r["numbers"]
        if "abd_al_baqi" in nb:  # مسلم: يُعرض رقم عبد الباقي ويُقابَل به
            disp, key = [nb["abd_al_baqi"]], {int(x) for x in nb["abd_al_baqi"].split("/")}
        else:
            disp, key = nb["printed"], set(nb["printed"]) if not no_key else set()
        B[r["kitab"]["n"]].append({"n": disp, "key": key, "book": r["kitab"]["n"], "seq": r["seq"],
                                   "text": btext, "tokens": toks, "skel": [t["skel"] for t in toks],
                                   "loc": r["loc"]})
    return B


def run(coll, A, B, a_empty, tag, witness, whole_book=None, allah_flag=True, decision=None):
    """يحاذي الشاهد A بالأساس B ويكتب المخرجات. tag: «AB» لـ fawazahmed0، و«W<id>» لطبعة شاملة ثانية."""
    whole_book = coll in WHOLE_BOOK if whole_book is None else whole_book
    if whole_book:
        # بترتيب رقم A لا بكتبه (section_details في A مسلم خاطئة أحيانًا: الكتاب 16 يبدأ عندها من 388)
        A = {0: sorted((x for b in A for x in A[b]), key=lambda x: x["order"] if "order" in x else x["n"][0])}  # order: ترتيب الشاهد الثاني في ملفه
        B = {0: [x for b in sorted(B) for x in B[b]]}

    out_dir = ROOT / "work" / "compare"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows, queue, st = [], [], Counter()
    for book in sorted(set(A) | set(B)):
        for g in align_block(A.get(book, []), B.get(book, [])):
            ga, gb, score = g[:3]
            reordered = len(g) > 3
            a_nums = [n for x in ga for n in x["n"]]
            b_nums = [n for x in gb for n in x["n"]]
            kb = gb[0]["book"] if gb else ga[0]["book"]
            gid = f"{coll}-k{kb:02d}-" + ("A" + "+".join(map(str, a_nums)) if ga else "Bseq" + str(gb[0]["seq"]))
            shape = f"{len(ga)}:{len(gb)}"
            st["groups_" + shape if shape in ("1:1", "1:0", "0:1") else "groups_merged"] += 1
            book = kb
            row = {"id": gid, "kitab": book, "A": a_nums, "B": b_nums, "B_seq": [x["seq"] for x in gb],
                   "loc": gb[0]["loc"] if gb else None, "shape": shape, "score": round(score, 4)}
            if reordered:
                row["reordered"] = True
                st["groups_reordered"] += 1
            if not ga or not gb:
                row["level"] = "L5"
                side = "A" if ga else "B"
                txt = (ga or gb)[0]["text"]
                queue.append({"diff_id": gid + "-d01", "level": "L5", "kind": f"only_in_{side}", "kitab": book,
                              "A_numbers": a_nums, "B_numbers": b_nums, "loc": row["loc"],
                              "text_start": txt[:160]})
                st["L5_only_in_" + side] += 1
                rows.append(row)
                continue
            a_text = " ".join(x["text"] for x in ga)
            u = {"tokens": [t for x in gb for t in x["tokens"]], "text": " ".join(x["text"] for x in gb)}
            diffs, top, cnt, ta = compare(a_text, u)
            row["level"] = top
            row["counts"] = {k: v for k, v in cnt.items() if v}
            if score < MERGE_MIN:
                # تقسيم أو نص مختلف تحت الرقم نفسه: بند واحد للمالك بدل عشرات الفروق
                row["low_score"] = True
                row["level"] = "L5"
                st["low_score_groups"] += 1
                queue.append({"diff_id": gid + "-d01", "level": "L5", "kind": "segmentation_mismatch",
                              "kitab": book, "A_numbers": a_nums, "B_numbers": b_nums, "loc": row["loc"],
                              "score": round(score, 4), "A_start": a_text[:160], "B_start": u["text"][:160],
                              "decision": None})
                rows.append(row)
                continue
            st["level_" + top] += 1
            st.update({k: v for k, v in cnt.items()})
            k = 0
            for d in diffs:
                if d["level"] != "L4":
                    continue
                k += 1
                (i1, i2), (j1, j2) = d["i"], d["j"]
                kind = d["kind"].replace("_in_P", "_in_B")
                queue.append({"diff_id": f"{gid}-d{k:02d}", "level": "L4", "kind": kind, "kitab": book,
                              "A_numbers": a_nums, "B_numbers": b_nums, "loc": row["loc"],
                              "context_before": " ".join(t["raw"] for t in u["tokens"][max(0, j1 - 6):j1]),
                              "readings": {"A": " ".join(t["raw"] for t in ta[i1:i2]),
                                           "B": " ".join(t["raw"] for t in u["tokens"][j1:j2])},
                              "context_after": " ".join(t["raw"] for t in u["tokens"][j2:j2 + 4]),
                              "decision": None})
            rows.append(row)

    with (out_dir / f"{coll}-{tag}.jsonl").open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    # قرار المالك (2026-11-20): نص الشاملة (B) هو المعتمد، وتُعلَّم مواضع خلاف A فقط
    by_gid = {r["id"]: r for r in rows}
    for q in queue:
        q["B_seq"] = by_gid[q["diff_id"].rsplit("-d", 1)[0]]["B_seq"]
        q["decision"] = decision or DECISION
        # عيب معروف في بعض ملفات الشاملة (أبو داود 1726): سقوط لفظ الجلالة من النص نفسه.
        # يُوسم ولا يُحسم آليًا لـ B؛ ينتظر قرار المالك
        # الوسم فقط إن كان الفرق كله لفظ الجلالة: بحذفه من الطرفين يتطابقان (لا «رسول الله»/«النبي»)
        rd = q.get("readings")
        if allah_flag and coll in ALLAH_DEFECT and rd:
            wa = [K.skel(K.PUNCT.sub("", w)) for w in rd["A"].split()]
            wb = [K.skel(K.PUNCT.sub("", w)) for w in rd["B"].split()]
            if wa.count("الله") > wb.count("الله") and \
                    [w for w in wa if w != "الله"] == [w for w in wb if w != "الله"]:
                q["flag"] = "B_missing_allah"
                q["decision"] = OWNER_A
                if set(q["B_numbers"]) & OVERRULED.get(coll, set()):
                    q["decision"] = OVERRULED_DECISION
                st["flag_B_missing_allah"] += 1
    with (ROOT / "review" / f"{coll}-{tag}-queue.jsonl").open("w", encoding="utf-8") as fh:
        for q in queue:
            fh.write(json.dumps(q, ensure_ascii=False) + "\n")
    # ملف الخلافات بجوار النص: سطر لكل حديث في B فيه خلاف حروف مع A (أو لا نظير له)
    var = defaultdict(list)
    for q in queue:
        v = {k: q[k] for k in ("level", "kind", "A_numbers", "readings", "context_before", "context_after",
                               "score", "A_start", "text_start") if k in q}
        for s in q["B_seq"] or [None]:
            var[s].append(v)
    vname = f"{coll}-A-variants.jsonl" if tag == "AB" else f"{coll}-{tag}-variants.jsonl"
    with (ROOT / "text" / coll / vname).open("w", encoding="utf-8") as fh:
        for s in sorted(var, key=lambda x: (x is None, x or 0)):
            fh.write(json.dumps({"B_seq": s, "witness": witness, "variants": var[s]}, ensure_ascii=False) + "\n")
    stats = {"A_records": sum(len(v) for v in A.values()), "A_empty_text": a_empty,
             "B_hadith_records": sum(len(v) for v in B.values()), "groups": len(rows),
             "queue_items": len(queue), "queue_by_kind": dict(Counter(q["kind"] for q in queue)),
             "groups_with_L4": sum(1 for r in rows if r["level"] == "L4"),
             **dict(sorted(st.items()))}
    (out_dir / f"{coll}-{tag}-stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
