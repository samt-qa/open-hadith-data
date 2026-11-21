"""جدول التقابل (concordance): لكل حديث أرقامه في الترقيمات الأخرى.

الاستعمال: python -I scripts/concordance.py

المخرجات:
  build/concordance.jsonl          سطر لكل سجل حديث في كل كتاب من COLLECTIONS:
      {"id": "bukhari:1", "refs": {"<system>": <value or list>, "<system>_merged": true, ...}}
  reports/concordance-report.md    التغطية وطريقة الإسناد والحدود ونتائج الفحوص الذاتية

لا يُخترع رقم: كل إسناد إما منقول من السجل نفسه، وإما من محاذاة المقابلة الموجودة بالمحتوى
(work/compare/<c>-AB.jsonl من compare_ab.py، وwork/compare/<c>-W<wid>.jsonl من compare_witness.py).
- مجموعة 1:1 ← رقم الطرف الآخر (قائمة إن كان السجل الواحد هناك يحمل أكثر من رقم).
- مجموعة مدموجة (n:m غير 1:1) ← قائمة أرقام الطرف الآخر و "<system>_merged": true.
- مجموعة ضعيفة (score < 0.6، low_score: تقسيم أو نص مختلف تحت الرقم نفسه) أو بلا نظير ← لا إسناد.

الأنظمة:
  fawazahmed0                hadithnumber في base/fawazahmed0/ara-<c>.json (الستة والموطأ)
  fawazahmed0_arabicnumber   مسلم: arabicnumber في الملف نفسه (رقم عبد الباقي عند fawazahmed0)
  shamela-<wid>              رقم الحديث في الطبعة الشاهدة الثانية من الشاملة
  abd_al_baqi                مسلم: numbers.abd_al_baqi في السجل (كما طُبع في الأساس)
  numbering_series           numbers.series: الجزء/السلسلة التي بدأ فيها الترقيم من جديد (الكبير، البزار)
  mulhaq                     numbers.mulhaq: رقم الحديث في الملحق (أحمد)
  ibnhibban_taqasim          taqasim: «القسم:النوع» في التقاسيم والأنواع (ابن حبان)
  printed_as                 numbers.printed_as: الرقم كما طُبع خطأً في الأساس (والمعرّف بالرقم المتوقع)
"""
import hashlib
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hadith_ids as H  # noqa: E402
import textkeys as K  # noqa: E402
from compare_ab import A_FILES, MERGE_MIN  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "build" / "concordance.jsonl"
REPORT = ROOT / "reports" / "concordance-report.md"

WITNESSES = {"tirmidhi": 1435, "nasai": 1339, "abudawud": 117359, "ibnmajah": 98138, "ahmad": 98139,
             "muslim": 1727, "bukhari": 735, "malik": 28107, "darimi": 36114, "adabmufrad": 9647,
             "tahawi": 1547, "ibnjarud": 13071, "ibnabishaybah": 9944, "hakim": 2266, "ibnkhuzaymah": 121382,
             "ibnhibban": 537, "abdurrazzaq": 84, "bayhaqi": 7861, "abuyala": 181}
# sha256 المسجّلة في PROVENANCE.md
SHA256 = {
    "bukhari": "e34a3402889ca378871da3c5984b7875c680920e93f1c8738ac7afe502179562",
    "muslim": "194073b24090c5368e4d14a3f55c9e0ef144c7437bd7e5aa83aa4d2bc54a8ea0",
    "abudawud": "216139c5f40a8147e700d62ffa3b5b2fe45d0e034f86941a193c598c10056189",
    "tirmidhi": "408028cd56329ed78edbe3ad443beb96b58e16c3e5bd49f9bc7b0eac77c8820f",
    "nasai": "c705983c19bb089c87cd6531aff609bd94d862183ed0859115b0ff991826a956",
    "ibnmajah": "b406e6be81588ab0ec1ddbed32f5fd95bbcdda242c460d88331e82eb5c2bc0aa",
    "malik": "088b1f354e110211da006d47e37dd8f8837368f318ed683271f0fdb0f09a3ab5",
}
SAMPLE, SEED, OVERLAP_OK = 20, 20261121, 0.5


def num(v):
    """رقم المصدر كما هو، والقيمة الصحيحة عددًا صحيحًا («8» ← 8، و«8.01» يبقى نصًّا، و402.2 يبقى عشريًّا)."""
    if isinstance(v, str):
        s = v.strip()
        return int(s) if s.isdigit() else s
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def scalar_or_list(vals):
    vals = list(dict.fromkeys(vals))
    return vals[0] if len(vals) == 1 else vals


