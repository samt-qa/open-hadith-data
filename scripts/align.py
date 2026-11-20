"""الخطوتان 6 و7: المحاذاة بين القراءة العمياء (P) والشاهد A، ثم المقابلة وتصنيف الفروق.

المخرجات: work/align/bukhari.jsonl ، review/queue.jsonl ، work/align/stats.json
لا يحسم شيئًا: كل فرق من L2 فما فوق يذهب إلى قائمة المراجعة.
آراء الوكيل (agent_opinion) تُقرأ من review/opinions.jsonl إن وُجد وتُدمج بمعرّف الفرق.
"""
import difflib
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import textkeys as K  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
READ = ROOT / "work" / "readings" / "bukhari" / "j01"
A_FILE = ROOT / "base" / "fawazahmed0" / "ara-bukhari.json"
ALIGN = ROOT / "work" / "align" / "bukhari.jsonl"
QUEUE = ROOT / "review" / "queue.jsonl"
OPIN = ROOT / "review" / "opinions.jsonl"
STATS = ROOT / "work" / "align" / "stats.json"
FIRST, LAST = 6, 25
LINES_PER_PAGE = 25
MIN_SCORE = 0.6


def load_units():
    """يجمع مقاطع الصفحات في وحدات، ويضمّ الممتد على صفحتين."""
    units, open_unit = [], None
    for p in range(FIRST, LAST + 1):
        f = READ / f"p{p:04d}.json"
        if not f.exists():
            raise SystemExit(f"ملف القراءة ناقص: {f}")
        d = json.loads(f.read_text(encoding="utf-8"))
        ptoks = sum(len(K.tokens(s["text"])) for s in d["segments"]) or 1
        before = 0
        for s in d["segments"]:
            toks = K.tokens(s["text"])
            unc = set()
            for u in s["uncertain"]:
                a = max(0, len(K.tokens(s["text"][:u["offset"]])) - 1)
                b = len(K.tokens(s["text"][:u["offset"] + u["length"]]))
                unc.update(range(a, max(b, a + 1)))
            part = {"page": p, "seq": s["seq"], "text": s["text"], "n": len(toks), "unc": unc,
                    "n_unc": len(s["uncertain"]),
                    "frac0": before / ptoks, "frac1": (before + len(toks)) / ptoks,
                    "image": d["image"], "sha": d["image_sha256"]}
            before += len(toks)
            if s["continues_from_prev_page"] and open_unit is not None:
                open_unit["parts"].append(part)
                if open_unit["printed_number"] is None:
                    open_unit["printed_number"] = s.get("printed_number")
            else:
                open_unit = {"kind": s["kind"], "printed_number": s.get("printed_number"), "parts": [part],
                             "orphan_start": bool(s["continues_from_prev_page"])}
                units.append(open_unit)
            if not s["continues_to_next_page"]:
                open_unit = None
    for u in units:
        u["text"] = " ".join(p["text"] for p in u["parts"])
        u["tokens"] = K.tokens(u["text"])
        u["unc"], off = set(), 0
        for p in u["parts"]:
            u["unc"].update(i + off for i in p["unc"])
            off += p["n"]
    return units


def locate(u, idx):
    """موضع الكلمة رقم idx من الوحدة: جزء الصفحة ونسبة الارتفاع التقريبية."""
    off = 0
    for p in u["parts"]:
        if idx < off + p["n"] or p is u["parts"][-1]:
            frac = p["frac0"] + (p["frac1"] - p["frac0"]) * ((idx - off) / max(p["n"], 1))
            return p, min(max(frac, 0.0), 1.0)
        off += p["n"]


def ratio(a, b):
    return round(difflib.SequenceMatcher(None, a, b, autojunk=False).ratio(), 4)


def mark_name(m):
    return "+".join(K.MARK_NAMES[c] for c in sorted(m)) or "بلا حركة"


def mark_diffs(ra, rp):
    """فروق التشكيل بين كلمتين متفقتي الهيكل: (حركات مختلفة، ناقصة عند A، ناقصة عند P)."""
    la, lp = K.letters(ra), K.letters(rp)
    diff, miss_a, miss_p = [], 0, 0
    if len(la) != len(lp):
        return diff, miss_a, miss_p
    for (b, ma), (_, mp) in zip(la, lp):
        if ma == mp:
            continue
        if ma < mp:
            miss_a += 1
        elif mp < ma:
            miss_p += 1
        else:
            diff.append(f"{b}: {mark_name(ma)} (A) ↔ {mark_name(mp)} (P)")
    return diff, miss_a, miss_p


