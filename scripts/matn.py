"""فصل المتن عن السند في سجلات الأحاديث.

الواجهة العامة:
    split(record) -> {"isnad": str|None, "matn": str|None,
                      "confidence": "high"|"medium"|"low"|None,
                      "method": "source"|"heuristic"}

- المتن والسند مقطعان حرفيان من record["text"] (شرائح منه)، لا يُعاد كتابة شيء.
- إن كان في السجل حقل "matn" من المصدر ووقع في النص (حرفيًّا أو بعد تطبيع المسافات فقط)
  أُخذ بـ method="source" وconfidence="high". وإلا عومل كأنه غير موجود.
- وإلا فالطريقة الآلية (split_heuristic): قواعد صريحة على صيغ الأداء وعلامات القول.

الفحص الذاتي:
    python -I scripts/matn.py --eval
يقيس الطريقة الآلية على المعيار الذهبي (الكتب الستة ذات matn من المصدر)، ويطبع المقاييس
ويكتب build/matn-eval.json.
"""
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------- تطبيع للمطابقة فقط

_DIAC = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")
_EDGE = re.compile(r"^[^\wﷺ]+|[^\wﷺ]+$")
_ALEF = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ؤ": "و", "ئ": "ي"})
_TOKEN = re.compile(r"\S+")
_WORD = re.compile(r"\w|ﷺ")
PBUH = "ﷺ"  # ﷺ


def _skel(tok):
    s = _DIAC.sub("", tok)
    s = _EDGE.sub("", s)
    return s.translate(_ALEF)


# صيغ الأداء القوية: إن جاءت بعد «قال:» استمر السند.
TX_STRONG = {
    "حدثنا", "حدثني", "حدثناه", "حدثنيه", "حدثه", "حدثهم", "حدثتني", "حدثتنا", "حدثت", "حدثاه",
    "اخبرنا", "اخبرني", "اخبرناه", "اخبرنيه", "اخبره", "اخبرهم", "اخبرتني", "اخبرتنا", "اخبرت",
    "انبانا", "انباني", "انبانيه", "انباناه", "انباه", "نبانا", "انبا",
    "ثنا", "ثني", "نا", "ناه", "حدثناهم", "سمعت", "سمعنا", "سمعته", "سمعتها", "سمعه",
    "قرات", "قرئ", "قراه", "قراءه",
}
# روابط السند: تصل حلقة بأخرى، ولا تكفي وحدها لاستمرار السند بعد «قال:».
TX_LINK = TX_STRONG | {
    "عن", "عنه", "سمع", "يحدث", "تحدث", "يخبر", "حدث", "انا", "ح", "رواه", "يرويه",
    "يرفعه", "رفعه", "يبلغ", "به", "يعني", "يعنى", "يقال", "وهو", "هو",
}
GLOSS = {"عن", "به", "هو", "وهو", "يعني", "يعنى", "يقال", "ح", "عنه"}  # روابط لا تدل وحدها على سند تالٍ
SPEECH = {"قال", "قالت", "قالا", "قالوا", "يقول", "تقول", "يقولون", "قلن", "فقال", "فقالت",
          "وقال", "وقالت", "وزاد", "زاد", "يقولا"}
ANNA = {"ان", "انه", "انها", "انهم", "انهما"}
PROPHET = {"النبي", "رسول", "نبي"}
# ثقة كل قرينة معايرةً على المعيار الذهبي بعد حجب «» (انظر reports/matn-eval.md)
LEX_CONF = {"prophet": "high", "anna-prophet": "high", "anna-speech": "high",
            "speech": "medium", "anna": "medium",
            "colon": "low", "speech-nc": "low", "refer": "low"}
TOL = 5  # تسامح المقياس بالكلمات
GAP = 16  # أقصى بُعد (بالكلمات) بين صيغتي أداء متتاليتين في السند


def _strip_wa(s):
    if len(s) > 2 and s[0] in "وف" and s[1:] in TX_LINK:
        return s[1:]
    return s


def _tokens(text):
    """كلمات النص مع مواضعها، وهيكلها المطبّع، وهل يليها نقطتا القول."""
    toks = []
    for m in _TOKEN.finditer(text):
        raw = m.group()
        sk = _skel(raw)
        if not sk:  # رمز ترقيم منفصل
            if toks and ":" in raw:
                toks[-1][3] = True
            if toks and "«" in raw:
                toks[-1][4] = True
            continue
        toks.append([m.start(), m.end(), _strip_wa(sk), raw.rstrip().endswith(":") or ":" in raw[-2:],
                     False, raw, sk])
    return toks