def words(text):
    return {t["skel"] for t in K.tokens(text or "") if len(t["skel"]) > 1}


def overlap(a, b):
    wa, wb = words(a), words(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / min(len(wa), len(wb))


def rec_text(r):
    return r.get("text_source", r.get("text", ""))


def load_rows(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(x) for x in f]


def assign_from_rows(rows, system, by_seq, refs, st, map_a=lambda n: n, links=None):
    """يسند أرقام الطرف الآخر (row["A"]) إلى سجلات الأساس (row["B_seq"]) من صفوف المحاذاة."""
    for row in rows:
        ga, gb = row["A"], row["B_seq"]
        if not gb:
            st["only_in_other"] += 1
            continue
        if not ga:
            st["no_match_or_unnumbered"] += len(gb)
            continue
        if row.get("low_score") or row["score"] < MERGE_MIN:
            st["weak_excluded"] += len(gb)
            continue
        vals = [v for v in (map_a(n) for n in ga) if v is not None]
        if not vals:
            st["no_number_on_other_side"] += len(gb)
            continue
        merged = row["shape"] != "1:1"
        for s in gb:
            r = by_seq.get(s)
            if r is None or r.get("type") != "hadith":
                st["stale_seq"] += 1
                continue
            rr = refs[r["id"]]
            if system in rr:  # سجل وقع في مجموعتين (لا يُتوقع): قائمة مدموجة
                old = rr[system] if isinstance(rr[system], list) else [rr[system]]
                rr[system] = list(dict.fromkeys(old + vals))
                rr[system + "_merged"] = True
                st["double_assigned"] += 1
                continue
            rr[system] = list(dict.fromkeys(vals)) if merged else scalar_or_list(vals)
            if merged:
                rr[system + "_merged"] = True
            st["merged" if merged else "one_to_one"] += 1
            if links is not None:
                links.append((r["id"], row))


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    rng = random.Random(SEED)
    out_lines, report = [], {}
    all_ids = {}
    checks = []

    for coll in H.COLLECTIONS:
        recs = H.load(coll)
        hads = [r for r in recs if r.get("type") == "hadith"]
        by_seq = {r["seq"]: r for r in recs}
        by_id = {r["id"]: r for r in hads}
        all_ids[coll] = set(by_id)
        refs = {r["id"]: {} for r in hads}
        info = {"total": len(hads), "systems": {}}

        # 1) fawazahmed0
        if coll in A_FILES:
            p = ROOT / "base" / "fawazahmed0" / A_FILES[coll]
            if not p.exists():
                raise SystemExit(f"مفقود: {p} — نزّله بـ python -I scripts/fetch_a.py {coll}")
            digest = hashlib.sha256(p.read_bytes()).hexdigest()
            if digest != SHA256[coll]:
                raise SystemExit(f"sha256 لا يطابق PROVENANCE.md: {p}")
            aj = json.loads(p.read_text(encoding="utf-8"))
            a_by_n = {}
            for h in aj["hadiths"]:
                a_by_n.setdefault(h["hadithnumber"], h)
            rows = load_rows(ROOT / "work" / "compare" / f"{coll}-AB.jsonl")
            st, links = Counter(), []
            assign_from_rows(rows, "fawazahmed0", by_seq, refs, st, map_a=num, links=links)
            info["systems"]["fawazahmed0"] = {"st": st, "method": "محاذاة المقابلة بالمحتوى (compare_ab.py ← work/compare/" + coll + "-AB.jsonl)",
                                              "sample": sample_check(rng, links, by_seq, lambda row: " ".join(
                                                  a_by_n[n]["text"] for n in row["A"] if n in a_by_n))}
            if coll == "muslim":
                st2 = Counter()

                def arabic(n):
                    v = a_by_n.get(n, {}).get("arabicnumber")
                    return num(v) if v not in (None, "") else None
                assign_from_rows(rows, "fawazahmed0_arabicnumber", by_seq, refs, st2, map_a=arabic)
                # برهان: الجزء الصحيح من arabicnumber يطابق numbers.abd_al_baqi في الأساس؟
                agree = tot = 0
                for hid, rr in refs.items():
                    v = rr.get("fawazahmed0_arabicnumber")
                    abq = by_id[hid]["numbers"].get("abd_al_baqi")
                    if v is None or rr.get("fawazahmed0_arabicnumber_merged") or not abq:
                        continue
                    tot += 1
                    bset = {int(x) for x in re.findall(r"\d+", str(abq))}
                    vals = v if isinstance(v, list) else [v]
                    agree += any(int(float(x)) in bset for x in vals)
                info["systems"]["fawazahmed0_arabicnumber"] = {
                    "st": st2, "method": "من المحاذاة نفسها (الصف ← hadithnumber ← arabicnumber)",
                    "extra": f"الجزء الصحيح يطابق abd_al_baqi في الأساس في {agree} من {tot} مطابقة 1:1"}
                checks.append(("مسلم: arabicnumber يوافق عبد الباقي في الأساس (1:1)", f"{agree}/{tot}", agree >= 0.95 * tot))

        # 2) الشاهد الثاني
        if coll in WITNESSES:
            wid = WITNESSES[coll]
            system = f"shamela-{wid}"
            wit = load_rows(ROOT / "text" / coll / f"witness-{wid}.jsonl")
            w_by_n = defaultdict(list)
            for r in wit:
                if r.get("type") != "hadith":
                    continue
                nb = r.get("numbers") or {}
                disp = [nb["abd_al_baqi"]] if "abd_al_baqi" in nb else nb.get("printed") or []
                for n in disp:
                    w_by_n[num(n)].append(rec_text(r))
            rows = load_rows(ROOT / "work" / "compare" / f"{coll}-W{wid}.jsonl")
            st, links = Counter(), []
            assign_from_rows(rows, system, by_seq, refs, st, map_a=num, links=links)
            note = "رقم عبد الباقي كما طُبع في الشاهد" if coll == "muslim" else "الرقم المطبوع في الشاهد"
            info["systems"][system] = {"st": st, "method": f"محاذاة الشاهد بالمحتوى (compare_witness.py ← work/compare/{coll}-W{wid}.jsonl)؛ القيمة {note}",
                                       "sample": sample_check(rng, links, by_seq, lambda row: " ".join(
                                           t for n in row["A"] for t in w_by_n.get(num(n), [])))}

        # 3) الترقيمات داخل السجل
        inrec = Counter()
        for r in hads:
            nb, rr = r.get("numbers") or {}, refs[r["id"]]
            if nb.get("abd_al_baqi"):
                rr["abd_al_baqi"] = num(nb["abd_al_baqi"]); inrec["abd_al_baqi"] += 1
            if "series" in nb:
                rr["numbering_series"] = nb["series"]; inrec["numbering_series"] += 1
            if "mulhaq" in nb:
                rr["mulhaq"] = nb["mulhaq"]; inrec["mulhaq"] += 1
            if r.get("taqasim"):
                rr["ibnhibban_taqasim"] = scalar_or_list(r["taqasim"]); inrec["ibnhibban_taqasim"] += 1
            if nb.get("printed_as") not in (None, []):
                v = nb["printed_as"]
                rr["printed_as"] = scalar_or_list(v) if isinstance(v, list) else v; inrec["printed_as"] += 1
        for k, c in inrec.items():
            info["systems"][k] = {"st": Counter(one_to_one=c), "method": "منقول من السجل نفسه", "inrec": True}

        for r in hads:
            out_lines.append(json.dumps({"id": r["id"], "refs": refs[r["id"]]}, ensure_ascii=False))
        report[coll] = info
        print(coll, {k: dict(v["st"]) for k, v in info["systems"].items()})

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out_lines) + "\n")

    # الفحوص الذاتية: تُقرأ من الملف المكتوب
    seen, bad, dup, b1 = set(), 0, 0, None
    with open(OUT, encoding="utf-8") as f:
        for line in f:
            o = json.loads(line)
            assert set(o) == {"id", "refs"} and isinstance(o["refs"], dict)
            c = o["id"].split(":", 1)[0]
            bad += o["id"] not in all_ids.get(c, ())
            dup += o["id"] in seen
            seen.add(o["id"])
            if o["id"] == "bukhari:1":
                b1 = o["refs"].get("fawazahmed0")
    checks.insert(0, ("كل id في الملف موجود في السجلات", f"{len(seen)} معرّفًا، المفقود {bad}، المكرر {dup}", bad == 0 and dup == 0))
    checks.insert(1, ("البخاري 1 ↔ fawazahmed0 1", f"القيمة {b1!r}", b1 == 1))
    write_report(report, checks)
    for name, val, ok in checks:
        print("OK " if ok else "FAIL", name, val)
    return 0 if all(ok for _, _, ok in checks) else 1


