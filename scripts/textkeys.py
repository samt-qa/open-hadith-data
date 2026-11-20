"""مفاتيح المقارنة (القسم 7). للمقارنة فقط، ولا تُخزَّن بدل النص (القاعدة 8)."""
import re
import unicodedata

MARKS = "ًٌٍَُِّْٰ"
TATWEEL = "ـ"
D = f"[{MARKS}{TATWEEL}]*"
ALIFS = "أإآٱ"
MARK_NAMES = {"ً": "فتحتان", "ٌ": "ضمتان", "ٍ": "كسرتان", "َ": "فتحة", "ُ": "ضمة",
              "ِ": "كسرة", "ّ": "شدة", "ْ": "سكون", "ٰ": "ألف خنجرية"}


def _loose(phrase: str) -> str:
    """نمط يطابق العبارة مع أي تشكيل، وأي صورة للألف والياء، ومسافات اختيارية."""
    out = []
    for ch in phrase:
        if ch == " ":
            out.append(r"\s*")
        elif ch in "اأإآٱ":
            out.append(f"[ا{ALIFS}]{D}")
        elif ch in "يى":
            out.append(f"[يى]{D}")
        else:
            out.append(re.escape(ch) + D)
    return "".join(out)


# صيغ الصلاة والترضّي: تُستبدل برمز موحّد لكل صيغة
HONORIFICS = [
    ("§ص§", re.compile("ﷺ|" + _loose("صلى الله عليه وعلى اله وسلم") + "|" + _loose("صلى الله عليه واله وسلم")
                       + "|" + _loose("صلى الله عليه وسلم"))),
    ("§ر-هم§", re.compile(_loose("رضى الله") + r"\s*(?:" + _loose("تعالى") + r")?\s*" + _loose("عنهم") + r"(?![ء-ي])")),
    ("§ر-هما§", re.compile(_loose("رضى الله") + r"\s*(?:" + _loose("تعالى") + r")?\s*" + _loose("عنهما"))),
    ("§ر-ها§", re.compile(_loose("رضى الله") + r"\s*(?:" + _loose("تعالى") + r")?\s*" + _loose("عنها"))),
    ("§ر-ه§", re.compile(_loose("رضى الله") + r"\s*(?:" + _loose("تعالى") + r")?\s*" + _loose("عنه") + r"(?![ء-ي])")),
    ("§س§", re.compile(_loose("عليه السلام") + "|" + _loose("عليه الصلاة والسلام"))),
]
# ترتيب مهم: عنهما قبل عنهم قبل عنه
HONORIFICS = [HONORIFICS[0], HONORIFICS[2], HONORIFICS[1], HONORIFICS[3], HONORIFICS[4], HONORIFICS[5]]
# صيغ أخرى تكتبها الشاملة حرفًا مركّبًا ويكتبها غيرها نصًّا (أُضيفت 2026-11-20 لمقابلة الشاملة)
HONORIFICS += [
    ("§س-هما§", re.compile(_loose("عليهما السلام"))),
    ("§س-هم§", re.compile(_loose("عليهم السلام"))),
    ("§س-ها§", re.compile(_loose("عليها السلام"))),
    ("§عج§", re.compile(_loose("عز وجل"))),
    ("§تت§", re.compile(_loose("تبارك وتعالى"))),
    ("§رح§", re.compile(_loose("رحمه الله") + r"(?:\s*" + _loose("تعالى") + ")?")),
]
# الحروف المركّبة (Unicode) ← صيغها النصية، قبل مطابقة الصيغ أعلاه
LIGATURES = str.maketrans({
    "ﷺ": " صلى الله عليه وسلم ", "﵀": " رحمه الله ", "﵁": " رضي الله عنه ",
    "﵂": " رضي الله عنها ", "﵃": " رضي الله عنهم ", "﵄": " رضي الله عنهما ",
    "﵅": " رضي الله عنهن ", "﵇": " عليه السلام ", "﵈": " عليهم السلام ",
    "﵉": " عليهما السلام ", "﵊": " عليه الصلاة والسلام ", "﵍": " عليها السلام ",
    "﵎": " تبارك وتعالى ", "﷿": " عز وجل ", "﷽": " بسم الله الرحمن الرحيم ",
})
PUNCT = re.compile(r"[^ء-غف-ي" + MARKS + r"§\-\s]")


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def char_skel(ch: str) -> str:
    if ch in MARKS or ch == TATWEEL:
        return ""
    if ch in ALIFS:
        return "ا"
    if ch == "ى":
        return "ي"
    return ch


def skel(word: str) -> str:
    return "".join(char_skel(c) for c in word)


def tokens(text: str) -> list[dict]:
    """كلمات النص: لكل كلمة صورتها الخام (بتشكيلها) ومفتاح هيكلها."""
    t = nfc(text.translate(LIGATURES))
    # الصيغة تُستبدل بعلامة مؤقتة تحفظ لفظها الأصلي: skel رمز الصيغة، و raw لفظها كما في النص
    found = []

    def hold(tok):
        def f(m):
            found.append((tok, m.group(0).strip()))
            return f" §{len(found) - 1}§ "
        return f

    for tok, rx in HONORIFICS:
        t = rx.sub(hold(tok), t)
    out = []
    for w in t.split():
        if w.startswith("§"):
            tok, orig = found[int(w.strip("§"))]
            out.append({"raw": orig, "skel": tok})
            continue
        w = PUNCT.sub("", w).replace(TATWEEL, "").replace("§", "").replace("-", "")
        if skel(w):
            out.append({"raw": w, "skel": skel(w)})
    return out


def skeleton_key(text: str) -> str:
    return " ".join(t["skel"] for t in tokens(text))


def letters(word: str) -> list[tuple[str, frozenset]]:
    """حروف الكلمة، كل حرف مع مجموعة حركاته (ترتيب الشدة والحركة لا يؤثر)."""
    out = []
    for ch in nfc(word):
        if ch in MARKS:
            if out:
                out[-1] = (out[-1][0], out[-1][1] | {ch})
        elif ch != TATWEEL:
            out.append((char_skel(ch), frozenset()))
    return out


def tashkeel_key(text: str) -> str:
    return " ".join(
        t["skel"] if t["skel"].startswith("§") else "".join(b + "".join(sorted(m)) for b, m in letters(t["raw"]))
        for t in tokens(text))


def l2_fold(s: str) -> str:
    """طيّ الفروق الإملائية (L2): صور الهمزة، ة/ه، وحذف الألف في الرسم القديم."""
    # كراسي الهمزة (مسئول/مسؤول، رءوس/رؤوس، شيأ/شيئا) تُطوى كلها، و«أن لا» = «ألا»
    s = s.replace("انلا", "الا").replace("يء", "ئ")
    return s.replace("ؤ", "").replace("ئ", "").replace("ء", "").replace("ة", "ه").replace("ا", "")