def _is_pbuh(t):
    return PBUH in t[5] or t[2] in ("صلي",)


def _prophet_at(toks, k):
    """إن بدأ ذكر النبي ﷺ عند k أعاد موضع ما بعد «ﷺ»، وإلا None."""
    n = len(toks)
    if k >= n:
        return None
    s = toks[k][2]
    if s in ("النبي", "نبي") or s == "رسول" or s == "برسول":
        # النبي ﷺ / رسول الله ﷺ / نبي الله ﷺ
        for j in range(k, min(k + 4, n)):
            if PBUH in toks[j][5]:
                return j + 1
            if toks[j][2] == "صلي":  # «صلى الله عليه وسلم» مكتوبة
                for jj in range(j, min(j + 5, n)):
                    if toks[jj][2] == "وسلم":
                        return jj + 1
                return None
    return None


REFER = ("بهذا", "بمثل", "بمثله", "بمعناه", "بنحوه", "نحوه", "مثله", "بمعني", "بنحو", "مثل", "نحو", "بذلك", "بهذه")


def _txlike(s):
    if s in TX_LINK:
        return True
    if len(s) > 3 and s[0] == "و":
        s = s[1:]
    return s.startswith(("حدث", "اخبر", "انبا", "سمع", "نبا"))


def _tx_ahead(toks, k, w=6):
    """هل تقع صيغة أداء صريحة (لا «عن» ولا ما أوله فاء) في الكلمات w التالية لـ k؟"""
    for x in range(k, min(k + w, len(toks))):
        raw = toks[x][6]
        if raw.startswith("ف"):
            continue
        s = toks[x][2]
        if s not in GLOSS and _txlike(s):
            return True
    return False


def _after_speech(toks, k):
    """بعد موضع انتهاء السند k: تخطَّ «قال:» و«قال رسول الله ﷺ:» و«أنه قال:» ونحوها. يعيد موضع بداية المتن."""
    n = len(toks)
    for _ in range(4):
        if k >= n:
            return k
        s = toks[k][2]
        if s in SPEECH and (toks[k][3] or toks[k][4]):
            k += 1
            continue
        if s in SPEECH and k + 1 < n:
            p = _prophet_at(toks, k + 1)
            if p is not None and (toks[p - 1][3] or toks[p - 1][4]
                                  or (p < n and toks[p][2] in SPEECH and (toks[p][3] or toks[p][4]))):
                k = p
                continue
        if s in ("انه", "انها") and k + 1 < n and toks[k + 1][2] in SPEECH and (toks[k + 1][3] or toks[k + 1][4]):
            k += 2
            continue
        break
    return k


def _nested(toks, k):
    """«قال الزهري: وأخبرني…» : فعل قول بلا نقطتين، ثم اسم قصير بنقطتين، ثم صيغة أداء."""
    n = len(toks)
    if k >= n or toks[k][2] not in SPEECH or toks[k][3] or toks[k][4]:
        return False
    for x in range(k + 1, min(k + 5, n)):
        if toks[x][3] or toks[x][4]:
            return _cont(toks, x + 1)
    return False


def _cont(toks, k):
    """هل يستمر السند عند k (صيغة أداء أو تحويل)؟"""
    n = len(toks)
    if k >= n:
        return False
    s = toks[k][2]
    if s == "انا":  # «أنا» اختصار «أخبرنا» إن تلاها سند
        return any(toks[x][2] in TX_LINK and toks[x][2] != "انا" for x in range(k + 1, min(k + 9, n)))
    return s in TX_STRONG or s in ("عن", "ح", "يعني", "يعنى") or _txlike(s)