def compare(a_text, u):
    """يقابل نص A بوحدة P. يعيد (الفروق، أعلى مستوى، عدّادات، كلمات A)."""
    ta, tp = K.tokens(a_text), u["tokens"]
    sa, sp = [t["skel"] for t in ta], [t["skel"] for t in tp]
    diffs, cnt = [], Counter()
    miss = {"A": 0, "P": 0, "ex": []}

    def tash(i1, i2, j1, j2):
        ra = "".join(t["raw"] for t in ta[i1:i2])
        rp = "".join(t["raw"] for t in tp[j1:j2])
        d, ma, mp = mark_diffs(ra, rp)
        if d:
            diffs.append({"level": "L3", "kind": "tashkeel_different", "i": (i1, i2), "j": (j1, j2), "detail": d})
        if ma or mp:
            miss["A"] += ma
            miss["P"] += mp
            if len(miss["ex"]) < 12:
                miss["ex"].append({"A": " ".join(t["raw"] for t in ta[i1:i2]),
                                   "P": " ".join(t["raw"] for t in tp[j1:j2])})

    sm = difflib.SequenceMatcher(None, sa, sp, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                if not sa[i1 + k].startswith("§"):
                    tash(i1 + k, i1 + k + 1, j1 + k, j1 + k + 1)
            continue
        ja, jp = "".join(sa[i1:i2]), "".join(sp[j1:j2])
        only_hon = all(x.startswith("§") for x in sa[i1:i2] + sp[j1:j2])
        if ja == jp:
            cnt["L1_spacing"] += 1
            tash(i1, i2, j1, j2)
        elif only_hon:
            cnt["L1_honorific"] += 1
        elif K.l2_fold(ja) == K.l2_fold(jp):
            diffs.append({"level": "L2", "kind": "spelling", "i": (i1, i2), "j": (j1, j2)})
        else:
            kind = {"replace": "substitution", "delete": "omission_in_P", "insert": "addition_in_P"}[tag]
            diffs.append({"level": "L4", "kind": kind, "i": (i1, i2), "j": (j1, j2)})
    if miss["A"] or miss["P"]:
        diffs.append({"level": "L3", "kind": "tashkeel_missing", "i": (0, 0), "j": (0, 0),
                      "detail": {"missing_in_A": miss["A"], "missing_in_P": miss["P"], "examples": miss["ex"]}})
    levels = [d["level"] for d in diffs]
    if levels:
        top = max(levels)
    elif a_text.strip() == u["text"].strip():
        top = "L0"
    else:
        top = "L1"
    for d in diffs:
        cnt[d["level"] + "_" + d["kind"]] += 1
    cnt["tashkeel_letters_missing_in_A"] = miss["A"]
    cnt["tashkeel_letters_missing_in_P"] = miss["P"]
    return diffs, top, cnt, ta


def hid(n):
    return f"bukhari-{int(n):04d}" if float(n) == int(n) else f"bukhari-{n}"


def main() -> int:
    units = load_units()
    doc = json.loads(A_FILE.read_text(encoding="utf-8"))
    a_by_num = {h["hadithnumber"]: h for h in doc["hadiths"]}
    opinions = {}
    if OPIN.exists():
        for line in OPIN.read_text(encoding="utf-8").splitlines():
            if line.strip():
                o = json.loads(line)
                opinions[o["diff_id"]] = o["agent_opinion"]

    hadith_units = [u for u in units if u["kind"] == "hadith"]
    nums = [u["printed_number"] for u in hadith_units if isinstance(u["printed_number"], int)]
    lo, hi = (min(nums), max(nums)) if nums else (1, 0)
    window = [n for n in a_by_num if lo - 3 <= n <= hi + 3]
    a_skel = {n: K.skeleton_key(a_by_num[n]["text"]).replace(" ", "") for n in window}

    used, align_rows, queue, total = set(), [], [], Counter()
    for u in units:
        p0 = u["parts"][0]
        pref = {"ref": f"sultaniyya j1 p{p0['page']} seq{p0['seq']}", "text": u["text"],
                "pages": [p["page"] for p in u["parts"]]}
        if u["kind"] != "hadith":
            uid = f"bukhari-{u['kind']}-p{p0['page']:04d}s{p0['seq']:02d}"
            align_rows.append({"id": uid, "kind": u["kind"], "numbers": {}, "A": None, "B": None, "P": pref,
                               "match_score": {"A_P": None, "B_P": None, "A_B": None}, "level": "single_witness"})
            total["single_witness_" + u["kind"]] += 1
            continue
        usk = K.skeleton_key(u["text"]).replace(" ", "")
        n, score = u["printed_number"], 0.0
        if isinstance(n, int) and n in a_skel and n not in used:
            score = ratio(a_skel[n], usk)
        if score < MIN_SCORE:  # الرقم المطبوع غائب أو لا يطابق: ابحث في النافذة
            best = max(((ratio(a_skel[m], usk), m) for m in window if m not in used), default=(0, None))
            if best[0] >= MIN_SCORE and best[0] > score:
                score, n = best
        if score < MIN_SCORE:
            uid = f"bukhari-unmatched-p{p0['page']:04d}s{p0['seq']:02d}"
            align_rows.append({"id": uid, "kind": "hadith", "numbers": {"printed": u["printed_number"]}, "A": None,
                               "B": None, "P": pref,
                               "match_score": {"A_P": score, "B_P": None, "A_B": None}, "level": "L5"})
            note = "مقطع حديث في المطبوع لم يجد مطابقًا في A"
            if u["orphan_start"]:
                note += " (بدايته في صفحة قبل نطاق التجربة)"
            queue.append({"diff_id": uid + "-d01", "hadith_id": uid, "level": "L5", "kind": "no_match_in_A",
                          "context_before": "", "readings": {"A": None, "B": None, "P": u["text"]},
                          "image": p0["image"], "crop": {"page": p0["page"], "y_frac": round(p0["frac0"], 3)},
                          "approx_line": 1 + int(p0["frac0"] * LINES_PER_PAGE),
                          "agent_opinion": opinions.get(uid + "-d01"), "note": note})
            total["L5"] += 1
            continue
        used.add(n)
        uid = hid(n)
        a = a_by_num[n]
        diffs, top, cnt, ta = compare(a["text"], u)
        total.update(cnt)
        total["hadith_level_" + top] += 1
        row_nums = {"abdulbaqi": n}
        if u["printed_number"] != n:
            row_nums["printed_as_read"] = u["printed_number"]
        align_rows.append({"id": uid, "kind": "hadith", "numbers": row_nums,
                           "A": {"ref": f"fawazahmed0:ara-bukhari#{n}", "text": a["text"]}, "B": None, "P": pref,
                           "match_score": {"A_P": score, "B_P": None, "A_B": None}, "level": top})
        for k, d in enumerate(diffs, 1):
            (i1, i2), (j1, j2) = d["i"], d["j"]
            part, frac = locate(u, j1)
            item = {"diff_id": f"{uid}-d{k:02d}", "hadith_id": uid, "level": d["level"], "kind": d["kind"],
                    "context_before": " ".join(t["raw"] for t in u["tokens"][max(0, j1 - 6):j1]),
                    "readings": {"A": " ".join(t["raw"] for t in ta[i1:i2]), "B": None,
                                 "P": " ".join(t["raw"] for t in u["tokens"][j1:j2])},
                    "context_after": " ".join(t["raw"] for t in u["tokens"][j2:j2 + 4]),
                    "image": part["image"], "crop": {"page": part["page"], "y_frac": round(frac, 3)},
                    "approx_line": 1 + int(frac * LINES_PER_PAGE),
                    "p_uncertain": any(j in u["unc"] for j in range(j1, max(j2, j1 + 1))),
                    "agent_opinion": None}
            if "detail" in d:
                item["detail"] = d["detail"]
            if d["kind"] == "tashkeel_missing":
                item.update({"readings": {"A": None, "B": None, "P": None}, "context_before": "",
                             "context_after": "", "p_uncertain": False,
                             "crop": {"page": u["parts"][0]["page"], "y_frac": round(u["parts"][0]["frac0"], 3)},
                             "image": u["parts"][0]["image"],
                             "approx_line": 1 + int(u["parts"][0]["frac0"] * LINES_PER_PAGE)})
            item["agent_opinion"] = opinions.get(item["diff_id"])
            queue.append(item)
    # سجلات في A ضمن نطاق أرقام التجربة ولم تظهر في القراءة
    for n in sorted(m for m in a_by_num if lo <= m <= hi and m not in used):
        uid = hid(n)
        note = "سجل في A داخل نطاق أرقام التجربة ولم يُعثر عليه في القراءة"
        if not a_by_num[n]["text"].strip():
            note += " (نصه فارغ في A)"
        queue.append({"diff_id": uid + "-d01", "hadith_id": uid, "level": "L5", "kind": "in_A_not_in_P",
                      "context_before": "", "readings": {"A": a_by_num[n]["text"], "B": None, "P": None},
                      "image": None, "crop": None, "approx_line": None,
                      "agent_opinion": opinions.get(uid + "-d01"), "note": note})
        align_rows.append({"id": uid, "kind": "hadith", "numbers": {"abdulbaqi": n},
                           "A": {"ref": f"fawazahmed0:ara-bukhari#{n}", "text": a_by_num[n]["text"]},
                           "B": None, "P": None,
                           "match_score": {"A_P": None, "B_P": None, "A_B": None}, "level": "L5"})
        total["L5"] += 1

    order = {"L5": 0, "L4": 1, "L3": 2, "L2": 3}
    queue.sort(key=lambda q: (order[q["level"]], q["kind"] == "tashkeel_missing", q["diff_id"]))
    ALIGN.parent.mkdir(parents=True, exist_ok=True)
    ALIGN.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in align_rows), encoding="utf-8")
    QUEUE.write_text("".join(json.dumps(q, ensure_ascii=False) + "\n" for q in queue), encoding="utf-8")
    stats = {"pages": LAST - FIRST + 1, "units": dict(Counter(u["kind"] for u in units)),
             "a_number_range": [lo, hi], "matched_hadiths": len(used),
             "queue_total": len(queue),
             "queue_by_level_kind": dict(Counter(q["level"] + ":" + q["kind"] for q in queue)),
             "queue_items_touching_uncertain": sum(1 for q in queue if q.get("p_uncertain")),
             "uncertain_spans": sum(p["n_unc"] for u in units for p in u["parts"]),
             "counters": dict(total),
             "P_tokens": sum(len(u["tokens"]) for u in units),
             "P_tokens_hadith": sum(len(u["tokens"]) for u in hadith_units)}
    STATS.write_text(json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