def sample_check(rng, links, by_seq, other_text):
    if not links:
        return None
    pick = rng.sample(links, min(SAMPLE, len(links)))
    scores = []
    for hid, row in pick:
        base = " ".join(rec_text(by_seq[q]) for q in row["B_seq"] if q in by_seq)  # المجموعة كلها في الأساس
        scores.append((hid, round(overlap(base, other_text(row)), 3)))
    vals = [s for _, s in scores]
    return {"n": len(vals), "mean": round(sum(vals) / len(vals), 3), "min": min(vals),
            "ok": sum(v >= OVERLAP_OK for v in vals), "low": [h for h, s in scores if s < OVERLAP_OK]}


def pct(a, b):
    return f"{100 * a / b:.1f}%" if b else "—"


def write_report(report, checks):
    L = ["# جدول التقابل (concordance) — التقرير", "",
         "يبنيه `python -I scripts/concordance.py`، ومخرجه `build/concordance.jsonl`: سطر لكل سجل حديث "
         "(كل كتب `COLLECTIONS`، والمعرّف من `scripts/hadith_ids.py`) بالصيغة "
         "`{\"id\": \"bukhari:1\", \"refs\": {\"<system>\": <value or list>, \"<system>_merged\": true}}`. "
         "السجل الذي لا ترقيم آخر له يأتي بـ `refs` فارغة.", "",
         "## الأنظمة وطريقة الإسناد", "",
         "| النظام | المصدر | الإسناد |", "|---|---|---|",
         "| `fawazahmed0` | `hadithnumber` في `base/fawazahmed0/ara-<book>.json` (الستة والموطأ؛ sha256 مطابق لـ PROVENANCE.md) | محاذاة المقابلة بالمحتوى `work/compare/<book>-AB.jsonl` (compare_ab.py) |",
         "| `fawazahmed0_arabicnumber` | `arabicnumber` في ara-muslim.json (رقم عبد الباقي عند fawazahmed0؛ «8.01» يبقى نصًّا) | المحاذاة نفسها، من hadithnumber إلى arabicnumber |",
         "| `shamela-<wid>` | رقم الحديث المطبوع في الطبعة الشاهدة (مسلم 1727: رقم عبد الباقي فيها) | محاذاة الشاهد `work/compare/<book>-W<wid>.jsonl` (compare_witness.py) |",
         "| `abd_al_baqi` | `numbers.abd_al_baqi` (مسلم) | منقول من السجل |",
         "| `numbering_series` | `numbers.series`: الجزء الذي بدأ فيه الترقيم من جديد (الطبراني الكبير، البزار) | منقول من السجل؛ يُقرأ مع رقم المعرّف |",
         "| `mulhaq` | `numbers.mulhaq`: رقم الحديث في الملحق (المسند) | منقول من السجل |",
         "| `ibnhibban_taqasim` | `taqasim`: «القسم:النوع» في التقاسيم والأنواع | منقول من السجل (نص أو قائمة) |",
         "| `printed_as` | `numbers.printed_as`: الرقم كما طُبع خطأً في الأساس | منقول من السجل |", "",
         "قواعد الإسناد من المحاذاة: مجموعة 1:1 ← رقم الطرف الآخر (قائمة بلا وسم الدمج إن كان سجله الواحد يحمل أكثر من رقم، "
         "كتكرار fawazahmed0 النص نفسه تحت رقمين). مجموعة مدموجة (اختلاف التقسيم n:m) ← قائمة و`<system>_merged: true` "
         "لكل سجل من سجلات الأساس فيها. لا إسناد لما لا نظير له، ولا للمجموعات الضعيفة (score < 0.6، "
         "أي تقسيم أو نص مختلف تحت الرقم نفسه)، ولا لشاهد بلا رقم.", "",
         "## التغطية", "",
         "النسبة من سجلات الحديث في الأساس. «ضعيف» = مستبعد لضعف التشابه؛ «بلا نظير» = سجلات الأساس التي لم تجد نظيرًا.", "",
         "| الكتاب | السجلات | النظام | مغطّى | النسبة | 1:1 | مدموج | ضعيف | بلا نظير | انفرد به الآخر |",
         "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|"]
    for coll, info in report.items():
        for sysname, d in info["systems"].items():
            st = d["st"]
            cov = st["one_to_one"] + st["merged"]
            L.append(f"| {coll} | {info['total']} | `{sysname}` | {cov} | {pct(cov, info['total'])} | {st['one_to_one']} | "
                     f"{st['merged']} | {st['weak_excluded']} | {st['no_match_or_unnumbered'] + st['no_number_on_other_side']} | "
                     f"{st['only_in_other']} |")
    L += ["", "## الفحوص الذاتية", ""]
    for name, val, ok in checks:
        L.append(f"- {'ناجح' if ok else 'فاشل'}: {name} — {val}")
    stale = sum(d["st"]["stale_seq"] + d["st"]["double_assigned"] for i in report.values() for d in i["systems"].values())
    L.append(f"- سجلات أساس في المحاذاة لا تطابق سجل حديث حاليًّا (B_seq قديم) أو وقعت في مجموعتين: {stale}")
    L += ["", f"### عيّنة التشابه النصي ({SAMPLE} ربطًا عشوائيًّا لكل نظام في كل كتاب، بذرة {SEED})", "",
          "التداخل = الكلمات المشتركة (هيكل الحروف، بلا تشكيل) ÷ عدد كلمات الأقصر من الطرفين. "
          f"«مقبول» ≥ {OVERLAP_OK}. في المدموج يُقابَل نص المجموعة كلها في الأساس بنصها كلها في الطرف الآخر. "
          "الأنظمة المنقولة من السجل نفسه لا طرف آخر لها فلا عيّنة.", "",
          "| الكتاب | النظام | العيّنة | المتوسط | الأدنى | مقبول | دون الحد |", "|---|---|---:|---:|---:|---:|---|"]
    tot_n = tot_ok = 0
    for coll, info in report.items():
        for sysname, d in info["systems"].items():
            s = d.get("sample")
            if not s:
                continue
            tot_n += s["n"]; tot_ok += s["ok"]
            L.append(f"| {coll} | `{sysname}` | {s['n']} | {s['mean']} | {s['min']} | {s['ok']} | {', '.join(s['low']) or '—'} |")
    L += ["", f"المجموع: {tot_ok} من {tot_n} ربطًا مقبول ({pct(tot_ok, tot_n)}).", ""]
    extras = [(c, k, d["extra"]) for c, i in report.items() for k, d in i["systems"].items() if d.get("extra")]
    for c, k, e in extras:
        L.append(f"- {c} `{k}`: {e}.")
    L += ["", "## الحدود", "",
          "- الإسناد من المحاذاة الآلية الموجودة كما هي؛ لم تُعَد المحاذاة. مواضع الخلاف التي في طوابير المراجعة "
          "(`review/*-queue.jsonl`) لم يقضِ فيها المالك، فالربط في المجموعات المدموجة والمعاد ترتيبها قرينة لا قطع.",
          "- المجموعات الضعيفة (score < 0.6) مستبعدة وإن اشتركت في الرقم، فلا يُفترض أن رقمين متساويين حديث واحد.",
          "- `fawazahmed0` للموطأ ترقيم تسلسلي خاص بذلك المصدر، غير ترقيم عبد الباقي؛ وللبخاري والنسائي والترمذي "
          "وابن ماجه أرقام فرعية عشرية فيه (402.2) تُنقل كما هي.",
          "- `shamela-98139` (أحمد ت شاكر) لا يغطي إلا 1–8782 من المسند؛ ومسلم 1727 قيمته رقم عبد الباقي المطبوع في الشاهد.",
          "- `numbering_series` لا يكفي وحده: الرقم في الطبراني الكبير يتكرر بين السلاسل، فيُقرأ (السلسلة، الرقم) معًا.",
          "- الكتب التي لا مصدر مفتوحًا ولا شاهدًا لها (الطبراني بمعاجمه، الطيالسي، الحميدي، النسائي الكبرى، الدارقطني، البزار) "
          "ليس لها إلا ما في السجل نفسه.",
          "- إن أُعيد الاستخراج فتغيّر `seq` لزم إعادة `compare_*.py` قبل هذا السكربت؛ الفحص أعلاه يعدّ ما لا يطابق.", ""]
    REPORT.write_text("\n".join(L), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    sys.exit(main())