def _lexical(text):
    """يعيد (موضع بداية المتن بالحرف أو None، نوع القرينة)."""
    toks = _tokens(text)
    n = len(toks)
    if n < 4:
        return None, "short"
    first = None
    for i in range(min(6, n)):
        if toks[i][2] in TX_STRONG or (toks[i][2] == "عن" and i <= 3):
            first = i
            break
    if first is None:
        return None, "no-isnad"
    refer = False
    last = first
    j = first + 1
    pos = lambda k: toks[k][0] if k < n else len(text)  # آخر النص: سند بلا متن

    def done(k, kind):
        return pos(k), ("refer" if refer else kind)

    while j < n:
        if j - last > GAP:
            return None, "gap"
        t = toks[j]
        s = t[2]
        colon = t[3] or t[4]
        # (أ) ذكر النبي ﷺ بعد صيغة أداء: عن/سمعت رسول الله ﷺ
        p = _prophet_at(toks, j)
        if p is not None and (toks[j - 1][2] in ("عن", "سمعت", "سمع", "سمعنا", "يبلغ", "رفعه", "يرفعه")
                              or toks[j - 1][3] or toks[j - 1][4]):
            if _cont(toks, p):
                last = j = p
                continue
            if p < n and toks[p][2].startswith(REFER):
                refer = True
                last = j = p
                j += 1
                continue
            return done(_after_speech(toks, p), "prophet")
        # (ب) صيغة أداء: تمدّ السند
        if s in TX_LINK:
            last = j
            j += 1
            continue
        # (ج) فعل قول
        if s in SPEECH:
            if _cont(toks, j + 1):
                last = j = j + 1
                continue
            if colon:
                k = _after_speech(toks, j + 1)
                if _cont(toks, k):
                    last = j = k
                    continue
                if _nested(toks, k):
                    last = j = k
                    continue
                return done(k, "speech")
            if _nested(toks, j):
                last = j = j + 1
                continue
            if j - last <= 8 and not s.startswith("ف"):
                k = _after_speech(toks, j)
                if k > j + 1:
                    return done(k, "speech")
                return done(j + 1, "speech-nc")
            j += 1
            continue
        # (د) «أنّ» بعد اسم الراوي
        if s in ANNA and j - last <= 8:
            ahead = [toks[x][2] for x in range(j + 1, min(j + 9, n))]
            if any(_txlike(a) and a not in GLOSS for a in ahead):
                last = j
                j += 1
                continue
            k = _after_speech(toks, j)
            if k != j:
                return done(k, "speech")
            for x in range(j + 1, min(j + 7, n)):
                if toks[x][2] in SPEECH and (toks[x][3] or toks[x][4]) and not toks[x][6].startswith(("ف", "و")):
                    return done(_after_speech(toks, x), "anna-speech")
                if toks[x][3] or toks[x][4]:
                    break
            p = _prophet_at(toks, j + 1)
            if p is not None:
                if p < n and toks[p][2] in SPEECH and (toks[p][3] or toks[p][4]) and not toks[p][2].startswith("ف"):
                    return done(p + 1, "prophet")
                return done(j, "anna-prophet")
            return done(j, "anna")
        # (هـ) نقطتان بعد اسم الراوي
        if colon and j - last <= 8:
            if _cont(toks, j + 1) or _tx_ahead(toks, j + 1):
                last = j = j + 1
                continue
            nx = toks[j + 1][2] if j + 1 < n else ""
            if nx in SPEECH or nx in ANNA or _prophet_at(toks, j + 1) is not None:
                j += 1
                continue
            return done(j + 1, "colon")
        j += 1
    return len(text), "isnad-only"


def _word_index(text, pos):
    return sum(1 for m in _TOKEN.finditer(text, 0, pos) if _WORD.search(m.group()))


def _heuristic(text, use_quotes=True):
    """يعيد (النتيجة، موضع بداية المتن أو None، نوع القرينة، حال العلامة «)."""
    res = {"isnad": None, "matn": None, "confidence": None, "method": "heuristic"}
    if not text or not text.strip():
        return res, None, "empty", "none"
    lex, kind = _lexical(text)
    q = text.find("«") if use_quotes else -1
    quote_ok = False
    if q >= 0:
        # العلامة « قرينة إن سبقها سند: صيغة أداء صريحة في أول ست كلمات
        bt = [_strip_wa(_skel(x)) for x in text[:q].split()]
        bt = [x for x in bt if x]
        quote_ok = any(x in TX_STRONG for x in bt[:6])
    start, conf, qstate = None, None, "none"
    if lex is not None and quote_ok:
        if abs(_word_index(text, lex) - _word_index(text, q)) <= TOL:
            start, conf, qstate = q, "high", "agree"
        elif q < lex:
            # « قبل نهاية السند المقدَّرة: السند لا يحوي « عادةً، فالقواعد تجاوزت بداية المتن
            start, conf, qstate = q, "medium", "disagree-q"
        else:
            # « بعد البداية المقدَّرة بكثير: في بعض النشرات تحيط «» بالمتن كله، وفي أكثرها
            # بكلام النبي ﷺ وحده داخل المتن. نأخذ القاعدة اللفظية (المتن كله) بثقة منخفضة.
            start, conf, qstate = lex, "low", "disagree-lex"
    elif lex is not None:
        start, conf = lex, LEX_CONF.get(kind, "low")
    elif quote_ok:
        start, conf, qstate = q, "medium", "quote-only"
    if start is None:
        return res, None, kind, qstate
    matn = text[start:].strip()
    if not matn or not _WORD.search(matn):
        # انتهى النص والسند لم ينقطع: سند بلا متن (إحالة «مثله» أو تحويل)، فلا متن
        if start == lex and text.strip():
            res["isnad"] = text.strip() if _WORD.search(text) else None
            res["confidence"] = "low"
            return res, None, "isnad-only", qstate
        return res, None, kind, qstate
    # متن قصير جدًّا (مثله، نحوه) أغلبه إحالة لا متن
    if len(matn.split()) <= 3:
        conf = "low"
    s0 = start + (len(text[start:]) - len(text[start:].lstrip()))
    isnad = text[:start].rstrip()
    res["isnad"] = isnad if isnad and _WORD.search(isnad) else None
    res["matn"] = text[s0:s0 + len(matn)]
    res["confidence"] = conf
    return res, s0, kind, qstate


def split_heuristic(text, use_quotes=True):
    """الطريقة الآلية وحدها (تتجاهل حقل matn). يعيد dict بمفاتيح split نفسها، method="heuristic".
    use_quotes=False يحجب قرينة العلامة «» (يُستعمل في التقييم لمحاكاة الكتب التي لا علامات فيها)."""
    return _heuristic(text, use_quotes)[0]


# ---------------------------------------------------------------- المتن من المصدر

_WS = re.compile(r"\s+")


def _locate(text, matn):
    """يعيد (بداية, نهاية) للمتن في النص حرفيًّا أو بعد تطبيع المسافات، أو None."""
    m = matn.strip()
    if not m:
        return None
    i = text.rfind(m)
    if i >= 0:
        return i, i + len(m)
    norm, idx = [], []
    prev_ws = False
    for k, ch in enumerate(text):
        if ch.isspace():
            if prev_ws:
                continue
            prev_ws = True
            norm.append(" ")
        else:
            prev_ws = False
            norm.append(ch)
        idx.append(k)
    nt = "".join(norm)
    nm = _WS.sub(" ", m)
    i = nt.rfind(nm)
    if i < 0:
        return None
    return idx[i], idx[i + len(nm) - 1] + 1


def split(record):
    """يفصل المتن عن السند في سجل حديث.

    يعيد {"isnad", "matn", "confidence", "method"}؛ المتن والسند شرائح حرفية من record["text"].
    """
    text = record.get("text") or ""
    src = record.get("matn")
    if src and isinstance(src, str) and text:
        loc = _locate(text, src)
        if loc is not None:
            a, b = loc
            isnad = text[:a].rstrip()
            return {"isnad": isnad if isnad and _WORD.search(isnad) else None,
                    "matn": text[a:b], "confidence": "high", "method": "source"}
    return split_heuristic(text)


# ---------------------------------------------------------------- التقييم

GOLD = ["bukhari", "muslim", "nasai", "tirmidhi", "tayalisi", "ibnjarud"]
CONFS = ("high", "medium", "low", "none")


def _short(s, n=60):
    s = _WS.sub(" ", s).strip()
    return s if len(s) <= n else s[:n] + "…"


def evaluate():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from hadith_ids import COLLECTIONS, load

    t0 = time.time()
    out = {"metric": {"tolerance_words": TOL,
                      "word": "رمز مفصول بمسافة يحوي حرفًا (علامات الترقيم المنفردة لا تُعدّ)",
                      "match": "تطابق إن كان فرق بداية المتن عن الذهبي ≤ 5 كلمات وفرق نهايته ≤ 5 كلمات",
                      "modes": {"quotes": "الطريقة الآلية كما تعمل فعلًا (تستعمل «»)",
                                "blind": "بعد استبدال «» بمسافات: يقيس القواعد اللفظية وحدها"}},
           "gold": {"quotes": {}, "blind": {}}, "blind_by_kind": {}, "exact_start": {},
           "source_unlocated": {}, "distribution": {}, "quote_state": {}, "errors": {}}
    examples = defaultdict(list)
    kinds = defaultdict(lambda: [0, 0])
    for c in GOLD:
        recs = [r for r in load(c) if r.get("type") == "hadith"]
        stats = {m: {k: [0, 0] for k in CONFS} for m in ("quotes", "blind")}
        exact = [0, 0]
        unloc = 0
        for r in recs:
            text = r.get("text") or ""
            g = r.get("matn")
            if not g or not isinstance(g, str) or not g.strip():
                continue
            loc = _locate(text, g)
            if loc is None:
                unloc += 1
                continue
            gs, ge = _word_index(text, loc[0]), _word_index(text, loc[1])
            for mode in ("quotes", "blind"):
                t = text if mode == "quotes" else text.replace("«", " ").replace("»", " ")
                p, ps, kind, _ = _heuristic(t, use_quotes=(mode == "quotes"))
                conf = p["confidence"] or "none"
                st = stats[mode][conf]
                st[1] += 1
                if mode == "blind":
                    kinds[kind][1] += 1
                if ps is None:
                    continue
                d0 = _word_index(t, ps) - gs
                d1 = _word_index(t, ps + len(p["matn"])) - ge
                ok = abs(d0) <= TOL and abs(d1) <= TOL
                if mode == "quotes" and conf == "high":
                    exact[1] += 1
                    exact[0] += abs(d0) <= 1
                if ok:
                    st[0] += 1
                    if mode == "blind":
                        kinds[kind][0] += 1
                elif len(examples[(mode, conf)]) < 60:
                    examples[(mode, conf)].append({
                        "id": r["id"], "kind": kind, "d_start": d0, "d_end": d1,
                        "gold": _short(text[max(0, loc[0] - 50):loc[0]])[-45:] + " ‖ " + _short(text[loc[0]:], 30),
                        "pred": _short(t[max(0, ps - 50):ps])[-45:] + " ‖ " + _short(t[ps:], 30)})
        out["source_unlocated"][c] = unloc
        out["exact_start"][c] = {"within_1_word": exact[0], "total_high": exact[1]}
        for mode in ("quotes", "blind"):
            out["gold"][mode][c] = {k: {"correct": v[0], "total": v[1],
                                        "accuracy": round(v[0] / v[1], 4) if v[1] and k != "none" else None}
                                    for k, v in stats[mode].items()}
    out["blind_by_kind"] = {k: {"correct": a, "total": b, "accuracy": round(a / b, 4) if b else None}
                            for k, (a, b) in sorted(kinds.items(), key=lambda x: -x[1][1])}
    for c in COLLECTIONS:
        dist = Counter()
        qs = Counter()
        for r in load(c):
            if r.get("type") != "hadith":
                continue
            p = split(r)
            key = f"{p['method']}/{p['confidence'] or 'none'}"
            if p["matn"] is None and p["isnad"] is not None:
                key = f"{p['method']}/isnad-only"
            dist[key] += 1
            if p["method"] == "heuristic":
                qs[_heuristic(r.get("text") or "")[3]] += 1
        out["distribution"][c] = dict(sorted(dist.items()))
        out["quote_state"][c] = dict(sorted(qs.items()))
    for (mode, conf), xs in sorted(examples.items()):
        out["errors"][f"{mode}/{conf}"] = xs[:30]
    out["seconds"] = round(time.time() - t0, 1)
    return out


def _summarize(res):
    lines = [f"metric: start and end within {TOL} words of gold"]
    for mode in ("quotes", "blind"):
        lines.append(f"== gold, mode={mode}  (correct/total per confidence)")
        agg = {k: [0, 0] for k in CONFS}
        for c, d in res["gold"][mode].items():
            parts = []
            for k in CONFS:
                v = d[k]
                agg[k][0] += v["correct"]
                agg[k][1] += v["total"]
                acc = f" ({v['accuracy']:.3f})" if v["accuracy"] is not None else ""
                parts.append(f"{k}={v['correct']}/{v['total']}{acc}" if k != "none" else f"none={v['total']}")
            lines.append(f"  {c:9} " + "  ".join(parts))
        lines.append("  ALL       " + "  ".join(
            (f"{k}={a}/{b}" + (f" ({a / b:.3f})" if b else "")) if k != "none" else f"none={b}"
            for k, (a, b) in agg.items()))
    lines.append("== blind accuracy by rule: " + "  ".join(
        f"{k}={v['correct']}/{v['total']}" + (f" ({v['accuracy']:.3f})" if v["accuracy"] is not None else "")
        for k, v in res["blind_by_kind"].items()))
    tot = Counter()
    for d in res["distribution"].values():
        tot.update(d)
    n = sum(tot.values())
    lines.append(f"== distribution, 27 books, {n} hadith: " + "  ".join(
        f"{k}={v} ({v / n:.1%})" for k, v in sorted(tot.items())))
    lines.append(f"== gold matn not located in text: {res['source_unlocated']}")
    lines.append(f"== seconds: {res['seconds']}")
    return "\n".join(lines)


def main(argv):
    if "--eval" in argv:
        res = evaluate()
        b = ROOT / "build"
        b.mkdir(exist_ok=True)
        with open(b / "matn-eval.json", "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
        s = _summarize(res)
        enc = sys.stdout.encoding or "utf-8"
        print(s.encode(enc, "replace").decode(enc))
        print("written: build/matn-eval.json")
        return 0
    print("usage: python -I scripts/matn.py --eval")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
