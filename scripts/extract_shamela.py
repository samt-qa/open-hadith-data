"""استخراج نص كتاب من ملف الشاملة الخام (turath books-v3 JSON) إلى سجلات JSONL.

الاستعمال: python scripts/extract_shamela.py bukhari 1681

المدخل:  base/shamela/<id>/<id>.json   (لا يُعدَّل)
المخرج:  text/<collection>/<collection>.jsonl ، و text/<collection>/extract-stats.json

ما يفعله بالنص (تحويل صيغة فقط، لا تصحيح — القاعدة 8):
- يحذف وسوم HTML (روابط الرواة، وسوم المتن، مراسي الفهرس) ويحفظ ما فيها في حقول مستقلة
  (narrators، matn).
- يحذف علامات بداية الصفحة ⦗٧⦘ ويحوّلها إلى حقل loc.
- يحذف رقم الحديث («١ - »، «٣٧٥٦ (م) - ») ويحفظه في numbers.
- يفصل حواشي الشاملة (بعد الخط _________) وإحالاتها (^١) إلى حقل notes.
- يوحّد المسافات. لا يمسّ الحروف ولا التشكيل ولا الرموز (ﷺ ﵁ …).

تقسيم الأحاديث: رقم الحديث قد يقع في أول المدخل أو في وسطه (حديث عبد الباقي المقسوم)،
فيُقبل الرقم إذا جاء على تسلسل الترقيم (أكبر من السابق بخمسة على الأكثر) أو كان رقمًا فرعيًا (م).

أنواع السجلات: front، kitab، bab، hadith، other (نص بلا رقم بعد أول حديث).
"""
import json
import re
import sys
from collections import Counter
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AR = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

TITLE = re.compile(r'<span[^>]*data-type="title"[^>]*>(.*?)</span>', re.S)
EMPTY_SPAN = re.compile(r'<span[^>]*>\s*</span>')
PAGE_MARK = re.compile(r"⦗([٠-٩]+)⦘")
NARRATOR = re.compile(r'<a href="inr://man-(\d+)">(.*?)</a>', re.S)
MATN = re.compile(r"<hadeeth-\d+>(.*?)<hadeeth>", re.S)
TAG = re.compile(r"<[^>]+>")
NOTE_REF = re.compile(r"\(\^[٠-٩0-9]+\)")
SEP = "_________"
# <hr> فاصل حواشٍ إن تلاه قوس («(تعليق الشاملة)»، «(^١)»)؛ وقد يسبق حديثًا من هامش المطبوع فلا يُقطع عنده
# النسائي 829: «<hr> <span title>(تعليق الشاملة)</span>» عنوان فوق الحواشي لا كتاب
SEP_RX = re.compile(r"_{9,}|<hr\s*/?>(?=\s*(?:[(\[]|<span[^>]*>\s*\(تعليق))")
# شاهدا مسلم 1727 والبخاري 735: كل <hr> فاصل الحواشي (شرح المحقق يبدأ أحيانًا بلا قوس)
SEP_ANY_HR = re.compile(r"_{9,}|<hr\s*/?>")
# حكم الألباني بعد الحديث (أبو داود 1726، ابن ماجه 1198): يُحفظ في حقل grades لا في النص
GRADE_RX = re.compile(r"^\s*\[حكم الألباني\]\s*:?\s*(.+?)\s*$", re.S)
INLINE_GRADE = re.compile(r"\[حكم الألباني\]\s*:?\s*\n?([^\n]+)")
# مسند أحمد 25794: حاشية الحكم تبدأ بلفظ حكم («إسناده صحيح على شرط الشيخين.») ← أول جملة إلى grades.arnaout
AHMAD_MARKS = {"•": "zawaid_abdullah", "°": "wijadat_abdullah", "*": "abdullah_from_father_or_shaykh"}
# طبعتا الأرنؤوط (الرسالة) شاهدين ثانيين: أبو داود 117359، ابن ماجه 98138 — حواشٍ بعد «_________» على طريقة مسند أحمد
ARNAOUT_W = {117359, 98138}
# طبعات الرسالة بحواشٍ «(^N)» وتتمات «=» على طريقة الأرنؤوط: الشاهدان أعلاه، والمستدرك ط الرسالة 1424 (أساس)
RISALA_FN = ARNAOUT_W | {1424}
AHMAD_GRADE = re.compile(r"\s*((?:إسناد|حديث|صحيح|حسن|ضعيف|رجاله|أثر|مرفوع|المرفوع|موضوع|منكر|مرسل|خبر)[^.\n]*)")
# مصنف ابن أبي شيبة ت الشثري 333: حكم المحقق في الحاشية إلى أول «؛» أو «،» أو «.»
SHATHRI_GRADE = re.compile(r"\s*((?:صحيح|حسن|ضعيف|منقطع|مرسل|معضل|موقوف|مقطوع|إسناده|منكر|موضوع|شاذ|مضطرب"
                           r"|مجهول|متروك|فيه|ضعفه|في إسناده|رجاله)[^؛،.:\n]*)")
# مصنف عبد الرزاق 13174: أول الحديث مصفوف قبل رقمه (يُطابَق بلا تشكيل)
# مسند أبي يعلى ت السناري 181: حكم المحقق أول سطر التخريج قبل «:» («صحيح:»، «ضعيف بهذا التمام:»، «قوى لغيره:»)
SINARI_GRADE = re.compile(r"\s*((?:صحيح|صحيج|ضعيف|صعيف|حسن|منكر|قوى|قوي|باطل|جيد|موضوع|شاذ|مرسل|منقطع|معضل|موقوف|مقطوع"
                          r"|ساقط|واه|تالف|صالح|إسناده|المرفوع|الموقوف)[^:؛.\n]{0,60})[:؛.]")
RAZZAQ_LEAD = re.compile(r"[،\s]*(?:[٠-٩]\s+)?(?:أخبرنا|عبد\s*الرزاق|الرزاق[،\s])")
_M = "[ً-ْٰ]*"
_tol = lambda w: _M.join(w) + _M  # الكلمة بتشكيل اختياري بين حروفها
# «عَبْدُ الرَّزَّاقِ،» (بفاصلة) أو «أَخْبَرَنَا» في آخر نص الحديث السابق قبل رقم التالي (لا «وبه يأخذ عبد الرزاق» بلا فاصلة)
RAZZAQ_TRAIL = re.compile(r"(?<=[\s»\"؛.،;:)\]])(?:" + _tol("أخبرنا") + r"\s*)?(?:" + _tol("عبد") + r"\s*" + _M + r"\s*"
                          + _tol("الرزاق") + r"|" + _tol("أخبرنا") + r")[\s،.,]*(?:⦗[٠-٩]+⦘\s*)*$")
RAZZAQ_LEAD_LINE = re.compile(r"[،\s]*(?:[٠-٩]\s+)?(?:أخبرنا\s*)?(?:عبد\s*)?(?:الرزاق)?[،.\s]*")
VERSE_REF = re.compile(r"\s*\[[^\]\[\n]{2,25}:\s*[٠-٩]+(?:\s*[-–،,]\s*[٠-٩]+)*\]")
# رقم حديث: في أول المدخل أو بعد سطر جديد أو وسم أو مسافة؛ مع لاحقة فرعية اختيارية (م) أو (م ١)
MARK = re.compile(r"(?:(?<=^)|(?<=[\s>\]]))([٠-٩]+)\s*(\((م[^)]*)\))?\s*-\s*(\((م[^)]*)\)\s*)?(?=\S)")
# مسلم (طبعة 711): «٥٩ - (٣٦) » أو «٢٥ - (١٦٩٧/ ١٦٩٨) » أو «• » في أول السطر
MARK_MUSLIM = re.compile(r"(?:(?<=^)|(?<=\n))\s*(?:(?:([٠-٩]+)\s*-\s*)?\(([٠-٩]+(?:\s*/\s*[٠-٩]+)*)\)|•)\s*")
# إعدادات كل كتاب: طريقة التقسيم
PROFILES = {"muslim": "muslim"}
# معاجم الطبراني (الزيادات): الكبير 1733 (ت السلفي)، الأوسط 28171، الصغير 13068
TABARANI = {"tabaranikabir", "tabaraniawsat", "tabaranisaghir"}


def misprint_of(printed: int, expected: int) -> bool:
    """رقم مطبوع خطأً مكان المتوقع: حرف ساقط، أو حرف مختلف، أو حرفان متبادلان (مسند أحمد ت شاكر)."""
    a, b = str(printed), str(expected)
    if len(a) == len(b):
        d = [i for i in range(len(a)) if a[i] != b[i]]
        return len(d) == 1 or (len(d) == 2 and d[1] == d[0] + 1 and a[d[0]] == b[d[1]] and a[d[1]] == b[d[0]])
    if len(a) == len(b) - 1:
        return any(b[:i] + b[i + 1:] == a for i in range(len(b)))
    if len(a) == len(b) + 1:  # رقم زائد («٢٩٥٨٢» مكان ٢٩٥٨)
        return any(a[:i] + a[i + 1:] == b for i in range(len(a)))
    return False


def seq_misprints(pages, start=0, skip=lambda p: False):
    """مسند البزار 12981 ومسند أبي يعلى ت السناري 181: أرقام الأحاديث في أول السطر (قبل فاصل الحواشي) بترتيب الملف؛
    الرقم مصحَّف مكان المتوقع (السابق + 1) إن شهد له جاره: التالي هو السابق + 2 («٤٣٠٩، ٣٤١٠، ٤٣١١»، «٣٧٨٨» مكررًا قبل ٣٧٩٠)،
    أو كان تصحيفًا في الشكل (misprint_of) والذي بعد التالي هو السابق + 3 (تصحيفان متتاليان «٦٧٥١، ٦٧٥٢» مكان ٦٧٠١، ٦٧٠٢).
    ← {(رقم المدخل، الرقم المطبوع): [المتوقع أو None لكل ورود بالترتيب]}. الفجوة الحقيقية («٢٠١٨ ثم ٢٠٢٢، ٢٠٢٣») لا يشهد لها الجار فتبقى."""
    seq = []
    for idx, p in enumerate(pages):
        if idx < start or skip(p):
            continue
        body = re.split(r"_{9,}|<hr", p["text"], maxsplit=1)[0]
        for m in re.finditer(r"(?:^|\n)[ \t]*([٠-٩]+)[ \t]*-", body):
            seq.append((idx, int(m.group(1).translate(AR))))
    fix, prev = {}, 0
    for i, (idx, n) in enumerate(seq):
        nx = seq[i + 1][1] if i + 1 < len(seq) else None
        nx2 = seq[i + 2][1] if i + 2 < len(seq) else None
        # أو خرج عن ترتيب جاريه والفرق بينهما يتسع له («٢٥١٥، ٢٥٥٥، ٢٥١٨» ← ٢٥١٦)
        if n != prev + 1 and prev and (nx == prev + 2 or (misprint_of(n, prev + 1) and nx2 == prev + 3)
                                       or (nx is not None and nx - prev >= 2 and not prev < n < nx)):
            fix.setdefault((idx, n), []).append(prev + 1)
            prev += 1
        else:
            fix.setdefault((idx, n), []).append(None)
            prev = n
    return fix


def clean(s: str) -> str:
    s = PAGE_MARK.sub(" ", s)
    s = TAG.sub("", s)
    s = unescape(s)  # كيانات HTML في الملف («&quot;» علامة تنصيص) ← حروفها؛ بعد حذف الوسوم لئلا يُقرأ «&lt;» وسمًا
    s = NOTE_REF.sub("", s)
    s = re.sub(r"^[\s.]+$", "", s, flags=re.M)  # أسطر النقاط (مكان نص في الهامش)
    s = re.sub(r"[ \t ]+", " ", s)
    s = re.sub(r" *\n *", "\n", s)
    s = re.sub(r"\n{2,}", "\n", s)
    return s.strip()


def level_of(span_html: str) -> int:
    m = re.search(r'data-level="(\d)"', span_html)
    return int(m.group(1)) if m else 2


class Extractor:
    def __init__(self, collection, book_id, toc_top=None):
        self.collection, self.book_id = collection, int(book_id)
        self.fixes, self.fixes_applied = {}, []  # إصلاحات المالك في الملف الخام: {رقم المدخل: [إصلاح]}
        self.profile = PROFILES.get(collection, "seq")
        self.toc_top = toc_top or {}  # رقم المدخل ← عناوين المستوى الأول في فهرس الشاملة
        self.toc_bab = {}  # رقم المدخل ← أرقام الأبواب «(N)» من المستوى الثاني (ابن ماجه)
        self.records, self.stats = [], Counter()
        self.kitab = {"n": 0, "title": None}
        self.bab = {"n": 0, "title": None}
        self.last_num = 0
        self.used = set()
        self.seen_hadith = False
        self.current = None  # آخر سجل يُلحق به نص لاحق في المدخل نفسه
        self.body_end = 10 ** 9  # الموطأ 28107: أول مدخل بعد آخر كتاب (تراجم الرجال)
        self.azami_k = {}  # الموطأ 28107: الرقم العام ← عدّاد الأحاديث «٤/ ١»
        self.body_start = 0  # مسند أحمد: أول مدخل بعد المقدمات (ما قبله مقدمة لا أحاديث)
        self.last_note = None  # مسند أحمد: (السجل، موضع الحاشية) لتتمة الحاشية في الصفحة التالية
        self.misprints = {}  # مسند أحمد ت شاكر 98139: الرقم المتوقع ← الرقم كما طُبع خطأً
        self.ahmad_marks = {}  # مسند أحمد: رقم الحديث ← رمز الطبعة (زيادات عبد الله…)
        self.series = None  # المعجم الكبير 1733: الجزء الذي يبدأ فيه ترقيم جديد (١٣ و١٧ فما بعده)
        self.toc_levels = []  # الطبراني: مستوى كل عنوان في فهرس الشاملة (وسم «toc-N» = العنصر N من الفهرس)
        self.kh_grades = []  # ابن خزيمة 1446: تعليقات المحقق «<s0>» بترتيب ورودها (علامتها ⁅G k⁆ في النص)
        self.hb_dups = []  # ابن حبان 1729: المكرر المبتور قبل «[N]» (علامته ⁅D k⁆ في النص)
        self.tasil_kind = {}  # مصنف عبد الرزاق ط التأصيل 84: رقم الحديث ← مرفوع (°) أو موقوف (•)
        self.pre_fix, self._idx = {}, None  # البزار 12981 وأبو يعلى 181: الأرقام المصحَّفة (seq_misprints)، والمدخل الجاري

    def new(self, rtype, raw, vol, page, entry, numbers=None, title=None, margin=False):
        loc = [{"juz": vol, "page": page}]
        rec = {"seq": len(self.records) + 1, "type": rtype, "collection": self.collection,
               "source": {"shamela": self.book_id, "entry": entry}}
        if numbers:
            rec["numbers"] = numbers
        if rtype in ("bab", "hadith", "other"):
            rec["kitab"] = dict(self.kitab)
            rec["bab"] = dict(self.bab)
        if title is not None:
            rec["title"] = title
        if margin:
            rec["from_margin"] = True
        rec["loc"] = loc
        rec["_raw"] = ""
        self.records.append(rec)
        self.stats[rtype] += 1
        self.current = rec
        self.append(raw)
        return rec

    def append(self, raw):
        rec = self.current
        juz = rec["loc"][0]["juz"]
        for m in PAGE_MARK.finditer(raw):
            pg = int(m.group(1).translate(AR))
            if pg != rec["loc"][-1]["page"]:
                rec["loc"].append({"juz": juz, "page": pg})
        rec["_raw"] += raw

    def body(self, html, vol, page, entry, margin=False):
        """نص بلا عناوين: يقسَّم عند أرقام الأحاديث المقبولة."""
        if self.collection == "ahmad":
            # مسند أحمد 25794: «الملحق المستدرك من مسند الأنصار» يرقّم أحاديثه «. . /N - » بلا رقم في المسند
            # ← سجل حديث بلا رقم مطبوع، ورقمه في الملحق في numbers.mulhaq
            parts = re.split(r"(?:^|\s)(?:\.\s*){2,}/\s*([٠-٩]+)\s*-\s*", html)
            if len(parts) > 1:
                groups, cuts = self.seq_cuts(parts[0])
                self.split(parts[0], groups, cuts, vol, page, entry, margin)
                for k in range(1, len(parts), 2):
                    self.new("hadith", parts[k + 1], vol, page, entry,
                             numbers={"printed": [], "mulhaq": int(parts[k].translate(AR))})
                    self.seen_hadith = True
                return
        if self.profile == "muslim":
            groups = self.muslim_cuts(html)
            cuts = bool(groups)
        else:
            groups, cuts = self.seq_cuts(html)
        self.split(html, groups, cuts, vol, page, entry, margin)

    def muslim_cuts(self, html):
        """مسلم (711): كل «رقم - (رقم عبد الباقي)» في أول سطر بداية حديث، ولو تكرر الرقم
        (الطبعة تكرره لكل إسناد)؛ و«•» في أول السطر بداية خبر بلا رقم (في المقدمة)."""
        groups = []
        for m in MARK_MUSLIM.finditer(html):
            if m.group(2):  # «(٢٢٤)» بلا رقم تسلسلي: printed فارغة
                nums = {"printed": [int(m.group(1).translate(AR))] if m.group(1) else [],
                        "abd_al_baqi": re.sub(r"\s", "", m.group(2)).translate(AR)}
            else:
                nums = {"printed": [], "unnumbered": True}
            groups.append((m, nums, m))
        return groups

    def seq_cuts(self, html):
        cuts = []
        for m in MARK.finditer(html):
            n = int(m.group(1).translate(AR))
            sub = m.group(3) or m.group(5)
            at_start = not clean(html[:m.start()])
            if self.book_id == 9647 and not re.search(r"(?:^|\n)[^\S\n]*$", html[:m.start(1)]):
                # الأدب المفرد ت الزهيري: رقم الحديث في أول السطر فقط؛ «٢٣- ب…» في سطر التخريج ليس حديثًا
                continue
            if (self.collection in ("tahawi", "nasaikubra") and not sub and self.last_num + 5 < n <= self.last_num + 20
                    and re.search(r"(?:^|\n)[^\S\n]*$", html[:m.start(1)])):
                # الطحاوي 21108: قفزة في ترقيم المطبوع داخل المدخل («٢٧٧٠» ثم «٢٧٨٠») في أول سطر ← يُقبل ويتابع منه
                at_start = True
            if (self.collection in ("tahawi", "nasaikubra") and not sub and self.last_num - 10 <= n < self.last_num
                    and n not in self.used and re.search(r"(?:^|\n)[^\S\n]*$", html[:m.start(1)])):
                # الطحاوي 21108: رقم أصغر لم يُستعمل في أول سطر («٦٢٤» ثم «٦٢٣») ← حديث برقمه كما طُبع
                at_start = True
            if (self.collection == "adabmufrad" and at_start and n == self.last_num and not sub
                    and self.current is not None and self.current["type"] == "bab"):
                # الأدب المفرد 12991: الرقم نفسه مطبوع لحديثين متتاليين بعد عنوان باب (٢٧٠، ١٠٠١) ← سجل حديث بالرقم كما طُبع
                cuts.append((m, n, sub))
                continue
            if sub:
                ok = n == self.last_num or at_start
            elif self.last_num < n <= self.last_num + 5:
                ok = True
            else:
                # ترقيم عبد الباقي لا يتبع ترتيب المطبوع دائمًا (٣٥٢٨ بعد ٣٥١٦ ثم ٣٥٢٢):
                # يُقبل الرقم في أول المدخل فقط، إن لم يُستعمل، وكان قريبًا من السابق
                ok = at_start and n not in self.used and abs(n - self.last_num) <= 50
                # النسائي 829: الرقم نفسه يُعاد في أول مدخل تالٍ (٣٥٣٣ ثلاثًا، ٢٨٢١، ٥٥٦٤) ← سجل حديث بالرقم نفسه
                # (والموطأ 1699 كذلك: ١٣ ثلاثًا في الحج، ٤٨، ١٤، ٣٧…)
                # (والطحاوي 21108: ١٣١، ٣٩٤، ٤٩٠، ٢١١٢… رقم مكرر لروايتين)
                if self.collection in ("nasai", "malik", "tahawi", "nasaikubra") and at_start and n == self.last_num:
                    ok = True
                # مسند أبي يعلى ت حسين أسد 12520: رقم الحديث السابق مطبوعًا ثانيةً في أول مدخل تالٍ لحديث آخر بالإسناد نفسه
                # («١٣٨٦ - وَعَنْ أَبِي سَعِيدٍ…»، و٧٤٤٠ أربع مرات) ← سجل حديث بالرقم كما طُبع (يظهر في duplicate_numbers)
                if self.book_id == 12520 and at_start and n == self.last_num:
                    ok = True
                # الدارمي 21795: رقم في أول المدخل يُعاد (١٢١٢ مرتين…) أو خطأ مطبعي (٦٧٢ مكان ٦٩٩) ← سجل حديث برقمه كما طُبع
                if self.collection == "darimi" and at_start and abs(n - self.last_num) <= 50:
                    ok = True
                # ابن حبان 1729: الترقيم عام متسلسل وفي ملف الشاملة فجوات (٥٦١ ثم ٦٠٧) وأرقام مقدَّمة أو مكررة
                # (١٤٧١ ثم ١٤٦١، و٧٩٠ مرتين) ← كل «N - » في أول السطر رقم حديث، ما لم يُستعمل (إلا تكرار السابق مباشرة)
                if (self.book_id == 1729 and not sub and abs(n - self.last_num) <= 200
                        and (n not in self.used or n == self.last_num)
                        and re.search(r"(?:^|\n)[^\S\n]*$", html[:m.start(1)])):
                    ok = True
                    self.last_num = max(self.last_num, n)
                # مسند أحمد ت شاكر 98139: رقم مصحَّف في أول السطر مكان التالي المتوقع («٤١٦» مكان ٤٩٦، «٢٤٨» مكان ٢٠٤٨)
                # ← يُقبل بالرقم المتوقع، ويُحفظ ما طُبع في numbers.printed_as
                # (لا يُعدّ تصحيفًا تكرارُ الرقم السابق أو رقمٌ مستعمل قريب من المتوقع: ذلك تكرار طبعة لا تصحيف)
                # (والطحاوي 21108: «٦٢٣» ثانيةً مكان ٦٢٥، «٣٠٥٠» مكان ٣٠٥٥)
                if ((self.book_id == 98139 or self.collection == "tahawi") and not ok and not sub and n != self.last_num
                        and (self.collection == "tahawi" or not (n in self.used and abs(n - self.last_num - 1) <= 5))
                        and re.search(r"(?:^|\n)[^\S\n]*$", html[:m.start(1)]) and self.last_num + 1 not in self.used
                        and misprint_of(n, self.last_num + 1)):
                    self.misprints[self.last_num + 1] = n
                    n, ok = self.last_num + 1, True
                # مسند الطيالسي 1456: رقم مقلوب الأرقام في أول المدخل مكان التالي المتوقع («٥٧٤» مكان ٤٧٥)
                # ← يُقبل بالرقم المتوقع، ويُحفظ ما طُبع في numbers.printed_as (عيب مصدر يُعرض على المالك)
                if (self.collection == "tayalisi" and not ok and not sub and at_start
                        and self.last_num + 1 not in self.used
                        and (sorted(str(n)) == sorted(str(self.last_num + 1)) or misprint_of(n, self.last_num + 1))):
                    self.misprints[self.last_num + 1] = n
                    n, ok = self.last_num + 1, True
                # الدارمي ت الزهراني 36114: «رقم - (رقم الباب)» في أول السطر (معلَّم بـ U+2063) حديث مهما كان رقمه
                if self.book_id in (36114, 28107, 84) and html[m.end():m.end() + 1] == "⁣":
                    ok = True
                    self.last_num = n
                # معاجم الطبراني: رقم في أول السطر بعد فجوة في الترقيم (أرقام ساقطة من المطبوع: ١١٤٤ ثم ١١٥٠،
                # ١٠٤٨٤ ثم ١٠٤٩٣) ← يُقبل ويصير هو الرقم الجاري، لئلا تُرفض الأرقام بعده
                if (self.collection in TABARANI and not ok and not sub and self.last_num < n <= self.last_num + 300
                        and n not in self.used and re.search(r"(?:^|\n)\s*$", TAG.sub("", html[:m.start(1)]))):
                    ok = True
                    self.last_num = n
            if ((self.collection == "bazzar" or self.book_id == 181) and not sub
                    and re.search(r"(?:^|\n)[^\S\n]*$", TAG.sub("", html[:m.start(1)]))):
                # مسند البزار 12981 ومسند أبي يعلى ت السناري 181: رقم في أول السطر
                occ = self.pre_fix.get((self._idx, n))  # ورود الرقم في المدخل بالترتيب
                exp = occ.pop(0) if occ else None
                if exp is not None and exp not in self.used:
                    # مصحَّف يشهد له جاره (seq_misprints) ← يُقبل بالرقم المتوقع، وما طُبع في numbers.printed_as
                    self.misprints[exp] = n
                    n, ok = exp, True
                elif self.last_num + 5 < n <= self.last_num + 300 and n not in self.used:
                    # فجوة في ترقيم المطبوع (البزار: ١١٧٠ آخر الجزء ٣ ثم ١١٩٤ أول الجزء ٤) ← يُقبل ويصير الرقم الجاري
                    ok = True
                    self.last_num = n
                elif not ok and n == self.last_num:
                    # الرقم نفسه مطبوع لحديثين متتاليين (البزار ٢٣١٢، ٧٣٤٧، ٨٥٤١) ← سجل حديث بالرقم كما طُبع
                    ok = True
                elif not ok and self.last_num - 5 <= n < self.last_num and n not in self.used:
                    # رقم أصغر لم يُستعمل بعد صفحة مقدَّمة في الملف (السناري: ص ٤٩٥ فيها ٢٠٦٢ قبل ص ٤٩٦ وفيها ٢٠٦٠، ٢٠٦١)
                    # ← حديث برقمه كما طُبع، في موضعه من الملف
                    ok = True
            if self.book_id == 333 and html[m.end():m.end() + 4] == "[*m]":
                # مصنف ابن أبي شيبة 333: رقم مطبوع خطأً «(N) [*]» (انظر entry) ← حديث برقمه، خارج التسلسل:
                # لا يدخل used ولا يحرّك last_num، فيبقى الرقم الصحيح نفسه مقبولًا في موضعه
                self.misprints[m.start()] = n
                cuts.append((m, n, sub))
                continue
            if ok:
                cuts.append((m, n, sub))
                if not sub:
                    self.used.add(n)
                    if self.last_num < n <= self.last_num + 5 or (
                            # الطحاوي 21108 والكبرى 8361: قفزة في ترقيم المطبوع (٢٤٢٩ ← ٢٤٥٠) في أول المدخل ← يتابع التسلسل منها
                            self.collection in ("tahawi", "nasaikubra") and at_start and n > self.last_num):
                        self.last_num = n
                        while self.last_num + 1 in self.used:  # تجاوز ما سبق قبوله خارج الترتيب
                            self.last_num += 1
        # أرقام متتالية بلا نص بينها («٤٠٨ - ٤٠٩ - حدثنا») = سجل واحد بعدة أرقام
        groups = []
        for m, n, sub in cuts:
            if groups and not html[groups[-1][0].end():m.start()].strip() and not sub and not groups[-1][2]:
                groups[-1] = (m, groups[-1][1] + [n], None, groups[-1][3])
            else:
                groups.append((m, [n], sub, m))
        out = []
        for m, ns, sub, first in groups:
            nums = {"printed": ns}
            if sub:
                nums["sub"] = sub.strip()
            if self.book_id == 333 and self.misprints.pop(first.start(), None) is not None:
                nums["misprint"] = True  # «كذا الرقم بالمطبوع، وهو غلط» (مُعِدّ الشاملة)
            if (self.book_id in (98139, 181) or self.collection in ("tayalisi", "tahawi", "bazzar")) and not sub and ns[0] in self.misprints:
                nums["printed_as"] = self.misprints[ns[0]]
            if (self.book_id == 1733 or self.collection == "bazzar") and self.series is not None:
                nums["series"] = self.series  # الكبير: الجزء الذي بدأ فيه الترقيم من جديد
            out.append((m, nums, first))
        return out, cuts

    def split(self, html, groups, cuts, vol, page, entry, margin):
        pos = 0
        for m, nums, first in groups:
            before = html[pos:first.start()]
            bare = lambda s: re.sub(r"[ً-ْٰ\s،,:]", "", s)
            if (self.collection == "humaydi" and clean(before) and self.current is not None
                    and self.current["type"] == "top" and self.current.get("title_from") == "shamela_toc"
                    and "\n" not in clean(before).strip()
                    and bare(self.current["title"]).startswith(bare(clean(before)))):
                # الحميدي 8493: عنوان المسند سطرًا بلا وسم قبل أول حديث، وعنوان الفهرس فيه العنوان ثم أول الحديث
                # («أحاديث زيد بن أرقم ﵁ حدثنا الحميدي…») ← عنوان الكتاب هو السطر
                self.current["title"] = clean(before).strip()
                self.current["title_from"] = "text"
                before = ""
            lead = ""
            if self.book_id == 13174 and clean(before):
                # مصنف عبد الرزاق 13174: أول الحديث («عَبْدُ الرَّزَّاقِ،» أو «أَخْبَرَنَا») مصفوف في الملف قبل رقمه
                # («عَبْدُ الرَّزَّاقِ،\n\n٧٤٤٤ - عَنِ الثَّوْرِيِّ…») ← بداية الحديث التالي لا ذيل السابق:
                # ما قبل أول رقم في المدخل إن بدأ بها، أو سطرها الأخير وحده إن كان هو الصيغة فقط
                bare = lambda s: re.sub(r"[ً-ْٰ]", "", clean(s))
                if pos == 0 and RAZZAQ_LEAD.match(bare(before)):
                    lead, before = before, ""
                else:
                    mm = re.search(r"\n([^\n]*?)(\s*(?:⦗[٠-٩]+⦘\s*)*)$", "\n" + before)
                    tm = RAZZAQ_TRAIL.search(before)
                    if mm and re.search("أخبرنا|الرزاق", bare(mm.group(1))) and RAZZAQ_LEAD_LINE.fullmatch(bare(mm.group(1))):
                        k = len(before) - len(mm.group(0)) + 1
                        before, lead = before[:k], before[k:]
                    elif tm and not re.search(r"(?:يأخذ|قول)\s*$", bare(before[:tm.start()])):
                        # في آخر السطر (لا «وبه يأخذ عبد الرزاق» و«قول عبد الرزاق»، فهما من الكلام) بعد نص الحديث السابق («…قَبْلَ أَنْ يُسَلِّمَ» عَبْدُ الرَّزَّاقِ،»)
                        before, lead = before[:tm.start()], before[tm.start():]
                lead = re.sub(r"\s+", " ", lead).strip() + " " if lead else ""
            if clean(before):
                if (self.book_id == 13174 and pos == 0 and self.current is not None
                        and self.current["type"] in ("hadith", "other") and self.current["source"]["entry"] != entry):
                    # تتمة الحديث السابق (من مدخل قبله) قبل أول رقم (قول معمر أو ابن جريج…) ← تُلحق به في سطر جديد
                    self.append("\n" + before)
                elif self.current is not None and self.current["type"] not in ("kitab", "top") and not (
                        self.current["type"] == "bab" and self.current["_raw"] and pos == 0 and False):
                    self.append(before)
                else:
                    self.new("other" if self.seen_hadith else "front", before, vol, page, entry)
            self.seen_hadith = True
            self.new("hadith", lead, vol, page, entry, numbers=nums, margin=margin)
            pos = m.end()
        rest = html[pos:]
        if clean(rest):
            if self.current is None:
                self.new("front", rest, vol, page, entry)
            elif (self.book_id == 9771 and self.current["type"] == "hadith" and self.current["source"]["entry"] != entry
                  and (not (mm := re.match(r"\s*([٠-٩]+)\s*-\s*", TAG.sub("", rest)))
                       or [int(mm.group(1).translate(AR))] == self.current["numbers"]["printed"])):
                # سنن الدارقطني 9771: المدخل في ملف الشاملة إسناد أو تتمة، فما جاء بلا رقم أو بتكرار رقم الحديث
                # نفسه («٢٩٦١ -» أربع مرات) يُلحق بالحديث قبله، ويُحذف الرقم المكرر
                if mm:
                    rest = re.sub(r"^((?:<[^>]+>|\s)*)[٠-٩]+\s*-\s*", r"\1", rest, count=1)
                    nums = self.current["numbers"]
                    nums["repeated_in_source"] = nums.get("repeated_in_source", 0) + 1
                self.append("\n" + rest)
            elif self.book_id == 2266 and self.current["type"] == "hadith":
                # المستدرك ط العلمية 2266 (شاهد): المدخل حديث، وما فيه بلا رقم تتمة الحديث قبله
                self.append(rest)
            elif (self.book_id == 21795 and not cuts and self.current["source"]["entry"] != entry
                  and self.current["type"] == "hadith"):
                # الدارمي 21795 (قرار المالك 2026-11-20): الفقرة بلا رقم تتمة الحديث قبلها، كما يشهد ت الزهراني 36114.
                # سطر جديد قبلها لئلا تلتصق بسطر حكم المحقق فتُنقل معه إلى grades
                self.append("\n" + rest)
            elif (self.collection == "humaydi" and not cuts and self.current["source"]["entry"] != entry
                  and self.current["type"] == "hadith"
                  and (mm := re.match(r"\s*([٠-٩]+)\s*-\s*", TAG.sub("", rest)))
                  and [int(mm.group(1).translate(AR))] == self.current["numbers"]["printed"]):
                # مسند الحميدي 8493: فقرة الحديث في مدخل مستقل تحمل رقم الحديث نفسه («٨ - ثم شهدت العيد…») ← تتمته
                self.append("\n" + re.sub(r"^\s*[٠-٩]+\s*-\s*", "", rest))
            elif (self.collection in ("humaydi", "tayalisi") and not cuts and self.current["type"] == "top"
                  and self.current.get("title_from") == "shamela_toc" and not self.current["_raw"].strip()
                  and re.sub(r"[ً-ْٰ\s،,]", "", clean(rest)) == re.sub(r"[ً-ْٰ\s،,]", "", self.current["title"])):
                # الحميدي 8493: عنوان المسند في المتن سطرًا بلا وسم يكرر عنوان الفهرس ← هو عنوان الكتاب (بتشكيل المتن)
                self.current["title"] = clean(rest).strip()
                self.current["title_from"] = "text"
            elif (self.collection in ("humaydi", "tayalisi") and not cuts and self.current["source"]["entry"] != entry
                  and self.current["type"] in ("kitab", "top", "hadith") and len(clean(rest)) < 90
                  and not re.match(r"\s*(?:و?قال|و?حدثنا|و?أخبرنا)", re.sub(r"[ً-ْٰ]", "", clean(rest)))):
                # الحميدي 8493 والطيالسي 1456: ترجمة مسند صحابي أو راوٍ عنه سطرًا بلا وسم
                # («أَحَادِيثُ زَيْدِ بْنِ أَرْقَمَ ﵁»، «صَالِحٌ مَوْلَى التَّوْأَمَةِ عَنْ أَبِي هُرَيْرَةَ») ← باب، والبسملة قبلها في نصه
                lines = [x for x in clean(rest).split("\n") if x.strip()]
                if lines and not re.fullmatch(r"بسم الله الرحمن الرحيم", re.sub(r"[ً-ْٰ]", "", lines[-1]).strip()):
                    t = lines[-1].strip()
                    self.bab = {"n": self.bab["n"] + 1, "title": t}
                    self.new("bab", "\n".join(lines[:-1]), vol, page, entry, title=t)
                    self.current["title_from"] = "plain_line"
                else:
                    self.new("other", rest, vol, page, entry, margin=margin)
            elif (self.collection == "tayalisi" and not cuts and self.current["source"]["entry"] != entry
                  and self.current["type"] == "hadith"
                  and re.match(r"\s*(?:و?قال|و?حدثنا|و?أخبرنا)", re.sub(r"[ً-ْٰ]", "", clean(rest)))):
                # مسند الطيالسي 1456: إسناد آخر أو قول أبي داود في مدخل مستقل بلا رقم («قال أبو داود: وقال همام…»،
                # «حدثنا يونس قال: وحدثني…… بمثله») ← تتمة الحديث قبله
                self.append("\n" + rest)
            elif self.book_id == 148486 and self.current["type"] in ("hadith", "other", "bab"):
                # البيهقي ت التركي 148486: المدخل صفحة مطبوعة، وما في أولها بلا رقم تتمة الحديث (أو نص الباب) قبله
                self.append(rest)
            elif (self.book_id == 7861 and not cuts and self.current["source"]["entry"] != entry
                  and self.current["type"] in ("hadith", "other", "bab")):
                # البيهقي ط العلمية 7861 (شاهد): المدخل فقرة؛ الفقرة بلا رقم (إسناد آخر، «وروينا عن…»، قول البيهقي)
                # تتمة ما قبلها، والفقرة التي تحمل رقم الحديث الجاري نفسه («١١٠٧٤ - قال: …») تتمته ويُحذف الرقم المكرر
                mm = re.match(r"\s*([٠-٩]+)\s*-\s*", TAG.sub("", rest))
                if (mm and self.current["type"] == "hadith"
                        and [int(mm.group(1).translate(AR))] == self.current["numbers"]["printed"]):
                    rest = re.sub(r"^((?:<[^>]+>|\s)*)[٠-٩]+\s*-\s*", r"\1", rest, count=1)
                    self.stats["w_repeated_number"] += 1
                self.append("\n" + rest)
            elif (self.book_id == 13174 and not cuts and self.current["type"] == "bab"
                  and RAZZAQ_LEAD.match(re.sub(r"[ً-ْٰ]", "", clean(rest)))):
                # مصنف عبد الرزاق 13174: رواية بلا رقم أول الباب («عَبْدُ الرَّزَّاقِ، عَنْ مَعْمَرٍ…») ← سجل حديث بلا رقم
                self.seen_hadith = True
                self.new("hadith", rest, vol, page, entry, numbers={"printed": [], "unnumbered": True}, margin=margin)
            elif (self.book_id == 13174 and not cuts and self.current["source"]["entry"] != entry
                  and self.current["type"] in ("hadith", "other")):
                # مصنف عبد الرزاق 13174: كل فقرة مدخل، فالفقرة بلا رقم («قَالَ: وَسَمِعْتُهُ يَقُولُ…»، «قَالَ مَعْمَرٌ…»)
                # تتمة الحديث قبلها ← تُلحق به في سطر جديد
                self.append("\n" + rest)
            elif cuts or self.current["source"]["entry"] == entry or (
                    # النسائي 829: تتمة الحديث في مدخل مستقل («قال قتادة…»، «وعن أبي صالح…»)؛ إلا زيادة النسخة
                    self.collection == "nasai" and self.current["type"] == "hadith"
                    and not clean(rest).startswith("وجد في نسخة")) or (
                    # مسند أحمد 25794: المدخل صفحة مطبوعة، وما في أولها بلا رقم تتمة الحديث السابق
                    (self.collection == "ahmad" or self.book_id in RISALA_FN)
                    and self.current["type"] in ("hadith", "other")) or (
                    # الترمذي ت شاكر 1435 (شاهد): كلام الترمذي يتمّ في مدخل تالٍ بلا رقم ← تتمة الحديث، ما لم يكن له حكم مستقل
                    self.book_id == 1435 and self.current["type"] == "hadith" and not self.w_grade) or (
                    # الدارمي 36114: المدخل صفحة مطبوعة، وما في أولها بلا رقم تتمة الحديث السابق
                    self.book_id in (36114, 84) and self.current["type"] in ("hadith", "other")) or (
                    # الأدب المفرد: المدخل فقرة، وما بلا رقم بعد حديث تتمته (المتن أو حكم الألباني بعده)
                    self.collection == "adabmufrad" and self.current["type"] == "hadith") or (
                    # ابن حبان 1729 و537 وابن خزيمة 1446 و121382: المدخل صفحة، وما في أولها بلا رقم تتمة الحديث السابق
                    self.book_id in (1729, 1446, 121382, 537) and self.current["type"] in ("hadith", "other")) or (
                    # مسند أبي يعلى ت السناري 181 (شاهد): المدخل صفحة مطبوعة، وما في أولها بلا رقم تتمة الحديث السابق
                    self.book_id == 181 and self.current["type"] in ("hadith", "other")):
                # (ومصنف عبد الرزاق ط التأصيل 84 كذلك: المدخل صفحة مطبوعة)
                self.append(rest)
            elif (self.collection == "bazzar" and self.current["type"] in ("hadith", "bab")
                  and (re.match(r"\s*(?:حدثنا|أخبرنا|حدثني|أخبرني)\s", re.sub(r"[ً-ْٰ]", "", clean(rest)))
                       or self.current["type"] == "hadith")):
                # مسند البزار 12981: المدخل فقرة؛ فقرة بلا رقم تبدأ بـ«حدثنا/أخبرنا» رواية بلا رقم في المطبوع (بعد حديث أو عنوان)،
                # وغيرها بعد حديث («وَنَا يُونُسُ…» إسناد آخر، «قَالَ: وَسَأَلْتُ ابْنَ عُمَرَ…»، «ثم قال:…») تتمته
                if re.match(r"\s*(?:حدثنا|أخبرنا|حدثني|أخبرني)\s", re.sub(r"[ً-ْٰ]", "", clean(rest))):
                    self.seen_hadith = True
                    self.new("hadith", rest, vol, page, entry, numbers={"printed": [], "unnumbered": True}, margin=margin)
                else:
                    self.append("\n" + rest)
            elif (self.book_id == 12520 and self.current["type"] == "hadith"
                  and not re.match(r"\s*(?:بسم الله|تابع|آخر ما كان)", re.sub(r"[ً-ْٰ]", "", clean(rest)))):
                # مسند أبي يعلى ت حسين أسد 12520: المدخل فقرة؛ فقرة بلا رقم تبدأ بـ«حدثنا» رواية بلا رقم في المطبوع،
                # وغيرها («وَحَدَّثَنَا الدَّوْرَقِيُّ…» إسناد آخر، «قَالَ: وَسَمِعْتُهُ يَقُولُ…»، «وَنَهَى…») تتمة الحديث قبلها؛
                # أما البسملة و«تابع مسند…» أول الجزء وخاتمة النسخة «آخر ما كان عند…» فتبقى other
                if re.match(r"\s*(?:حدثنا|أخبرنا)", re.sub(r"[ً-ْٰ]", "", clean(rest))):
                    self.new("hadith", rest, vol, page, entry, numbers={"printed": [], "unnumbered": True}, margin=margin)
                else:
                    self.append("\n" + rest)
            elif (self.collection in TABARANI and not cuts and len(clean(rest)) <= 60
                  and not re.search(r'[«»"،:.؟!]|حدث|أخبر|ثنا|\bنا\b|قال|\bعن\b|سمع|بإسناد',
                                    (plain := re.sub(r"[ً-ْٰ]", "", clean(rest))))
                  and not plain.startswith(("و", "ثم", "ف")) and not re.search("[ﷺ﵌]", plain)):
                # معاجم الطبراني: سطر قصير وحده بلا صيغة رواية ولا علامة («أحمد بن دكين المصري») = اسم شيخ عنوانًا بلا وسم
                # ← سجل باب (plain_heading)
                self.bab = {"n": self.bab["n"] + 1, "title": clean(rest)}
                self.new("bab", "", vol, page, entry, title=clean(rest))
                self.current["plain_heading"] = True
            elif self.collection in TABARANI and not cuts and self.current["type"] in ("hadith", "other"):
                # معاجم الطبراني: المدخل فقرة؛ والفقرة بلا رقم بعد حديث تتمته (إسناد آخر بلا رقم، «وبإسناده…»، «قال ابن شهاب…»،
                # «ونهى أن…») ← تُلحق به في سطر جديد
                self.append("\n" + rest)
            elif self.collection == "tahawi" and re.match(
                    r"\s*(?:و?حدثنا|ما حدثنا|و?أخبرنا)\s", re.sub(r"[ً-ْٰ]", "", TAG.sub("", rest))):
                # شرح معاني الآثار: رواية بإسنادها في مدخل بلا رقم في الملف ← سجل حديث بلا رقم
                self.seen_hadith = True
                self.new("hadith", rest, vol, page, entry, numbers={"printed": [], "unnumbered": True}, margin=margin)
            elif self.collection == "nasaikubra" and re.match(
                    r"\s*(?:أخبرنا|أخبرني|حدثنا|حدثني)\s", re.sub(r"[ً-ْٰ]", "", TAG.sub("", rest))):
                # السنن الكبرى 8361: رواية بإسنادها في مدخل بلا رقم في الملف ← سجل حديث بلا رقم
                self.seen_hadith = True
                self.new("hadith", rest, vol, page, entry, numbers={"printed": [], "unnumbered": True}, margin=margin)
            elif self.collection == "nasaikubra" and self.current["type"] == "hadith":
                # السنن الكبرى 8361: «وأخبرنا…» إسناد آخر، و«قال: وسمعت…» تتمة ← تلحق بالحديث قبلها
                self.append("\n" + rest)
            elif self.collection == "tahawi" and self.current["type"] in ("hadith", "bab", "other"):
                # شرح معاني الآثار: كلام الطحاوي بين الأحاديث (مدخل بلا رقم) ← يلحق بالحديث قبله، أو بنص الباب
                self.append("\n" + rest)
            elif (self.collection == "ibnmajah" and self.book_id == 1198 and self.current["type"] == "hadith"
                  and re.search(r"،\s*$", TAG.sub("", self.current["_raw"]).split("<hr")[0].rstrip())):
                # ابن ماجه 1198 (2894): حديث انقطع بفاصلة وتتمته في المدخل التالي ← تُلحق به
                self.append(rest)
            elif (self.collection == "ibnmajah" and self.book_id == 1198 and self.current["type"] == "hadith"
                  and (mm := re.match(r"\s*([٠-٩]+)\s*-\s*", TAG.sub("", rest)))
                  and [int(mm.group(1).translate(AR))] == self.current.get("numbers", {}).get("printed")):
                # ابن ماجه 1198 (3856): إسناد ثانٍ في مدخل مستقل يحمل رقم الحديث نفسه ← يُلحق به بلا تكرار الرقم
                self.append(re.sub(r"^\s*[٠-٩]+\s*-\s*", "", rest))
            elif self.collection == "malik" and re.match(
                    r"\s*و?حدثني", re.sub(r"[ً-ْٰ]", "", TAG.sub("", rest))):
                # الموطأ 1699: رواية في مدخل مستقل بلا رقم في المطبوع ← سجل حديث بلا رقم (كـ«•» في مسلم)
                self.seen_hadith = True
                self.new("hadith", rest, vol, page, entry, numbers={"printed": [], "unnumbered": True}, margin=margin)
            elif (self.collection == "malik" and self.current["type"] in ("hadith", "bab", "other")
                  and not re.match(r"\s*[٠-٩]+\s*-", TAG.sub("", rest))):
                # الموطأ 1699: تتمة الحديث أو قول مالك بعده في مدخل مستقل ← تُلحق بالحديث (كما في A)،
                # أو بنص الباب إن كان قول مالك تحت الباب بلا حديث
                self.append(rest)
            elif self.book_id == 9944 and self.current["type"] == "hadith":
                # مصنف ابن أبي شيبة ت الحوت 9944 (شاهد): المدخل فقرة؛ فقرة بلا رقم تبدأ بـ«حدثنا» رواية بلا رقم،
                # وغيرها («قال: وقال…»، «وكان يقول…») تتمة الحديث قبلها
                if re.match(r"\s*حدثنا", re.sub(r"[ً-ْٰ]", "", TAG.sub("", rest))):
                    self.new("hadith", rest, vol, page, entry, numbers={"printed": [], "unnumbered": True}, margin=margin)
                else:
                    self.append("\n" + rest)
            else:
                # مدخل جديد بلا رقم: نص مستقل (تعليق للمؤلف، تتمة باب…)
                self.new("other" if self.seen_hadith else "front", rest, vol, page, entry, margin=margin)

    def entry(self, idx, p):
        vol = int(p["vol"]) if str(p["vol"]).isdigit() else str(p["vol"])
        page = p["page"]
        raw_text = p["text"]
        self._idx = idx
        if self.collection == "bazzar" and vol == 18 and self.series != 18:
            # مسند البزار: الجزء ١٨ (ت صبري الشافعي) ترقيمه مستقل يبدأ من ١ ← سلسلة ترقيم جديدة (numbers.series)
            self.series = 18
            self.last_num, self.used, self.misprints = 0, set(), {}
        for f in self.fixes.get(idx, []):
            # إصلاح قرّره المالك (decisions/source-fixes.json): نص بعينه في المدخل الخام، يقع فيه مرة واحدة
            if raw_text.count(f["find"]) != 1:
                raise SystemExit(f"source fix not applicable: {f['collection']} entry {idx}: {f['item']}")
            raw_text = raw_text.replace(f["find"], f["replace"])
            self.fixes_applied.append(f)
        html = EMPTY_SPAN.sub("", raw_text)
        if self.collection in TABARANI:
            if self.book_id == 1733:
                # الكبير: وسم العنوان بعلامة تنصيص مفردة ← مزدوجة
                html = html.replace("data-type='title'", 'data-type="title"')
                # الأجزاء ١–١٢ ترقيمها متصل (١–١٣٦٥٤)؛ والجزء ١٣ (القطعة المنشورة لاحقًا) والأجزاء ١٧–٢٥
                # يبدأ كل منها من ١ ← سلسلة ترقيم جديدة باسم الجزء (numbers.series)
                if str(vol).isdigit() and int(vol) >= 13 and int(vol) != self.series:
                    self.series = int(vol)
                    self.last_num, self.used = 0, set()
                # رقم مطبوع على عنوان الصحابي («١٧٨٨ -<span title> جابر بن سمرة…</span>»، 6 مواضع) ← رقم العنوان
                # (heading_number في سجل الباب)، لا حديث
                html = re.sub(r'^(\s*)([٠-٩]+)\s*-\s*<span data-type="title"', r'\1<span data-heading-num="\2" data-type="title"', html)
                # وسم عنوان يبتلع الحديث بعده («<span title>رفاعة بن سموأل «\n\n٤٥٦٥ - حدثنا…»</span>»، 17 موضعًا)
                # ← يُغلق العنوان آخر سطره الأول، ويُحذف الإغلاق المتأخر
                html = re.sub(r'(<span[^>]*data-type="title"[^>]*>)([^<\n]*)(\n[^<]*?\n\s*[٠-٩]+\s*-[^<]*)</span>',
                              r"\1\2</span>\3", html)
            if self.toc_levels:
                # مستوى العنوان من فهرس الشاملة («toc-N» = العنصر N)، إن لم يكن في الوسم
                def lvl(m):
                    k = int(m.group(2)) - 1
                    if "data-level" in m.group(0) or not 0 <= k < len(self.toc_levels):
                        return m.group(0)
                    return m.group(1) + f' data-level="{self.toc_levels[k]}"' + m.group(3)
                html = re.sub(r'(<span data-type="title" id=["\']?toc-(\d+)["\']?)([^>]*>)', lvl, html)
            # «٢٣٠٨ ⦗١١⦘ حدثنا»: رقم بلا شرطة تليه علامة صفحة ← «٢٣٠٨ - ⦗١١⦘ حدثنا»
            html = re.sub(r"(^|\n)([٠-٩]+)\s*(⦗[٠-٩]+⦘)\s*(?=[ء-ي])", r"\1\2 - \3 ", html)
            # «٤٣٦١ - م حدثني»: إسناد آخر للحديث نفسه ← رقم فرعي «٤٣٦١ - (م) »
            html = re.sub(r"(^|\n)([٠-٩]+)\s*-\s*م\s+", r"\1\2 - (م) ", html)
            # «…\n\n١٠٥٣ -» في آخر المدخل ونص الحديث في المدخل التالي ← علامة U+2063 ليُقرأ الرقم (تُحذف في finish)
            html = re.sub(r"(^|\n)([٠-٩]+)\s*-\s*$", "\\1\\2 - ⁣", html)
        if self.book_id == 1435:
            # الترمذي ت شاكر 1435 (شاهد): وسم العنوان بعلامة تنصيص مفردة ← مزدوجة؛ عنوان «N - أبواب…» في مدخل
            # من المستوى الأول في الفهرس ← مستوى 1 ويُضمّ ذيله («عن رسول الله ﷺ») إليه؛ حكم الألباني «<s0> حكم» ← الصيغة المعروفة
            html = html.replace("data-type='title'", 'data-type="title"')
            if idx in self.toc_top:
                html = re.sub(r'<span data-type="title"([^>]*)>([٠-٩]+\s*-[^<]*)</span>([^\n<]*)',
                              r'<span data-level="1" data-type="title"\1>\2\3</span>', html, count=1)
            html = re.sub(r"<s0>\s*", "[حكم الألباني]: ", html)
            self.w_grade = "[حكم الألباني]" in html
        if self.book_id == 2266:
            # المستدرك ط العلمية 2266 (شاهد): سطر «[التعليق - من تلخيص الذهبي] N - حكمه» بعد الحديث ← grades.dhahabi
            # (ليس من نص الحاكم؛ يُربط بالحديث الذي رقمه N)
            rx = r'(?:<span[^>]*data-type="title"[^>]*>)?\s*\[التعليق - من تلخيص الذهبي\][ \t]*(?:</span>)?[ \t]*(?:([٠-٩]+)[ \t]*-[ \t]*)?([^\n]*)'
            talkhis = [(m.group(1), clean(m.group(2))) for m in re.finditer(rx, html)]
            html = re.sub(rx, "", html)
            self._talkhis = talkhis
        if self.book_id == 1339 and not isinstance(vol, int):
            # النسائي ط الرسالة 1339 (شاهد): مقدمة المحققين (المجلد «المقدمة») نص واحد بلا أحاديث، وحواشيها تُترك
            self.ahmad_front(re.split(r"_{9,}", html, maxsplit=1)[0], vol, page, idx)
            return
        if self.book_id == 1339:
            # رقم الحديث داخل وسم العنوان قبل إغلاقه («…</span>» بعد «١٧٦٣») ← بعد العنوان في سطر مستقل
            html = re.sub(r"\s*([٠-٩]+)</span>\s*-", r"</span>\n\1 -", html)
            # «<hr>» فاصل الحواشي في أربعة مداخل (تتلوه «*» أو تتمة حاشية لا قوس)
            if not re.search(r"_{9,}", html):
                html = re.sub(r"<hr\s*/?>", "_________", html, count=1)
            # «٥٤٨٠/ ١ - » و«٥٤٨٠/ ٢ - »: الأول رقم رئيس، وما بعده فرعي
            html = re.sub(r"(^|\n)([٠-٩]+)\s*/\s*م\s*-\s*", r"\1\2 - (م) ", html)  # «٦٤٨ / م - » إسناد آخر
            html = re.sub(r"(^|\n)([٠-٩]+)/\s*١\s*-\s*", r"\1\2 - ", html)
            html = re.sub(r"(^|\n)([٠-٩]+)/\s*([٠-٩]+)\s*-\s*", r"\1\2 - (م \3) ", html)
        if self.book_id == 1727:
            # مسلم ت عبد الباقي (شاهد): «N - م - (M)»، «N م - (M)»، «N - م K - (M)»، «م (M)» = إسناد مكرر للرقم M ← «N - (M)»
            html = re.sub(r"(^|\n)[ \t]*(?:([٠-٩]+)[ \t]*-?[ \t]*)?م[ \t]*[٠-٩]*[ \t]*-?[ \t]*(?=\([٠-٩]+(?:\s*/\s*[٠-٩]+)*\))",
                          lambda m: m.group(1) + (m.group(2) + " - " if m.group(2) else ""), html)
            # «(M) - وحدثنا» ← «(M) وحدثنا»
            html = re.sub(r"(^|\n)[ \t]*(\([٠-٩]+(?:\s*/\s*[٠-٩]+)*\))[ \t]*-[ \t]*", r"\1\2 ", html)
            # إحالة الآية «[٩ / التوبة / الآية ١١٣]» ← «[التوبة: ١١٣]» لتُنقل إلى verse_refs
            html = re.sub(r"\[\s*[٠-٩]+\s*/\s*([^\]/\n٠-٩]{1,20}?)\s*/\s*(?:الآية|الآيات|آية)?\s*-?\s*([٠-٩]+(?:\s*[-–،,]\s*[٠-٩]+)*)\s*\]",
                          r"[\1: \2]", html)
        if self.book_id == 333:
            # مصنف ابن أبي شيبة ت الشثري 333: مقدمة التحقيق قبل «[١] [كتاب الطهارة]» فيها قوائم مرقمة «١ - …» ليست أحاديث
            if idx < self.body_start:
                self.ahmad_front(SEP_ANY_HR.split(html, 1)[0], vol, page, idx)
                return
            # «(N) [*] حدثنا» حديث برقم مطبوع خطأً خارج التسلسل (حاشية مُعِدّ الشاملة: «كذا الرقم بالمطبوع، وهو غلط»)
            # ← «N - [*]» يُقبل في seq_cuts حديثًا برقمه كما طُبع، و numbers.misprint، ولا يغيّر التسلسل
            html = re.sub(r"(^|\n)\(([٠-٩]+)\)\s*\[\*\]\s*", r"\1\2 - [*m] ", html)
            # «<hr>» قبل حاشية مُعِدّ الشاملة «[*] قال مُعِدُّ…» فاصل حواشٍ
            html = re.sub(r"<hr\s*/?>(?=\s*\[\*\])", "_________", html)
            # «(¬<span…>١) [١١٤] باب…</span>» و«(*) <span…>»: بقايا إحالة حاشية قبل وسم العنوان
            html = re.sub(r"\(¬(<span[^>]*>)[٠-٩]+\)\s*", r"\1", html)
            html = re.sub(r"(^|\n)\(\*\)\s*(?=<span)", r"\1", html)
        if self.book_id == 735 and idx < self.body_start:
            # البخاري ت البغا (شاهد): مقدمة الشارح قبل «بدء الوحي» فيها قوائم مرقمة «١ - …» ليست أحاديث
            self.ahmad_front(SEP_ANY_HR.split(html, 1)[0], vol, page, idx)
            return
        if self.book_id == 735:
            # البخاري ت البغا (شاهد): إحالة الآية «/النساء: ١٦٣/» ← «[النساء: ١٦٣]» لتُنقل إلى verse_refs
            html = re.sub(r"/([^/\n<>]{2,25}:\s*[٠-٩]+(?:\s*[-–،,]\s*[٠-٩]+)*)/", r"[\1]", html)
            # إحالات البغا إلى مواضع الحديث الأخرى «[٥٤، ٢٣٩٢].» و«[ر: ٤٥٣٨]» (وقد تنكسر على سطرين)
            # ← تُحذف من النص وتُحفظ في cross_refs
            html = re.sub(r"\[(?:ر:\s*)?([٠-٩](?:[٠-٩،,\-–\s]|وانظر:?)*)\]\.?",
                          lambda m: '<span data-xref="' + ",".join(x.translate(AR) for x in re.findall(r"[٠-٩]+", m.group(1)))
                          + '"></span>', html)  # أرقام لاتينية في الوسم لئلا يُقرأ «N - » فيه رقمَ حديث
        if self.book_id == 28107:
            # الموطأ ت الأعظمي 28107 (شاهد ثانٍ): مقدمة التحقيق قبل «وقوت الصلاة» وتراجم الرجال بعد آخر كتاب ← لا تُستخرج
            if idx < self.body_start or idx >= self.body_end:
                self.stats["skipped_entries"] = self.stats.get("skipped_entries", 0) + 1
                return
            # الحواشي بعد «<hr>» مطلقًا (يتلوه رأس الصفحة «وقوت الصلاة: ١» ثم «(^١)…») ← notes لآخر سجل
            parts = re.split(r"<hr\s*/?>", html, maxsplit=1)
            if len(parts) == 2:
                html = parts[0]
                lines = [clean(x) for x in parts[1].split("\n") if clean(x)]
                self._azami_notes = lines
            # الأعظمي يرقّم كل فقرة ترقيمًا عامًّا، والعناوين أيضًا («٢ - <span title>») ← يُحذف رقم العنوان
            html = re.sub(r'(^|\n)\s*[٠-٩]+\s*-\s*(?=<span[^>]*data-type="title")', r"\1", html)
            # «٤/ ١ - »: الرقم العام ثم عدّاد الأحاديث المرفوعة ← «٤ - » ويُحفظ العدّاد في numbers.azami_hadith
            html = re.sub(r"(^|\n)((?:<[^>]+>)*\s*)?([٠-٩]+)\s*/\s*([٠-٩]+)\s*-\s*",
                          lambda m: (self.azami_k.__setitem__(int(m.group(3).translate(AR)), int(m.group(4).translate(AR)))
                                     or f"{m.group(1)}{m.group(2) or ''}{m.group(3)} - "), html)
            # كل «رقم - » في أول السطر فقرة مرقّمة عند الأعظمي ← تُقبل في seq_cuts دون شرط التتابع (علامة U+2063)
            html = re.sub(r"(^|\n)((?:<[^>]+>)*\s*)?([٠-٩]+)\s*-\s*", "\\1\\2\\3 - ⁣", html)
        if self.collection == "adabmufrad":
            # الأدب المفرد (12991 ت عبد الباقي، 9647 ت الزهيري): أبواب بلا كتب؛ عناوين المستوى الأول في الفهرس أبواب ← مستوى 2
            html = re.sub(r'(<span[^>]*data-type="title"[^>]*?) data-level="1"', r"\1", html)
            html = re.sub(r'data-level="1"([^>]*data-type="title")', r"\1", html)
            # حكم الألباني «[قال الشيخ الألباني]:\n صحيح» (12991) ← الصيغة المعروفة فيُنقل إلى grades.albani
            html = html.replace("[قال الشيخ الألباني]", "[حكم الألباني]")
            # 12991: المدخل التالي يُعاد فيه رقم الحديث الجاري («٣٤١ - قَالَ: فَانْطَلَقَ…»، «١٣١٩ - حدثنا» إسناد ثانٍ)
            # ← تتمة الحديث نفسه، يُحذف الرقم المكرر
            mm = re.match(r"\s*([٠-٩]+)\s*-\s*", html)
            if (mm and self.current is not None and self.current["type"] == "hadith"
                    and int(mm.group(1).translate(AR)) == self.last_num):
                html = "\n" + html[mm.end():]
                self.stats["adab_repeated_number"] += 1
            # عنوان باب سطرًا نصيًّا بلا وسم («بَابُ مَنْ خَتَمَ عَلَى خَادِمِهِ…») ← وسم عنوان
            html = re.sub(r'(^|\n)[ \t]*(بَابُ?ٌ?\s[^\n<]{2,150})[ \t]*(?=\n|$)',
                          r'\1<span data-type="title" data-plain="1">\2</span>', html)
        if self.collection == "tahawi":
            # شرح معاني الآثار: عنوان الباب يبتلع كلام الطحاوي بعده («بَابُ الْأَقْرَاءِ قَالَ أَبُو جَعْفَرٍ: …») ← يُقطع العنوان
            # عند «قال أبو جعفر» ويبقى الكلام نصًّا للباب
            html = re.sub(r'(<span[^>]*data-type="title"[^>]*>)(.*?)\s+(قَالَ أَبُو جَعْفَرٍ.*?)</span>',
                          r"\1\2</span>\n\3", html, flags=re.S)
            # عنوان كتاب أو باب سطرًا نصيًّا بلا وسم («كِتَابُ وُجُوهِ الْفَيْءِ…»، «بَابُ رَدِّ الْيَمِينِ») ← وسم عنوان
            html = re.sub(r'(^|\n)[ \t]*(كِتَابُ\s[^\n<]{2,150}?)[ \t]*(?=\n|$|\s+قَالَ)',
                          r'\1<span data-type="title" data-level="1" data-plain="1">\2</span>\n', html)
            html = re.sub(r'(^|\n)[ \t]*(بَابُ?ٌ?:?\s[^\n<]{2,150}?)[ \t]*(?=\n|$)',
                          r'\1<span data-type="title" data-plain="1">\2</span>', html)
            # رقم فرعي «٣٨٣٦م- » و«٤٠٢٠م - » و«٧٣٤٨أ - » ← «N - (م)» و«N - (م أ)»
            html = re.sub(r"(^|\n)([٠-٩]+)\s*م\s*-\s*", r"\1\2 - (م) ", html)
            html = re.sub(r"(^|\n)([٠-٩]+)\s*([أ-ي])\s*-\s*", r"\1\2 - (م \3) ", html)
            html = re.sub(r"(^|\n)([٠-٩]+)\s*-\s*([أ-ي])\s*-\s*", r"\1\2 - (م \3) ", html)  # «٦٥٤٤ - ب- »
        if self.collection == "nasaikubra":
            # السنن الكبرى للنسائي 8361: «٩٧٧٥/ ٩٧٧٦ - » رقمان لحديث ← «٩٧٧٥ - ٩٧٧٦ - »؛ «٢٠٣٠/ ١ - » أول أجزاء الحديث ← الرقم،
            # و«٢٠٣٠/ ٢ - » ما بعده ← رقم فرعي «(م ٢)»
            def _slash(m):
                a, b = int(m.group(2).translate(AR)), int(m.group(3).translate(AR))
                if b == a + 1:
                    return f"{m.group(1)}{m.group(2)} - {m.group(3)} - "
                return f"{m.group(1)}{m.group(2)} - " + ("" if b == 1 else f"(م {m.group(3)}) ")
            html = re.sub(r"(^|\n)([٠-٩]+)\s*/\s*([٠-٩]+)\s*-\s*", _slash, html)
            # إحالة الآية بعد إغلاق وسم الآية «﴿…﴾ [</span>البقرة: ٢٢٢]» ← الوسم قبل القوس لتُنقل الإحالة إلى verse_refs
            html = html.replace("[</span>", "</span>[")
            # عنوان باب سطرًا مفردًا في مدخل بلا وسم («تَأْوِيلُ قَوْلِ اللهِ…»، «الْمَلَائِكَةُ») بعد حديث ← وسم عنوان
            plain = clean(html)
            if (plain and "\n" not in plain and "data-type" not in html and len(plain) <= 250
                    and not re.match(r"\s*(?:و?أخبر|و?أنبا|و?حدث|و?قال|[٠-٩])", re.sub(r"[ً-ْٰ]", "", plain))):
                html = f'<span data-type="title" data-plain="1">{html.strip()}</span>'
                self.stats["kubra_plain_bab"] += 1
        if self.book_id == 9647:
            # الأدب المفرد ت الزهيري (شاهد): رقم الباب في عنوانه «١٠- بَابُ…» ← data-num؛ وإحالة حاشية بعد العنوان «</span> (١)» تُحذف
            html = re.sub(r'(<span[^>]*data-type="title"[^>]*)>\s*([٠-٩]+)\s*-\s*', r'\1 data-num="\2">', html)
            # سطر حكم الألباني بعد الحديث بلا وسم («صحيح - «الإرواء» (١١٩٨)…»، «ضعيف الإسناد؛ …»، «صحيح: انظر ما قبله»)
            # ← الصيغة المعروفة فيُنقل إلى grades.albani (الحكم غير مشكول، فلا يلتبس بلفظ «حَسَنٌ» في المتن)
            # (مع أخطاء الصفّ في لفظ الحكم: «صصحيح»، «صحيبح»، «صيح»، «ضغيف»، «ضعبف»)
            html = re.sub(r"(^|\n)[ \t]*\.?[ \t]*((?:ص?صحيب?ح|صيح|حسن|ضعيف|ضعبف|ضغيف|شاذ|منكر|موضوع|موقوف)(?![ً-ْ])[^\n]*)",
                          r"\1[حكم الألباني]: \2", html)
            # عدّاد الآثار عند الزهيري «٢ - (ث١) » ← numbers.athar (يُحفظ في finish)، ويُحذف من النص
            html = re.sub(r"(^|\n)([٠-٩]+\s*-\s*)\(ث\s*([٠-٩]+)\)\s*", "\\1\\2⁤\\3⁤ ", html)
        if self.book_id == 36114:
            # الدارمي ت الزهراني 36114 (شاهد ثانٍ): مقدمة التحقيق قبل «١ - باب*» نص مقدمة واحد، لا أحاديث
            if idx < self.body_start:
                front = clean(SEP_RX.split(html, 1)[0])
                if self.current is None:
                    self.new("front", front, vol, page, idx)
                else:
                    self.append("\n" + front)
                return
            # عنوان الباب برقمه «٣٧١ - باب…» (وسمًا أو سطرًا نصيًّا) ← رقمه في data-num؛ «*» علامة لوحة المخطوط
            html = re.sub(r'(<span[^>]*data-type="title"[^>]*)>\s*([٠-٩]+)\s*-\s*',
                          r'\1 data-num="\2">', html)
            html = re.sub(r'(^|\n)\s*([٠-٩]+)\s*-\s*(بابٌ?\*?[^\n]*)',
                          r'\1<span data-num="\2" data-type="title" data-plain="1">\3</span>', html)
            # إحالات الحواشي و«*» داخل العناوين ← تُحذف
            html = re.sub(r'(<span[^>]*data-type="title"[^>]*>)(.*?)</span>',
                          lambda m: m.group(1) + re.sub(r"\s*\([٠-٩]+\)|\*", "", m.group(2)) + "</span>", html, flags=re.S)
            # «٨٦٠ - (٢) أخبرنا»: الرقم العام ثم رقمه في الباب، و«(...)» إسناد بلا رقم في الباب ← يُحذف رقم الباب
            # وصيغة «رقم - (رقم الباب)» في أول السطر علامة حديث يقينية (الترقيم العام فيه أخطاء طباعة: ٩٠٧ بين ٨٦٠ و٨٦١)
            # ← يُعلَّم بـ U+2063 ليُقبل في seq_cuts دون شرط تتابع الأرقام، ويُحذف العلامة في finish()
            html = re.sub(r"(^|\n)([٠-٩]+)\s*-\s*\((?:[٠-٩]+|\.\.\.|…)\)\s*", "\\1\\2 - ⁣", html)
        if self.collection == "ibnjarud":
            # المنتقى لابن الجارود (627، والشاهد 13071): الأبواب مرقّمة تسلسليًّا في الكتاب كله،
            # «(٦١) <span title>» ثم «٦٣ - <span title>» ← رقم الباب في data-num (لا رقم حديث)
            html = re.sub(r'(^|\n)\s*([٠-٩]+)\s*[-–]\s*<span([^>]*data-type="title")', r'\1<span data-num="\2"\3', html)
            # باب بلا ترجمة «٧٦ - بَابٌ» وحده في المدخل ← عنوان باب برقمه
            html = re.sub(r'^\s*([٠-٩]+)\s*-\s*(بَابٌ)\s*$',
                          r'<span data-num="\1" data-type="title" data-plain="1">\2</span>', html)
            # «١٠١/ ٢ - » فقرة ثانية من الحديث ١٠١ في مدخل مستقل ← رقم فرعي
            html = re.sub(r"(^|\n)((?:<[^>]+>|[ \t])*)([٠-٩]+)/\s*([٠-٩]+)\s*-\s*", r"\1\2\3 - (م \4) ", html)
        if self.collection == "tayalisi":
            # مسند الطيالسي 1456: «٢٨٠٦ - م حدثنا» إسناد آخر للرقم نفسه ← رقم فرعي
            html = re.sub(r"(^|\n)([٠-٩]+)\s*-\s*م\s+", r"\1\2 - (م) ", html)
        if self.collection in ("tayalisi", "humaydi") and self.toc_top.get(idx):
            # الطيالسي 1456 والحميدي 8493: عنوان المسند في المتن وسم بلا مستوى يكرر عنوان الفهرس (المستوى الأول)
            # ← مستوى 1، لئلا يُنشأ «كتاب» من الفهرس و«باب» بالعنوان نفسه
            bare = lambda s: re.sub(r"[ً-ْٰ\s،,]", "", clean(s))
            tops = {bare(t) for t in self.toc_top.get(idx, [])}
            html = re.sub(r'<span (data-type="title"[^>]*)>(.*?)</span>',
                          lambda m: (f'<span data-level="1" {m.group(1)}>{m.group(2)}</span>'
                                     if "data-level" not in m.group(1) and bare(m.group(2)) in tops else m.group(0)),
                          html, count=1, flags=re.S)
        if self.book_id == 1446:
            # صحيح ابن خزيمة ت الأعظمي 1446: وسم العنوان بعلامة تنصيص مفردة ← مزدوجة؛ عنوان الكتاب (المستوى الأول
            # في الفهرس) وسم بلا مستوى ← مستوى 1؛ تعليق المحقق «<s0>N - قال الأعظمي: …» وتعقيب الألباني ← grades
            # والتتمة من المدخل السابق تبدأ سطرًا جديدًا؛ وعنوان باب سطرًا نصيًّا بلا وسم في أول المدخل ← وسم عنوان
            html = "\n" + html.replace("data-type='title'", 'data-type="title"')
            if 'data-type="title"' not in html:
                html = re.sub(r'^\s*(بَابُ\s[^\n<]*)', r'<span data-type="title" data-plain="1">\1</span>', html, count=1)
            if idx in self.toc_top:
                html = re.sub(r'<span (data-type="title")', r'<span data-level="1" \1', html, count=1)
            # وسم عنوان لا يُغلق في سطره (40 موضعًا) وإغلاقه بعد الحديث كله ← يُغلق آخر سطره ويُحذف الإغلاق المتأخر
            lines, late = html.split("\n"), 0
            for k, line in enumerate(lines):
                if late and "</span>" in line:
                    lines[k], late = line.replace("</span>", "", 1), late - 1
                elif 'data-type="title"' in line and "</span>" not in line:
                    lines[k], late = line + "</span>", late + 1
            html = "\n".join(lines)
            html = self.khuzayma_grades(html)
        if self.book_id == 1729:
            self.hibban_entry(html, vol, page, idx)
            return
        if self.book_id == 148486:
            self.bayhaqi_entry(html, vol, page, idx)
            return
        if self.book_id == 7861:
            # السنن الكبرى ط العلمية 7861 (شاهد): «١٠٨٣ م - » إسناد آخر للحديث ← رقم فرعي
            html = re.sub(r"(^|\n)([٠-٩]+)\s*م\s*-\s*", r"\1\2 - (م) ", html)
            # «٥٥٥٦ ⦗٢٤٠⦘ فَأَخْبَرَنَا» رقم بلا شرطة في أول السطر (وقد تليه علامة صفحة) ← «٥٥٥٦ - »
            html = re.sub(r"(^|\n)([٠-٩]+) +(?=(?:⦗[٠-٩]+⦘\s*)?[ء-ي])", r"\1\2 - ", html)
        if self.book_id in (121382, 537) and idx < self.body_start:
            # شاهدا ابن خزيمة ط3 (121382) وابن حبان «التقاسيم والأنواع» (537): مقدمة التحقيق قبل أول كتاب/قسم
            # فيها قوائم مرقمة «١ - …» ليست أحاديث ← نص مقدمة واحد
            self.ahmad_front(SEP_RX.split(html, 1)[0], vol, page, idx)
            return
        if self.book_id in (121382, 537):
            html = "\n" + html  # تتمة الحديث من الصفحة السابقة سطر جديد لا تلتصق بآخره
        if self.book_id == 121382:
            # رقم الباب داخل وسم العنوان «(٥٨) بَابُ …» ← data-num؛ علامة لوحة المخطوط «[١٦٣ - ب]» ← تُحذف
            html = re.sub(r'(<span[^>]*data-type="title"[^>]*)>\s*\(([٠-٩]+)\)\s*', r'\1 data-num="\2">', html)
            html, k = re.subn(r"\s*\[[٠-٩]+\s*-?\s*[أب]\]", "", html)
            self.stats["folio_marks"] = self.stats.get("folio_marks", 0) + k
        if self.book_id == 537:
            # «التقاسيم والأنواع» 537: رقم الحديث في «الإحسان» (الأساس 1729) بين قوسين آخر الحديث «[٣١٣٤]»
            # ← numbers تبقى رقم الطبعة، ورقم الإحسان في concordance.ihsan (مفتاح المقابلة)
            html = re.sub(r"\[([٠-٩]+)\](?=[ \t]*\.?[ \t]*(?:\n|$))", lambda m: f"⁅I{m.group(1).translate(AR)}⁆", html)
        if self.book_id == 13174:
            # مصنف عبد الرزاق 13174: علامة الاستفهام بعد إغلاق وسم العنوان («بَابُ هَلْ يَتَوَضَّأُ…</span>؟») ← داخل العنوان
            html = re.sub(r"</span>[ \t]*(؟)", r"\1</span>", html)
            # وإحالة الآية مقسومة على الإغلاق («﴿…﴾ [</span>الأنعام: ١٤١]») ← داخله
            html = re.sub(r"\[</span>([^\n<\]]{1,25}\])", r"[\1</span>", html)
        if self.book_id == 84:
            # مصنف عبد الرزاق ط التأصيل 84 (شاهد ثانٍ): مقدمة التحقيق قبل «١ - كتاب الطهارة» و«ثبت المصادر» بعد آخر كتاب ← لا تُستخرج
            if idx < self.body_start or idx >= self.body_end:
                self.stats["skipped_entries"] = self.stats.get("skipped_entries", 0) + 1
                return
            # الرقم بين معقوفين بعد رمز الطبعة («° [٢٣]» مرفوع، «• [٢٨]» موقوف) في المتن قبل فاصل الحواشي
            # ← «٢٣ - » بعلامة U+2063 (يُقبل في seq_cuts دون شرط التتابع)، والرمز في حقل tasil_kind؛
            # وأسطر التخريج «° [٥] [التحفة: …]» في الحواشي تبقى كما هي
            parts = re.split(r"(_{9,}|<hr\s*/?>)", html, maxsplit=1)  # فاصل الحواشي خط أو <hr>

            def tasil(m):
                kind = {"°": "marfu", "•": "mawquf"}.get(m.group(2) or "")
                if kind:
                    self.tasil_kind[int(m.group(3).translate(AR))] = kind
                return f"{m.group(1)}{m.group(3)} - ⁣"
            parts[0] = re.sub(r"(^|\n)[ \t]*([•°*])?[ \t]*\[([٠-٩]+)\][ \t]*،?[ \t]*", tasil, parts[0])
            html = "".join(parts)
        # صيغ ترقيم شاذة في الملف (تطبيع لمواضع القطع فقط، لا يدخل النص):
        # «٤٢٤٦ ٤٢٤٧ - » و«٤٤٥٥ - ٤٤٥٦ - ٤٤٥٧ حدثني» ← شُرط بعد كل رقم
        html = re.sub(r"(?<![٠-٩])([٠-٩]+) +(?=[٠-٩]+\s*-)", r"\1 - ", html)
        html = re.sub(r"((?:^|\n)(?:[٠-٩]+\s*-\s*)+)([٠-٩]+) +(?=[^\s٠-٩\-(])", r"\1\2 - ", html)
        # رقم قبل عنوان الباب («٤٣٠٠ - <span title>…</span> حدثنا») ← يُنقل بعد العنوان
        html = re.sub(r'(^|\n)((?:[٠-٩]+\s*-\s*)+)(<span[^>]*data-type="title"[^>]*>.*?</span>)', r"\1\3\n\2", html, flags=re.S)
        # رقم الباب قبل عنوانه («(٢٦) <span title>») ← يُحمل في وسم العنوان ثم في حقل bab_number
        # (الترمذي ت بشار: «(١) (٢٣٦) <span title>» = رقم الباب في أبوابه ثم رقمه العام؛ وقد يأتي العنوان نصًّا بلا وسم)
        html = re.sub(r'(^|\n)\s*\(([٠-٩]+)\)\s*(?:،?\s*\(([٠-٩]+)\)\s*)?(?:-\s*)?<span([^>]*data-type="title")',
                      lambda m: f'{m.group(1)}<span data-num="{m.group(2)}"'
                                + (f' data-num2="{m.group(3)}"' if m.group(3) else "") + m.group(4), html)
        html = re.sub(r'(^|\n)\s*\(([٠-٩]+)\)\s*(?:،?\s*\(([٠-٩]+)\)\s*)?(?:-\s*)?(بَاب[^\n]*)',
                      lambda m: f'{m.group(1)}<span data-num="{m.group(2)}"'
                                + (f' data-num2="{m.group(3)}"' if m.group(3) else "")
                                + f' data-type="title" data-plain="1">{m.group(4)}</span>', html)
        if self.collection == "nasai":
            # «٥١٢ م - » رقم فرعي بلا قوس ← «٥١٢ - (م) »
            html = re.sub(r"(^|\n)([٠-٩]+) م\s*-\s*", r"\1\2 - (م) ", html)
            # عنوان باب نصًّا بلا وسم في أول المدخل («(٢٦) تَأْوِيلُ قَوْلِ اللهِ…») ← وسم عنوان برقمه
            html = re.sub(r'^\s*\(([٠-٩]+)\)\s+([^\n<(]+)',
                          lambda m: f'<span data-num="{m.group(1)}" data-type="title" data-plain="1">{m.group(2)}</span>', html)
        # ابن ماجه 1198: عنوان الباب سطر نصي بلا وسم، ورقمه في فهرس الشاملة «(N) باب…» ← وسم عنوان برقمه
        if self.collection == "ibnmajah" and self.book_id == 1198:
            # «بَابُ» وحده في آخر المدخل واسمه في أول المدخل التالي ← يُحذف هنا ويُضمّ إلى الاسم هناك
            html, n = re.subn(r"\n\s*(بَاب[ُ]?)\s*(?=\n\s*\n<hr|\s*$)", "", html)
            if n:
                self.bab_prefix = "بَابُ "
        if self.collection == "malik":
            # الموطأ 1699: وسم عنوان بلا إغلاق يبتلع ما بعده («<span title>بَابُ …\n\n١٢ - قَالَ مَالِكٌ…») ← يُغلق آخر سطره
            # (والإغلاق قد يأتي بعد الحديث كله) ← يُغلق العنوان آخر سطره الأول ويُحذف الإغلاق المتأخر
            html = re.sub(r'(<span[^>]*data-type="title"[^>]*>)([^<\n]*)(\n[^<]*)</span>',
                          r"\1\2</span>\3", html)
            # الموطأ 1699: عنوان باب سطرًا نصيًّا بلا وسم وليس في الفهرس («بَابُ جَامِعِ الْوُقُوتِ») ← وسم عنوان
            html = re.sub(r'^\s*(بَابُ?\s[^\n<]{2,120})\s*$',
                          r'<span data-type="title" data-level="2" data-plain="1">\1</span>', html, flags=re.M)
        if self.collection == "ibnmajah" and self.book_id == 1198 and idx in self.toc_bab:
            nums = iter(self.toc_bab[idx])
            wrap = lambda m: (f'{m.group(1)}<span data-num="{next(nums, "")}"'
                              f' data-type="title" data-plain="1">{m.group(2)}</span>')
            html, n = re.subn(r'(^|\n)\s*(بَاب[^\n<]*)', wrap, html)
            if not n:  # عنوان بلا لفظ «باب» («الْمُبَالَغَةُ فِي الِاسْتِنْشَاقِ…»، «أَبْوَابُ مَوَاقِيتِ الصَّلَاةِ»)
                html = re.sub(r'^()\s*([^\n<٠-٩][^\n<]*)', wrap, html, count=1)
            html = html.replace(' data-num=""', "")
            if getattr(self, "bab_prefix", ""):
                html = html.replace('data-plain="1">', 'data-plain="1">' + self.bab_prefix, 1)
                self.bab_prefix = ""
        # إحالة حاشية بين الرقم والشرطة («١٨٤٢ (١) - ») تُنقل بعد الشرطة لئلا تُقرأ رقمًا فرعيًا
        html = re.sub(r"(^|\n)([٠-٩]+)\s*(\([٠-٩]+\))\s*-\s*", r"\1\2 - \3 ", html)
        # حديث أخرجه المحقق إلى الحاشية («٢٠٨٦ (^١).» ونصه في الحاشية): سجل بلا نص، والحاشية في notes
        html = re.sub(r"(^|\n)([٠-٩]+)\s*(\(\^[٠-٩]+\))\s*\.?[ \t]*(?=\n|$)", r"\1\2 - \3 .", html)
        # رقم قبل «بَابٌ» بلا عنوان («٣٤٠٣ - بَابٌ\nحدثني») ← باب ثم الرقم
        html = re.sub(r"(^|\n)((?:[٠-٩]+\s*-\s*)+)(بَابٌ:?)[ \t]*\n",
                      r'\1<span data-type="title" data-level="2">\3</span>\n\2', html)
        # رقم فرعي داخل الحديث بصيغة «١٧٦٧ م ١» ← «١٧٦٧ - (م ١)»
        html = re.sub(r"(>|^|\n)([٠-٩]+) م ([٠-٩]+) ", r"\1\2 - (م \3) ", html)
        if self.profile == "muslim":
            # وسوم المتن حول الرقم («<hadeeth-652>٥٨ - <hadeeth>(١٤٨٩)<hadeeth-652>») تُنقل بعده
            html = re.sub(r"(^|\n)((?:<hadeeth-?\d*>)*)([٠-٩]+\s*-\s*)((?:<hadeeth-?\d*>)*)(\([٠-٩/ ]+\))((?:<hadeeth-?\d*>)*)",
                          r"\1\3\5\2\4\6", html)
            # رقم قبل عنوان الباب («٦٤ - (٢٢٠٠) <span title>…</span>») ← بعد العنوان
            html = re.sub(r'(^|\n)((?:[٠-٩]+\s*-\s*)?\([٠-٩/ ]+\)\s*)(<span[^>]*data-type="title"[^>]*>.*?</span>)',
                          r"\1\3\n\2", html, flags=re.S)
        if self.collection == "darimi":
            # الدارمي 21795: «١٢٨٣ م - » و«٢٥٣٢ مكرر - » و«٤٠٢ - مكرر » ← رقم فرعي «٢٥٣٢ - (مكرر) »
            html = re.sub(r"(^|\n)([٠-٩]+) (م|مكرر)\s*-\s*", r"\1\2 - (\3) ", html)
            html = re.sub(r"(^|\n)([٠-٩]+)\s*-\s*مكرر\s+", r"\1\2 - (مكرر) ", html)
            # الدارمي 21795: حكم المحقق حسين أسد سطر بعد الحديث بوسم عنوان «[تعليق المحقق]» ← ليس بابًا؛
            # يبقى نصًّا خامًا هنا ويُنقل في finish() إلى grades.husayn_asad
            html = re.sub(r'<span data-type="title">\s*\[تعليق المحقق\]\s*</span>', "[تعليق المحقق]", html)
            # ذيل العنوان خارج الوسم («…كَيْفَ هُوَ</span>؟» و«…﴿…﴾ [</span>البقرة: ١٨٥]») ← داخل العنوان
            html = re.sub(r"</span>(؟)", r"\1</span>", html)
            html = re.sub(r"\[</span>([^\n<\]]{1,25}\])", r"[\1</span>", html)
            # عنوان باب نصًّا بلا وسم في أول المدخل («بَابُ ﴿إِذَا قُمْتُمْ…﴾ [المائدة: ٦] الْآيَةَ») ← وسم عنوان
            if "data-type=\"title\"" not in html:
                html = re.sub(r'^\s*(بَابٌ?ُ?[^\n<]*)', r'<span data-type="title" data-plain="1">\1</span>', html, count=1)
            # عنوان الكتاب في المتن وسم بلا مستوى؛ إن طابق (بلا تشكيل) عنوانًا من المستوى الأول في الفهرس ← مستوى 1
            bare = lambda s: re.sub(r"[ً-ْٰ\s]", "", clean(s))
            tops = {bare(t) for t in self.toc_top.get(idx, [])}
            if tops:
                html = re.sub(r'<span (data-type="title"[^>]*)>(.*?)</span>',
                              lambda m: (f'<span data-level="1" {m.group(1)}>{m.group(2)}</span>'
                                         if "data-level" not in m.group(1) and bare(m.group(2)) in tops else m.group(0)),
                              html, flags=re.S)
        if self.collection == "bazzar":
            if idx == 0:
                # مسند البزار 12981: المدخل الأول بطاقة الكتاب (المحققون، الناشر، «ترقيم الجزء ١٨ غير متسلسل…») ← front
                self.ahmad_front(html, vol, page, idx)
                return
            # «٤١٠٠ م- وعن أبي الدرداء…» و«٨٦٣١م- ذكر عمر بن يونس…»: رواية تابعة للحديث برقمه ← رقم فرعي «(م)»
            html = re.sub(r"(^|\n)([٠-٩]+)\s*م\s*-\s*", r"\1\2 - (م) ", html)
            # عنوان المسند سطرًا بلا وسم يكرر عنوان الفهرس («مُسْنَدُ أَبِي بَكْرٍ الصِّدِّيقِ ﵁. . . . . . .») ← يُحذف (العنوان في سجل الكتاب)
            bare = lambda s: re.sub(r"[ً-ْٰ\s.]", "", s)
            for t in self.toc_top.get(idx, []):
                html = re.sub(r"^\s*([^\n<]+)\n", lambda m: "" if bare(m.group(1)) == bare(t) else m.group(0), html, count=1)
        if self.book_id == 12520:
            # مسند أبي يعلى ت حسين أسد 12520: حكم المحقق سطر بعد الحديث بوسم عنوان «[حكم حسين سليم أسد]:» ← ليس بابًا؛
            # يبقى نصًّا خامًا هنا ويُنقل في finish() إلى grades.husayn_asad (كالدارمي 21795)
            html = re.sub(r'<span data-type="title"[^>]*>\s*\[حكم حسين سليم أسد\]\s*:?\s*</span>', "[حكم حسين سليم أسد]", html)
        notes = ""
        if self.collection == "ahmad":
            # مسند أحمد 25794: «<hr>» فاصل حواشٍ مطلقًا (تتلوه تتمة حاشية لا «(N)» دائمًا)
            parts = re.split(r"_{9,}|<hr\s*/?>", html, maxsplit=1)
            if len(parts) == 2:
                html, notes = parts
            if idx < self.body_start:
                self.ahmad_front(html, vol, page, idx)
                return
            if (self.book_id == 98139 and str(vol).isdigit() and int(vol) >= 2 and page <= 4
                    and not re.search(r"(?:^|\n)\s*[٠-٩]+\s*-", html)):
                # ت شاكر: صفحات أول كل جزء (العنوان، البسملة، «المسند»، حقوق الطبع) ← سجل front لا تتمة لآخر حديث
                self.ahmad_front(html, vol, page, idx)
                return
            if self.book_id == 98139:
                # مسند أحمد ت شاكر 98139: أخطاء صفّ في أول سطر الرقم («ِ١٠٦١ -»، «-١٤٤٦ -»، «٥١٣ـ»، «١٢٥٨.-»)
                html = re.sub(r"(^|\n)[ً-ْ\s\-]+(?=[٠-٩]+\s*[-ـ.]|[٠-٩]+ +[ء-ي])", r"\1", html)
                # «٥٠٦٣َ- حدثنا»: حركة بين الرقم والشرطة؛ «٢َ٢٢٤ -»: حركة داخل الرقم؛ «٧١٨* -»: نجمة مكان رقم
                html = re.sub(r"(?:(?<=^)|(?<=\n))[٠-٩][٠-٩ً-ْ]*[٠-٩](?=\s*[-*])",
                              lambda m: re.sub(r"[ً-ْ]", "", m.group(0)), html)
                html = re.sub(r"(^|\n)([٠-٩]+)[ً-ْ]+\s*-", r"\1\2 -", html)
                html = re.sub(r"(^|\n)([٠-٩]+)\*\s*-", r"\1\2 -", html)
                html = re.sub(r"(^|\n)([٠-٩]+)\s*(?:ـ+|\.\s*-?)\s*(?=\S)", r"\1\2 - ", html)
            # رموز الطبعة قبل الرقم (مقدمة المحققين): • زيادات عبد الله، ° وجاداته، * ما رواه عن أبيه وعن شيخ أبيه أو غيره
            # ← تُحفظ في حقل abdullah_mark وتُحذف من موضع الرقم
            def mark(m):
                self.ahmad_marks[int(m.group(3).translate(AR))] = AHMAD_MARKS[m.group(2)]
                return m.group(1) + m.group(3)
            html = re.sub(r"(^|\n)\s*([•°*])\s*([٠-٩]+)", mark, html)
            # بعد حذف الرمز: «٦٨٨٥ (١) - » إحالة بين الرقم والشرطة (القاعدة العامة أعلاه سبقت الحذف)
            html = re.sub(r"(^|\n)([٠-٩]+)\s*(\([٠-٩]+\))\s*-\s*", r"\1\2 - \3 ", html)
            # «٨٥٧١/١ - » و«١١٠٧٣/ أ - »: أول الأجزاء هو الرقم، والباقي رقم فرعي «(م K)»
            html = re.sub(r"(^|\n)([٠-٩]+)\s*/\s*([٠-٩]+|[أ-ي])\s*-\s*",
                          lambda m: f"{m.group(1)}{m.group(2)} - " + ("" if m.group(3) in ("١", "أ") else f"(م {m.group(3)}) "), html)
            # «٢٢٢٩ م - » رقم فرعي بلا قوس، «١٩٨١ حَدَّثَنَا» رقم بلا شرطة، «٩٩٣٦، ٩٩٣٧ - » رقمان بفاصلة
            html = re.sub(r"(^|\n)([٠-٩]+) م\s*-\s*", r"\1\2 - (م) ", html)
            html = re.sub(r"(^|\n)([٠-٩]+) +(?=[ء-ي])", r"\1\2 - ", html)
            html = re.sub(r"(^|\n)([٠-٩]+)،\s*(?=[٠-٩]+\s*-)", r"\1\2 - ", html)
            # علامة تنصيص الحديث السابق في أول سطر الرقم («\n"١٦١٥٢- ») ← تُعاد إلى آخر السطر السابق
            html = re.sub(r'\n\s*((?:&quot;|")+)\s*(?=[٠-٩]+\s*-)', r"\1\n", html)
            pre = (self.current, len(self.current["_raw"]) if self.current else 0, len(self.records))
            self.toc_and_titles(html, vol, page, idx)
            self.ahmad_notes(notes, pre)
            return
        if self.book_id in RISALA_FN:
            # الشاهد ت الأرنؤوط: الحواشي بعد «_________» دائمًا؛ إحالتها «(^N)» (أبو داود) أو «(N)» (ابن ماجه)
            # ← تُوحَّد «(N)» وتُربط بسجلها كما في مسند أحمد، وحكم المحققين ← grades.arnaout
            # و«<hr>» فاصل في بعض الصفحات (أبو داود 72)، إلا أن يتلوه عنوان باب أو رقم حديث (٣٣٨٢)
            parts = re.split(r'_{9,}|<hr\s*/?>(?!\s*(?:<span[^>]*data-type="title"|[٠-٩]+\s*[-/م]))', html, maxsplit=1)
            if len(parts) == 2:
                html, notes = parts
            html, notes = (re.sub(r"\(\^([٠-٩]+)\)", r"(\g<1>)", x) for x in (html, notes))
            if idx < self.body_start:
                self.ahmad_front(html, vol, page, idx)
                return
            if self.book_id == 1424:
                # المستدرك ط الرسالة: «١٢٠٨/ ١ - » و«١٢٠٨/ ٢ - » أخبار تابعة للحديث ١٢٠٨ (لا أوله) ← «(م K)»؛
                # و«١/ ٨٣٠ - » مقلوب في ملف الشاملة (٧٣٩) ← «٨٣٠/ ١»؛ وتكرار الرقم نفسه «١٣٢ - … ١٣٢ - » ← «(م)»
                def sub_1424(m):
                    a, b = int(m.group(2).translate(AR)), int(m.group(3).translate(AR))
                    main, k = (b, m.group(2)) if a < b and b > 20 and a <= 20 else (a, m.group(3))
                    return f"{m.group(1)}{str(main).translate(str.maketrans('0123456789', '٠١٢٣٤٥٦٧٨٩'))} - (م {k}) "
                html = re.sub(r"(^|\n)\s*([٠-٩]+)\s*/\s*([٠-٩]+)\s*-\s*", sub_1424, html)
                prev = [self.last_num]

                def rep_1424(m):
                    n = int(m.group(2).translate(AR))
                    if n == prev[0]:
                        return f"{m.group(1)}{m.group(2)} - (م) "
                    prev[0] = n
                    return m.group(0)
                html = re.sub(r"(^|\n)([٠-٩]+)\s*-\s*(?!\s*\(م)", rep_1424, html)
            # «٢٢٩٩/ ١ - » أجزاء حديث واحد: الأول هو الرقم، والباقي رقم فرعي «(م K)»؛ «٣٦٤٠ حدَّثنا» رقم بلا شرطة
            html = re.sub(r"(^|\n)([٠-٩]+)\s*/\s*([٠-٩]+)\s*-\s*",
                          lambda m: f"{m.group(1)}{m.group(2)} - " + ("" if m.group(3) == "١" else f"(م {m.group(3)}) "), html)
            html = re.sub(r"(^|\n)([٠-٩]+)\s*م\s*-\s*", r"\1\2 - (م) ", html)  # «٥٧م - » إسناد آخر للحديث
            html = re.sub(r"(^|\n)([٠-٩]+) +(?=[ء-ي])", r"\1\2 - ", html)
            # «*٥٩٦ - » (زيادة أبي الحسن القطان) و«-١٨٤٠ - » و«،٤١٤٢ - »: رمز أو شرطة أو فاصلة قبل الرقم ← تُحذف
            html = re.sub(r"(^|\n)\s*[*\-،]\s*(?=[٠-٩]+\s*-)", r"\1", html)
            pre = (self.current, len(self.current["_raw"]) if self.current else 0, len(self.records))
            self.toc_and_titles(html, vol, page, idx)
            self.ahmad_notes(notes, pre)
            return
        if self.book_id == 181:
            # مسند أبي يعلى ت السناري 181 (شاهد): المدخل صفحة مطبوعة؛ ما بعد الفاصل (خط أو <hr>) تخريج المحقق كله
            # («٢٨٥ - قوى: أخرجه مسلم…»، وتتمته «= …» في الصفحة التالية، و«(*) هو: معدود من الصحابة» لعنوان المسند)
            # ← notes للحديث الذي رقمه كذلك، وحكمه (ما قبل أول «:») ← grades.sinari
            parts = SEP_ANY_HR.split(html, 1)
            if len(parts) == 2:
                html, notes = parts
            html = re.sub(r"(?m)^[ \t]*(?:\*[ \t]*){3,}$", "", html)  # «* * *» فاصل زخرفي آخر المسند
            # «٨٤٩ م - حدثنا…» و«N م ٢ - …»: رواية تابعة للحديث برقمه ← رقم فرعي «(م)» (كما في الأساس «مكرر»)
            html = re.sub(r"(^|\n)([٠-٩]+)[ \t]*م[ \t]*([٠-٩]+)?[ \t]*-[ \t]*",
                          lambda m: f"{m.group(1)}{m.group(2)} - (م{' ' + m.group(3) if m.group(3) else ''}) ", html)
            if idx < self.body_start:
                self.ahmad_front(html, vol, page, idx)  # مقدمة التحقيق وترجمة المؤلف
                return
            if self.volume_front(page, html):
                # صفحات أول كل مجلد (البسملة، العنوان، حقوق الطبع) ← سجل other موسوم volume_front، لا تتمة لآخر حديث
                if clean(html):
                    self.new("other", html, vol, page, idx)
                    self.current["volume_front"] = True
                return
            # خاتمة المجلد «آخر المجلد الأول، ويليه المجلد الثاني، وأوله: / مسند سعد…» وخاتمة الكتاب «تم الكتاب… / ويليه فهارس الكتاب»
            # ← حقل colophon في الحديث قبلها (ليست من نص أبي يعلى)
            cols = [clean(x) for x in re.findall(r"(?m)^[ \t]*((?:آخر المجلد|تم الكتاب)[^\n]*\n[^\n]*)$", html)]
            html = re.sub(r"(?m)^[ \t]*(?:آخر المجلد|تم الكتاب)[^\n]*\n[^\n]*$", "", html)
            # ذيل عنوان المسند خارج الوسم («…مالك - ﵁</span> - (*)») ← الشرطة داخل العنوان، وإحالة «(*)» تُحذف (حاشيتها في notes)
            html = re.sub(r"</span>[ \t]*(-)?[ \t]*(?:\(\*\))?[ \t]*(?=\n|$)", lambda m: (" -" if m.group(1) else "") + "</span>", html)
            n0 = len(self.records)
            self.toc_and_titles(html, vol, page, idx)
            if cols and self.current is not None:
                self.current.setdefault("colophon", []).extend(cols)
            self.sinari_notes(notes, n0)
            return
        parts = (SEP_ANY_HR if self.book_id in (1727, 735, 84) else SEP_RX).split(html, 1)  # فاصل الحواشي: خط _________ أو <hr>
        if len(parts) == 2:
            html, notes = parts
        body_sharh = []
        if self.collection == "ibnmajah" and self.book_id == 1198:
            # ابن ماجه 1198: شرح «[ش …]» في المتن بلا فاصل (تحت عنوان باب) ← حقل sharh
            body_sharh = [clean(m) for m in re.findall(r"(?m)^\s*(\[ش\s[^\n]*\])\s*$", html)]
            html = re.sub(r"(?m)^\s*\[ش\s[^\n]*\]\s*$\n?", "", html)
        self.toc_and_titles(html, vol, page, idx)
        if self.book_id == 2266 and getattr(self, "_talkhis", None):
            for num, g in self._talkhis:
                n = int(num.translate(AR)) if num else None
                rec = next((r for r in reversed(self.records[-5:]) if r["type"] == "hadith"
                            and n in r["numbers"]["printed"]), None) if n else None
                if n is None and self.current is not None and self.current["type"] == "hadith":
                    rec = self.current  # سطر تلخيص بلا رقم ← الحديث الذي قبله
                # رقم لا سجل له (رقمه في سطر التلخيص وحده، 2440 و7165 ونحوها) ← لا يُنسب إلى غيره
                if rec is None or not g:
                    self.stats["talkhis_unlinked"] = self.stats.get("talkhis_unlinked", 0) + 1
                    continue
                d = rec.setdefault("grades", {})
                d["dhahabi"] = d["dhahabi"] + "\n" + g if "dhahabi" in d else g
                self.stats["graded"] += 1
            self._talkhis = None
        if self.book_id == 28107 and getattr(self, "_azami_notes", None):
            if self.current is not None:
                self.current.setdefault("notes", []).extend(self._azami_notes)
                self.stats["notes"] += len(self._azami_notes)
            self._azami_notes = None
        if self.book_id == 36114 and notes:
            # الدارمي 36114: الحواشي سطر لكل «(N) …» (تخريج، فروق النسخ، لوحات «* ك ٢/أ») ← notes لآخر سجل في الصفحة
            lines = [clean(x) for x in notes.split("\n") if clean(x)]
            if lines and self.current is not None:
                self.current.setdefault("notes", []).extend(lines)
                self.stats["notes"] += len(lines)
            notes = ""
        if body_sharh and self.current is not None:
            self.current.setdefault("sharh", []).extend(body_sharh)
            self.stats["sharh"] = self.stats.get("sharh", 0) + len(body_sharh)
        if notes:
            # ما في الحاشية: أحاديث مثبتة من هامش المطبوع، ثم تعليقات الشاملة
            paras = re.split(r"\n\s*\n", notes)
            # ابن ماجه 1198: «[حكم الألباني]» في فقرة وحده والحكم في التالية ← تُضمّان
            joined = []
            for x in paras:
                if joined and re.fullmatch(r"\s*\[حكم الألباني\]\s*:?\s*", TAG.sub("", joined[-1])):
                    joined[-1] = joined[-1].rstrip() + " " + x.strip()
                else:
                    joined.append(x)
            paras = joined
            # ابن ماجه 1198: رؤوس «[تعليق محمد فؤاد عبد الباقي]» و«[شرح محمد فؤاد عبد الباقي]» تتلوها فقرات
            # إلى الرأس التالي ← حقلا notes و sharh (ليست من النص). لا توجد في غيره من الكتب المستخرجة.
            HEAD = r"\s*\[(تعليق|شرح) محمد فؤاد عبد الباقي\]\s*"
            if any(re.fullmatch(HEAD, TAG.sub("", x)) for x in paras):
                kept, mode = [], None
                for x in paras:
                    plain = TAG.sub("", x)
                    h = re.fullmatch(HEAD, plain)
                    if h:
                        mode = "notes" if h.group(1) == "تعليق" else "sharh"
                    elif re.match(r"\s*\[حكم الألباني\]", plain):
                        mode = None
                        kept.append(x)
                    elif mode and self.current is not None and clean(x):
                        self.current.setdefault(mode, []).append(clean(x))
                        self.stats[mode] = self.stats.get(mode, 0) + 1
                    elif not mode:
                        kept.append(x)
                paras = kept
            grades = [GRADE_RX.match(TAG.sub("", x)) for x in paras]
            if any(grades) and self.current is not None:
                for g in grades:
                    if g:
                        self.current.setdefault("grades", {})["albani"] = clean(g.group(1))
                        self.stats["graded"] += 1
            paras = [x for x, g in zip(paras, grades) if not g]
            margin = "\n\n".join(x for x in paras if not re.match(r"\s*(\(\^|\(تعليق)", TAG.sub("", x)))
            comments = [clean(x) for x in paras if re.match(r"\s*(\(\^|\(تعليق)", TAG.sub("", x))]
            if self.book_id == 1339:
                # النسائي ط الرسالة 1339 (شاهد): الحاشية كلها تخريج المحققين وتعليقهم («= وأخرجه…») لا أحاديث من الهامش
                margin, comments = "", [clean(x) for x in paras if clean(x)]
            if self.book_id in (1727, 735, 84):
                # شاهدا مسلم ت عبد الباقي والبخاري ت البغا: ما بعد الفاصل شرح المحقق كله، لا أحاديث من الهامش
                # (ومصنف عبد الرزاق ط التأصيل 84: فروق النسخ والغريب وأسطر التخريج «° [٥] [التحفة: …]»)
                margin, comments = "", [clean(x) for x in paras]
            if self.collection == "bazzar":
                # مسند البزار 12981 (الأجزاء ١٠–١٨): ما بعد الفاصل حواشي المحقق «(١) تحرف في المطبوع إلى…» لا أحاديث من الهامش
                margin, comments = "", [clean(re.sub(r"_{9,}", "", x)) for x in paras if clean(re.sub(r"_{9,}", "", x))]
            if self.book_id in (121382, 537):
                # شاهدا ابن خزيمة ط3 وابن حبان 537: ما بعد الفاصل حواشي المحقق وتخريجه («[١٥٤٣] م الصلاة…»)
                margin, comments = "", [clean(x) for x in paras if clean(x)]
            target = self.current
            if clean(margin):
                self.body(margin, vol, page, idx, margin=True)
            if comments and target is not None:
                target.setdefault("notes", []).extend(c for c in comments if c)
                self.stats["notes"] += len(comments)

    def khuzayma_grades(self, html):
        """صحيح ابن خزيمة 1446: سطر «<s0>N - قال الأعظمي: …» وما يتلوه إلى رقم الحديث التالي أو عنوان
        تعليقُ المحقق (وتعقيبات الألباني «قال الألباني: …»)، لا من النص ← يُحفظ جانبًا ويُترك مكانه علامة
        «⁅G k⁆» (أرقام لاتينية لئلا تُقرأ رقمَ حديث)، وتُنقل في finish() إلى grades.azami و grades.albani.
        وفاصل «_________» قبل تعقيب «(*) قال الألباني…» كذلك."""
        out, block = [], None

        def flush():
            if block is not None and block["lines"]:
                out.append(f"⁅G{len(self.kh_grades)}⁆")
                self.kh_grades.append(block)
        for line in html.split("\n"):
            plain = PAGE_MARK.sub("", TAG.sub("", line)).strip()
            if "<s0>" in line or re.fullmatch(r"_{9,}", plain):
                flush()
                content = TAG.sub("", line.split("<s0>", 1)[1]) if "<s0>" in line else ""
                m = re.match(r"\s*([٠-٩]+)\s*-\s*", content)
                block = {"n": int(m.group(1).translate(AR)) if m else None,
                         "lines": [content[m.end():].strip()] if m else ([content.strip()] if content.strip() else [])}
                continue
            if block is not None:
                if not plain:
                    out.append(line)  # سطر فارغ أو علامة صفحة: يبقى في النص ولا يقطع التعليق
                    continue
                if re.match(r"[٠-٩]+\s*-", plain) or 'data-type="title"' in line:
                    flush()
                    block = None
                else:
                    block["lines"].append(plain)
                    continue
            out.append(line)
        flush()
        return "\n".join(out)

    def hibban_entry(self, html, vol, page, idx):
        """صحيح ابن حبان (الإحسان) ت الأرنؤوط 1729.
        - الحواشي بعد «_________» أو «<hr>»؛ إحالاتها في النص أرقام ملصقة («أقطع"١.») أو «(١)» أو «(^١)»
          ← تُوحَّد «(N)» وتُربط بسجلها كما في مسند أحمد، وحكم المحقق ← grades.arnaout.
        - «[٦٦:٣]» بعد الحديث رقم القسم والنوع في «التقاسيم والأنواع» ← حقل taqasim (ليس من النص).
        - عيب في ملف الشاملة (652 موضعًا): أول الحديث مكرر مبتورًا يلتصق به عنوان «ذكر…» (أو فقرة قبله)،
          ثم «[N]» والحديث كاملًا ← يؤخذ ما بعد «[N]»، ويُحفظ المكرر المبتور في duplicate_fragment.
        - «١-<span>» رقم الكتاب/الباب قبل وسم العنوان ← data-num؛ وسطر «٥- كِتَابُ … بَابُ …» عنوان مطبوع
          مكرر لوسوم العناوين ← printed_heading في أول عنوان من المدخل، و«…» قبله يُحذف."""
        html = "\n" + html  # تتمة الحديث من المدخل السابق تبدأ سطرًا جديدًا لا تلتصق بآخره
        parts = re.split(r"_{9,}|<hr\s*/?>", html, maxsplit=1)
        if len(parts) == 1:
            # فاصل الحواشي ساقط في بعض الصفحات: أول سطر يبدأ بإحالة «١ إسناده…» أو بتتمة حاشية «= …»
            parts = re.split(r"(?m)^(?=[ \t]*(?:\(?\^?[٠-٩]{1,2}\)?[ \t]*(?=[^\s٠-٩\-/])|=))", html, maxsplit=1)
            if len(parts) == 2:
                self.stats["hb_notes_without_separator"] = self.stats.get("hb_notes_without_separator", 0) + 1
        body, notes = (parts + [""])[:2]
        # رقم مفرد في سطر وحده («٥ -») بقية ترقيم أبواب الطبعة، لا حديث
        body, k = re.subn(r"(?m)^[ \t]*[٠-٩]{1,2}[ \t]*-[ \t]*$", "", body)
        if k:
            self.stats["hb_lone_numbers"] = self.stats.get("hb_lone_numbers", 0) + k
        # (أ) المكرر المبتور: «N - …ذكر…\n[N] …» (وقد يقع «[N]» وسط السطر)
        for m in reversed(list(re.finditer(r"\[([٠-٩]+)\][ \t]*", body))):
            prior = None
            for p in re.finditer(r"(?:^|\n)[ \t]*" + m.group(1) + r"\s*-\s*", body[:m.start()]):
                prior = p
            if prior is None:
                body = body[:m.start()] + "\n" + m.group(1) + " - " + body[m.end():]
                self.stats["hb_bracket_no_prior"] = self.stats.get("hb_bracket_no_prior", 0) + 1
                continue
            frag = body[prior.end():m.start()]
            body = body[:prior.end()] + f"⁅D{len(self.hb_dups)}⁆" + body[m.end():]
            self.hb_dups.append(clean(frag))
        # (ب) رقم القسم والنوع
        body = re.sub(r"\[\s*([٠-٩]+)\s*[:/]\s*([٠-٩]*)\s*\]",
                      lambda m: f"⁅T{m.group(1).translate(AR)}:{m.group(2).translate(AR)}⁆", body)
        # وبلا قوسين في آخر السطر («… يتوضأ. ١٠٠:»)
        body = re.sub(r"(?m)(?<=[.\"»”]) *([٠-٩]{1,3}) *: *([٠-٩]{0,3}) *$",
                      lambda m: f"⁅T{m.group(1).translate(AR)}:{m.group(2).translate(AR)}⁆", body)
        # (ج) العناوين المطبوعة المكررة، و«…» قبلها
        heads = []
        def head(m):
            heads.append(clean(m.group(2)))
            return m.group(1)
        body = re.sub(r"(^|\n)[ \t]*[٠-٩]+\s*-\s*((?:كِتَابُ|كتاب|بَابُ|باب)[^\n<]*)(?=\n|$)", head, body)
        body = re.sub(r"(^|\n)[ \t]*…[ \t]*(?=\n|$)", r"\1", body)
        # (د) رقم قبل وسم العنوان ← data-num؛ وسم بلا مستوى يطابق عنوان المستوى الأول في الفهرس ← مستوى 1
        body = re.sub(r"(^|\n)[ \t]*([٠-٩]+)\s*-\s*((?:بَابُ|بَاب|باب)\s*)?<span([^>]*)>",
                      r'\1<span data-num="\2"\4>\3', body)
        bare = lambda s: re.sub(r"[ً-ْٰ\s\[\]]", "", clean(s))
        tops = {bare(t) for t in self.toc_top.get(idx, [])}
        if tops:
            body = re.sub(r'<span ([^>]*data-type="title"[^>]*)>(.*?)</span>',
                          lambda m: (f'<span data-level="1" {m.group(1)}>{m.group(2)}</span>'
                                     if "data-level" not in m.group(1) and bare(m.group(2)) in tops else m.group(0)),
                          body, flags=re.S)
        # (هـ) إحالات الحواشي ← «(N)»: «(^N)»، و«(N)»، والرقم الملصق خارج الأقواس والوسوم وأول السطر
        body = re.sub(r"\(\^([٠-٩]+)\)", r"(\1)", body)
        mask = re.compile(r"<[^>]+>|\[[^\]\n]*\]|\([^)\n]*\)|⦗[^⦘]*⦘|⁅[^⁆]*⁆|(?:^|(?<=\n))[ \t]*[٠-٩]+\s*-\s*")
        def refs(seg):
            return re.sub(r"(?<![٠-٩])([٠-٩]{1,2})(?![٠-٩])", r"(\1)", seg)
        out, pos = [], 0
        for m in mask.finditer(body):
            out.append(refs(body[pos:m.start()]))
            out.append(m.group(0))
            pos = m.end()
        out.append(refs(body[pos:]))
        body = "".join(out)
        # الحواشي: «١إسناده…» و«(١) …» و«(^١) …» في أول السطر ← «(N) …»
        notes = re.sub(r"(?m)^[ \t]*\(?\^?([٠-٩]{1,2})\)?(?![٠-٩/])[ \t]*", r"(\1) ", notes)
        n0 = len(self.records)
        pre = (self.current, len(self.current["_raw"]) if self.current else 0, len(self.records))
        self.toc_and_titles(body, vol, page, idx)
        self.ahmad_notes(notes, pre)
        if heads:
            first = next((r for r in self.records[n0:] if r["type"] in ("top", "bab")), None)
            if first is not None:
                first.setdefault("printed_heading", []).extend(heads)
            else:
                self.stats["hb_heading_unattached"] = self.stats.get("hb_heading_unattached", 0) + 1

    def bayhaqi_entry(self, html, vol, page, idx):
        """السنن الكبير للبيهقي ت التركي 148486: المدخل صفحة مطبوعة.
        - مقدمة التحقيق قبل «مقدمة المصنف» (فيها قوائم شيوخ مرقمة «٧٧ - …» ليست أحاديث) ← نص مقدمة واحد،
          و«فهرس مراجع التحقيق» بعد آخر كتاب ← لا يُستخرج.
        - الحواشي بعد «_________» (أو «<hr>» في ثلاثة مداخل)، وإحالاتها «(^N)» و«(*)» في النص ← علامة «⁅nN⁆»
          (لا «(N)»: أرقام الآيات «﴿…(١) …﴾» في النص بالصيغة نفسها) وتُربط كل حاشية بالسجل الذي فيه إحالتها.
        - «١٠٨٣ م- » إسناد آخر للحديث ← رقم فرعي «(م)»."""
        if idx < self.body_start:
            self.ahmad_front(SEP_ANY_HR.split(html, 1)[0], vol, page, idx)
            return
        if idx >= self.body_end:
            self.stats["skipped_entries"] = self.stats.get("skipped_entries", 0) + 1
            return
        parts = SEP_ANY_HR.split(html, 1)
        body, notes = (parts + [""])[:2]
        body = re.sub(r"\(\^([٠-٩]+)\)|\(\*\)", lambda m: f"⁅n{m.group(1) or '*'}⁆", body)
        # وسم عنوان الباب يبتلع رقم الحديث بعده («بَابُ … ﴿…﴾ [التوبة: ١٠٣]\n\n٢٩١٣</span> - أخبرنا»، 11 موضعًا)
        # ← يُغلق العنوان قبل الرقم
        body = re.sub(r"\n\s*([٠-٩]+)\s*</span>(\s*-)", r"</span>\n\1\2", body)
        body = re.sub(r"(^|\n)([٠-٩]+)\s*م\s*-\s*", r"\1\2 - (م) ", body)
        pre = (self.current, len(self.current["_raw"]) if self.current else 0, len(self.records))
        self.toc_and_titles(body, vol, page, idx)
        self.bayhaqi_notes(notes, pre)

    def bayhaqi_notes(self, notes, pre):
        """البيهقي 148486: حاشية «(^N) …» ← notes السجل الذي فيه «⁅nN⁆» في الصفحة نفسها؛ وما في أول الحواشي بلا رقم
        تتمة آخر حاشية في الصفحة السابقة."""
        cur0, off0, n0 = pre
        cands = ([(cur0, cur0["_raw"][off0:])] if cur0 is not None else []) + [(r, r["_raw"]) for r in self.records[n0:]]
        where = {}
        for r, seg in cands:
            for n in r.get("_refs", []) + re.findall(r"⁅n([٠-٩]+|\*)⁆", seg):
                where.setdefault(n, r)
        # «(^N)» قبل clean() لأنها تحذف هذه الصيغة
        text = clean(re.sub(r"\(\^([٠-٩]+)\)", r"⁅n\1⁆", notes))
        if not text:
            return
        blocks = []
        for line in text.split("\n"):
            m = re.match(r"(?:⁅n([٠-٩]+)⁆|\((\*)\))\s*", line)
            if m:
                blocks.append([m.group(1) or "*", line[m.end():]])
            elif blocks:
                blocks[-1][1] += "\n" + line
            else:
                blocks.append([None, line])
        for num, body in blocks:
            body = body.strip()
            if num is None:
                if self.last_note is not None:
                    rec, i = self.last_note
                    rec["notes"][i] = rec["notes"][i] + "\n" + body
                    self.stats["note_continued"] += 1
                else:
                    self.stats["note_orphan"] += 1
                continue
            rec = where.get(num)
            if rec is None:
                self.stats["note_unlinked"] += 1
                rec = self.current
            if rec is None or not body:
                continue
            rec.setdefault("notes", []).append(body)
            self.last_note = (rec, len(rec["notes"]) - 1)
            self.stats["notes"] += 1

    def toc_and_titles(self, html, vol, page, idx):
        # حدود الكتب من فهرس الشاملة (المستوى الأول): كثير منها بلا عنوان في المتن.
        # إن لم يكن في المدخل عنوان من المستوى الأول أُنشئ سجل بعنوان الفهرس ووُسم بذلك.
        toc_titles = self.toc_top.get(idx, [])
        if toc_titles and not any(level_of(m.group(0)) == 1 for m in TITLE.finditer(html)):
            for t in toc_titles:
                self.new("top", "", vol, page, idx, title=t)
                self.current["title_from"] = "shamela_toc"
        last = 0
        for m in TITLE.finditer(html):
            self.body(html[last:m.start()], vol, page, idx)
            t, lvl = clean(m.group(1)), level_of(m.group(0))
            refs = []
            if self.collection == "ahmad" or self.book_id == 1729:
                # مسند أحمد: إحالة حاشية في العنوان («مسند أبي بكر الصديق (١)») ← تُحفظ لربط الحاشية وتُحذف من العنوان
                refs = re.findall(r"\(([٠-٩]+|\*)\)", t)
                t = re.sub(r"\s*\((?:[٠-٩]+|\*)\)", "", t)
            if self.book_id == 148486:
                # البيهقي ت التركي: إحالة حاشية في العنوان «⁅nN⁆» ← تُحفظ لربط الحاشية في السجل وتُحذف من العنوان
                refs = re.findall(r"⁅n([^⁆]*)⁆", t)
                t = re.sub(r"\s*⁅n[^⁆]*⁆", "", t).strip()
            if lvl == 1:
                self.new("top", "", vol, page, idx, title=t)
                if self.collection == "malik":
                    # الموطأ ت عبد الباقي: ترقيم الأحاديث يبدأ من ١ في كل كتاب
                    self.last_num, self.used = 0, set()
            else:
                self.bab = {"n": self.bab["n"] + 1, "title": t}
                self.new("bab", "", vol, page, idx, title=t)
                if self.collection in TABARANI:
                    self.current["toc_level"] = lvl  # الكبير: ٢ الصحابي، ٣–٥ ما تحته (صفته، ما رواه فلان عنه…)
                    hn = re.search(r'data-heading-num="([٠-٩]+)"', m.group(0))
                    if hn:
                        n = int(hn.group(1).translate(AR))
                        self.current["heading_number"] = {"printed": n, **({"series": self.series} if self.series else {})}
                        self.used.add(n)
                        if self.last_num < n <= self.last_num + 300:
                            self.last_num = n
                if self.book_id == 1729:
                    # ابن حبان 1729: الباب (2) ثم «ذكر…» (3، 4) ← مستوى العنوان في الفهرس
                    self.current["level"] = lvl
                num = re.search(r'data-num="([٠-٩]+)"', m.group(0))
                if num:
                    self.current["bab_number"] = int(num.group(1).translate(AR))
                num2 = re.search(r'data-num2="([٠-٩]+)"', m.group(0))
                if num2:
                    self.current["bab_number_global"] = int(num2.group(1).translate(AR))
            if refs:
                self.current["_refs"] = refs
            last = m.end()
        self.body(html[last:], vol, page, idx)

    def ahmad_front(self, html, vol, page, idx):
        """مسند أحمد 25794: مقدمات الطبعة قبل أول مسند — نص مقدمة واحد متصل، لا أحاديث ولا أبواب."""
        for t in self.toc_top.get(idx, []):
            self.new("top", "", vol, page, idx, title=t)
            self.current["title_from"] = "shamela_toc"
        txt = TITLE.sub(lambda m: "\n" + m.group(1) + "\n", html)
        if not clean(txt):
            return
        if self.current is not None and self.current["type"] == "front":
            self.append("\n" + txt)
        else:
            self.new("front", txt, vol, page, idx)

    def volume_front(self, page, html):
        """مسند أبي يعلى ت السناري 181: صفحات أول كل مجلد (البسملة، العنوان «٢١٠ - ٣٠٧ هـ»، حقوق الطبع): صفحة ١–٤ بلا عنوان ولا رواية."""
        return (self.book_id == 181 and isinstance(page, int) and page <= 4 and "data-type" not in html
                and not re.search(r"حد\S*ثن|أخبرن", re.sub(r"[ً-ْٰ]", "", html)))

    def sinari_notes(self, notes, n0):
        """مسند أبي يعلى ت السناري 181: سطر «N - حكم: تخريج…» يبدأ تخريج الحديث N (من أحاديث الصفحة أو قبلها قليلًا)؛
        وما بعده إلى السطر التالي من هذا النوع تتمته («= …» أول الصفحة تتمة تخريج الصفحة السابقة)؛ و«(*) …» حاشية
        عنوان المسند في الصفحة. الأرقام الصغيرة «١ - حماد بن زيد…» داخل التخريج تعداد، لا رأس تخريج."""
        if not clean(notes):
            return
        recent = {}
        for r in self.records[-80:]:
            if r["type"] == "hadith" and "sub" not in r["numbers"]:
                for n in r["numbers"]["printed"]:
                    recent[n] = r
        heads = [r for r in self.records[n0:] if r["type"] in ("top", "bab")]
        last_n = getattr(self, "sinari_last", 0)
        for line in clean(notes).split("\n"):
            # رأس التخريج: «٢٨٥ - » أو لأكثر من حديث «٣٧٣ و٣٧٤ - »، «٢٢٦٩ - ٢٢٧٠ - »
            m = re.match(r"([٠-٩]+(?:\s*(?:و|،|-)\s*[٠-٩]+)*)\s*-\s*", line)
            ns = [int(x.translate(AR)) for x in re.findall(r"[٠-٩]+", m.group(1))] if m else []
            g = SINARI_GRADE.match(line[m.end():]) if m else None
            recs = [recent[n] for n in ns if n in recent and n >= last_n]
            if m and not recs and g:
                # رأس بحكم ورقمه مصحَّف («٢ - ضعيف:» عند الحديث ٢١) ← أول حديث بعد آخر حديث رُبط به تخريج، بلا تخريج بعد
                recs = [r for n, r in sorted(recent.items()) if n > last_n and not r.get("notes")][:1]
                if recs:
                    self.stats["sinari_note_by_order"] += 1
            if recs:
                body = line[m.end():]
                last_n = max(max(r["numbers"]["printed"]) for r in recs)
                for rec in recs:
                    if g and "sinari" not in rec.get("grades", {}):
                        rec.setdefault("grades", {})["sinari"] = g.group(1).strip()
                        self.stats["graded_sinari"] += 1
                    rec.setdefault("notes", []).append(body)
                    self.stats["notes"] += 1
                self.last_note = (recs[-1], len(recs[-1]["notes"]) - 1)
                continue
            elif line.startswith("(*)") and (heads or self.current is not None):
                rec, body = (heads[-1] if heads else self.current), line[3:].strip()
            elif self.last_note is not None:
                rec, i = self.last_note
                rec["notes"][i] += "\n" + re.sub(r"^=\s*", "", line)
                self.stats["note_continued"] += 1
                continue
            else:
                self.stats["note_orphan"] += 1
                continue
            rec.setdefault("notes", []).append(body)
            self.last_note = (rec, len(rec["notes"]) - 1)
            self.stats["notes"] += 1
        self.sinari_last = last_n

    def ahmad_notes(self, notes, pre):
        """مسند أحمد 25794: حواشي المحققين «(N) …» تُربط بالسجل الذي فيه الإحالة (N) في المدخل نفسه.
        تتمة حاشية الصفحة السابقة (بلا رقم، وتبدأ غالبًا بـ«=») تُلحق بآخر حاشية."""
        cur0, off0, n0 = pre
        cands = ([(cur0, cur0["_raw"][off0:])] if cur0 is not None else []) + \
                [(r, r["_raw"]) for r in self.records[n0:]]
        where = {}
        if self.book_id == 98139:
            # ت شاكر: رقم الحاشية «(١٢) إسناده صحيح» هو رقم الحديث نفسه، لا إحالة في النص
            # ← يُربط بالحديث الذي رقمه كذلك، في المدخل أو قبله (الحديث يبدأ في صفحة سابقة)
            for r in reversed(self.records[-400:]):
                if r["type"] == "hadith" and "sub" not in r["numbers"] and r["numbers"]["printed"]:
                    where.setdefault(str(r["numbers"]["printed"][0]).translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")), r)
            cands = []
        for r, seg in cands:
            for n in r.get("_refs", []) + re.findall(r"\(([٠-٩]+|\*)\)", TAG.sub("", seg)):
                where.setdefault(n, r)
        if not clean(notes):
            return
        blocks = []
        for line in clean(notes).split("\n"):
            m = re.match(r"\(([٠-٩]+|\*)\)\s*", line)
            if m:
                blocks.append([m.group(1), line[m.end():]])
            elif blocks:
                blocks[-1][1] += "\n" + line
            else:
                blocks.append([None, line])
        for num, body in blocks:
            body = body.strip()
            if num is None:
                if self.last_note is not None:
                    rec, i = self.last_note
                    rec["notes"][i] = rec["notes"][i].rstrip(" =") + "\n" + body.lstrip("= ").strip()
                    self.stats["note_continued"] += 1
                else:
                    self.stats["note_orphan"] += 1
                continue
            rec = where.get(num)
            if rec is None:
                self.stats["note_unlinked"] += 1
                rec = self.current
            if rec is None:
                continue
            rec.setdefault("notes", []).append(body)
            rec.setdefault("_note_refs", []).append(num)
            self.last_note = (rec, len(rec["notes"]) - 1)
            self.stats["notes"] += 1

    def finish(self):
        for r in self.records:
            raw = r.pop("_raw")
            if self.book_id == 1446:
                # ابن خزيمة: تعليق المحقق (علامته ⁅G k⁆) ← grades.azami، وتعقيب الألباني ← grades.albani
                for m in re.finditer(r"⁅G(\d+)⁆", raw):
                    blk = self.kh_grades[int(m.group(1))]
                    g, key = {}, "azami"
                    for line in blk["lines"]:
                        line = re.sub(r"^\(\*\)\s*", "", clean(line))
                        km = re.match(r"قال (الأعظمي|الأعظي|الألباني)\s*:?\s*", line)
                        if km:
                            key = "albani" if km.group(1) == "الألباني" else "azami"
                            line = line[km.end():]
                        if line:
                            g[key] = g[key] + "\n" + line if key in g else line
                    grades = r.setdefault("grades", {})
                    for k, v in g.items():
                        grades[k] = grades[k] + "\n" + v if k in grades else v
                    self.stats["graded"] += 1
                    if r["type"] != "hadith":
                        self.stats["kh_grade_not_on_hadith"] = self.stats.get("kh_grade_not_on_hadith", 0) + 1
                    elif blk["n"] is not None and blk["n"] not in r["numbers"]["printed"]:
                        self.stats["kh_grade_number_mismatch"] = self.stats.get("kh_grade_number_mismatch", 0) + 1
                raw = re.sub(r"⁅G\d+⁆", "", raw)
            if self.book_id == 1729:
                # ابن حبان: رقم القسم والنوع ← taqasim؛ المكرر المبتور ← duplicate_fragment
                tq = re.findall(r"⁅T(\d+):(\d+)⁆", raw)
                if tq:
                    r["taqasim"] = [f"{a}:{b}" for a, b in tq]
                dups = [self.hb_dups[int(k)] for k in re.findall(r"⁅D(\d+)⁆", raw)]
                if dups:
                    r["duplicate_fragment"] = dups
                raw = re.sub(r"⁅[TD][^⁆]*⁆", "", raw)
            if self.book_id == 537:
                ih = [int(x) for x in re.findall(r"⁅I(\d+)⁆", raw)]
                if ih:
                    r["concordance"] = [{"ihsan": x} for x in ih]
                raw = re.sub(r"⁅I\d+⁆", "", raw)
            if self.book_id == 121382:
                raw = re.sub(r"\s*\([٠-٩]+\)", "", raw)  # إحالات الحواشي (الحاشية في notes)
            if self.book_id == 148486:
                r.pop("_refs", None)
                raw = re.sub(r"[ \t]*⁅n[^⁆]*⁆", "", raw)  # إحالات الحواشي (الحاشية في notes)
            if self.collection == "bazzar" and r.get("notes"):
                # مسند البزار: إحالات الحواشي «(١)» في نص سجل له حواشٍ ← تُحذف (الحاشية في notes)؛ لا ما بين ﴿ ﴾ (أرقام الآيات)
                raw = "".join(x if x.startswith("﴿") else re.sub(r"\s*\([٠-٩]\)", "", x)
                              for x in re.split(r"(﴿[^﴾]*﴾)", raw))
            if self.collection == "ahmad" or self.book_id in RISALA_FN or self.book_id == 1729:
                r.pop("_refs", None)
                note_refs = r.pop("_note_refs", [])
                if r["type"] == "hadith" and "sub" not in r["numbers"] and r["numbers"]["printed"]:
                    mk = self.ahmad_marks.get(r["numbers"]["printed"][0])
                    if mk:
                        r["abdullah_mark"] = mk
                # إحالات الحواشي «(١)» في النص ← تُحذف (الحاشية في notes)
                last_ref = (re.findall(r"\(([٠-٩]+|\*)\)", TAG.sub("", raw)) or [None])[-1]
                raw = re.sub(r"\s*\((?:[٠-٩]+|\*)\)", "", raw)
                if r["type"] == "hadith" and r.get("notes") and self.book_id == 98139:
                    # ت شاكر: حواشي الحديث كلها حواشيه؛ الحكم أول جملة من أول حاشية تبدأ بلفظ حكم ← grades.shakir
                    g = next((m for m in map(AHMAD_GRADE.match, r["notes"]) if m), None)
                    if g:
                        r.setdefault("grades", {})["shakir"] = g.group(1).split("،")[0].strip()
                        self.stats["graded"] += 1
                elif r["type"] == "hadith" and r.get("notes"):
                    # حكم المحققين: أول جملة من حاشية آخر إحالة في الحديث إن بدأت بلفظ حكم
                    # أرقام الحواشي تبدأ من ١ في كل صفحة: آخر حاشية بهذا الرقم هي حاشية آخر إحالة
                    i = max((k for k, n in enumerate(note_refs) if n == last_ref), default=None)
                    g = AHMAD_GRADE.match(r["notes"][i]) if i is not None else None
                    if not g:  # حاشية آخر إحالة في اللفظ لا في الحكم ← أول حاشية تبدأ بلفظ حكم
                        g = next((m for m in map(AHMAD_GRADE.match, r["notes"]) if m), None)
                    if g:
                        # الحكم إلى أول فاصلة، إلا أن يتلوها حكم الإسناد («حديث صحيح، وهذا إسناد ضعيف»)
                        parts = g.group(1).split("،")
                        grade = parts[0]
                        if len(parts) > 1 and re.match(r"\s*و(?:هذا إسناد|إسناده|هذا الإسناد)", parts[1]):
                            grade += "،" + parts[1]
                        r.setdefault("grades", {})["risala" if self.book_id == 1424 else "arnaout"] = grade.strip()
                        self.stats["graded"] += 1
            # حكم الألباني داخل النص بلا فاصل <hr> ← حقل grades
            for m in INLINE_GRADE.finditer(raw):
                r.setdefault("grades", {})["albani"] = clean(m.group(1))
                self.stats["graded"] += 1
            raw = INLINE_GRADE.sub("\n", raw)
            if self.book_id == 84:
                raw = raw.replace("⁣", "")
                if r["type"] == "hadith" and r["numbers"]["printed"] and r["numbers"]["printed"][0] in self.tasil_kind:
                    r["tasil_kind"] = self.tasil_kind[r["numbers"]["printed"][0]]
            if self.book_id == 28107:
                raw = raw.replace("⁣", "")
                if r["type"] == "hadith" and r["numbers"]["printed"] and r["numbers"]["printed"][0] in self.azami_k:
                    r["numbers"]["azami_hadith"] = self.azami_k[r["numbers"]["printed"][0]]
            if self.collection in TABARANI:
                raw = raw.replace("⁣", "")  # علامة الرقم في آخر المدخل (entry)
            if self.book_id == 36114:
                # سطر المقابلة بالطبعات «[ب ١٥١٠، د ١٥٨٧، ع ١٥٤٦، ف ١٦٦٧، م ١٥٥٣] تحفة ٤٥١٢، إتحاف ٥٩٦٩» ← حقل concordance
                # (د = طبعة الداراني = ت حسين أسد، الأساس 21795؛ الرموز في مقدمة المحقق)
                for cm in re.finditer(r"\[([^\]\n]*?د\s*[٠-٩]+[^\]\n]*)\]([^\n]*)", raw):
                    conc = {s: int(n.translate(AR)) for s, n in re.findall(r"([بدعفم])\s*([٠-٩]+)", cm.group(1))}
                    if conc:
                        r.setdefault("concordance", []).append(conc)
                    if clean(cm.group(2)).strip(" .،"):
                        r.setdefault("concordance_refs", []).append(clean(cm.group(2)).strip(" ."))
                raw = re.sub(r"\[[^\]\n]*?د\s*[٠-٩]+[^\]\n]*\][^\n]*", "\n", raw)
                # إحالات الحواشي «(١)» و«*» علامة لوحة المخطوط ← تُحذف من النص (الحاشية في notes)
                raw = re.sub(r"\s*\([٠-٩]+\)|\*|⁣", "", raw)
            if self.collection == "darimi":
                # حكم المحقق حسين أسد (سطر «[تعليق المحقق] إسناده صحيح…») ← grades.husayn_asad (ليس من النص)
                asad = [clean(m.group(1)) for m in re.finditer(r"\[تعليق المحقق\][ \t]*([^\n]*)", raw)]
                if asad:
                    r.setdefault("grades", {})["husayn_asad"] = "\n".join(a for a in asad if a)
                    self.stats["graded_asad"] = self.stats.get("graded_asad", 0) + 1
                raw = re.sub(r"\[تعليق المحقق\][ \t]*[^\n]*", "\n", raw)
            if self.book_id == 12520:
                # مسند أبي يعلى ت حسين أسد: سطر «[حكم حسين سليم أسد]: إسناده ضعيف» ← grades.husayn_asad (ليس من النص)
                asad = [clean(m.group(1)) for m in re.finditer(r"\[حكم حسين سليم أسد\][ \t]*:?[ \t]*([^\n]*)", raw)]
                if asad:
                    r.setdefault("grades", {})["husayn_asad"] = "\n".join(a for a in asad if a)
                    self.stats["graded_asad"] = self.stats.get("graded_asad", 0) + 1
                    if r["type"] != "hadith":
                        self.stats["asad_grade_not_on_hadith"] = self.stats.get("asad_grade_not_on_hadith", 0) + 1
                raw = re.sub(r"\[حكم حسين سليم أسد\][ \t]*[^\n]*", "\n", raw)
            # إحالات الآيات التي يضيفها محقق الشاملة «[البقرة: ٢٢٢]» ← حقل verse_refs (ليست من نص الحديث)
            if self.collection == "adabmufrad" and r["type"] == "hadith" and r["numbers"]["printed"]:
                # الرقم نفسه مطبوعًا ثانيةً في أول سطر داخل الحديث (إسناد ثانٍ أو تتمة: ٣٤٢، ٥٠١…) ← يُحذف الرقم ويبقى السطر
                n_ar = str(r["numbers"]["printed"][0]).translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))
                raw, k = re.subn(rf"(\n[ \t]*){n_ar}\s*-\s*", r"\1", raw)
                self.stats["adab_repeated_number"] += k
            if self.book_id == 9647:
                # عدّاد الآثار عند الزهيري «(ث N)» ← numbers.athar
                am = re.search(r"⁤([٠-٩]+)⁤", raw)
                if am and r["type"] == "hadith":
                    r["numbers"]["athar"] = int(am.group(1).translate(AR))
                raw = re.sub(r"⁤[٠-٩]+⁤", "", raw)
            if self.collection in ("nasaikubra", "tahawi", "adabmufrad"):
                # إحالة آية سورة اسمها حرف واحد «[ص: ٣٥]»، «[ق: ١]» (لا يلتقطها VERSE_REF) ← verse_refs
                one = re.findall(r"\s*\[([صقن]:\s*[٠-٩]+(?:\s*[-–،,]\s*[٠-٩]+)*)\]", raw)
                if one:
                    r.setdefault("verse_refs", []).extend(one)
                    raw = re.sub(r"\s*\[[صقن]:\s*[٠-٩]+(?:\s*[-–،,]\s*[٠-٩]+)*\]", "", raw)
            if (self.collection in ("ibnmajah", "malik", "adabmufrad", "nasaikubra", "tahawi", "abuyala", "bazzar")
                    or self.collection in TABARANI):
                # (وأبو يعلى 12520 والبزار 12981 كذلك)
                # وسم بحر الشعر «[البحر الطويل]» من محقق الشاملة ← حقل meter (ليس من النص)
                meters = re.findall(r"\[(البحر [^\]\n]{2,15})\]", raw)
                if meters:
                    r["meter"] = meters
                    raw = re.sub(r"\[البحر [^\]\n]{2,15}\]", "", raw)
            if self.collection == "ibnmajah":
                # خاتمة الناسخ بعد آخر حديث «وهذا آخر سنن…» ← حقل colophon
                cm = re.search(r"\n\s*(وهذا آخر سنن[^\n]*)\s*$", raw)
                if cm:
                    r["colophon"] = clean(cm.group(1))
                    raw = raw[:cm.start()]
            if self.book_id == 9771 and r["type"] == "hadith" and r["numbers"]["printed"]:
                # سنن الدارقطني 9771: رقم الحديث مكررًا في أول سطر داخل نصه (إسناد آخر له في ملف الشاملة) ← يُحذف ويُعدّ
                own = str(r["numbers"]["printed"][0]).translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))
                raw, k = re.subn(r"(\n(?:<[^>]+>|[ \t])*)" + own + r"\s*-\s*", r"\1", raw)
                if k:
                    r["numbers"]["repeated_in_source"] = r["numbers"].get("repeated_in_source", 0) + k
            if self.book_id == 1424:
                # المستدرك ط الرسالة: خاتمة الكتاب بعد آخر حديث «آخر كتاب الأهوال وهو آخر كتاب…» ← حقل colophon
                cm = re.search(r"\n\s*(آخر كتاب الأهوال[\s\S]*)$", raw)
                if cm:
                    r["colophon"] = clean(cm.group(1))
                    raw = raw[:cm.start()]
            if self.book_id == 333:
                # مصنف ابن أبي شيبة 333: إحالة «[*]» إلى حاشية مُعِدّ الشاملة (الحاشية في notes)
                raw = re.sub(r"[ \t]*\[\*m?\][ \t]*", " ", raw)
                # حكم الشثري: آخر حاشية تبدأ بلفظ حكم («منقطع؛ …»، «صحيح، أخرجه…»، «مرسل.») ← grades.shathri
                # (الحاشية تبقى في notes كاملة)
                if r["type"] == "hadith" and r.get("notes"):
                    lines = [x for n in r["notes"] for x in n.split("\n")]  # حواشي الصفحة سطر لكل إحالة
                    g = next((m for m in map(SHATHRI_GRADE.match, reversed(lines)) if m), None)
                    if g:
                        r.setdefault("grades", {})["shathri"] = g.group(1).strip()
                        self.stats["graded_shathri"] = self.stats.get("graded_shathri", 0) + 1
            if self.book_id == 735:
                # البخاري ت البغا: إحالاته إلى مواضع الحديث الأخرى (وسمها entry) ← حقل cross_refs
                xr = re.findall(r'data-xref="([^"]*)"', raw)
                if xr:
                    r["cross_refs"] = [int(x) for g in xr for x in g.split(",") if x]
            refs = [clean(m.group(0))[1:-1] for m in VERSE_REF.finditer(raw)]
            if refs:
                r["verse_refs"] = refs
                raw = VERSE_REF.sub("", raw)
            r["text"] = clean(raw)
            if r["type"] == "hadith":
                matn = " ".join(clean(m) for m in MATN.findall(raw) if clean(m))
                narr = [{"id": int(i), "name": clean(n)} for i, n in NARRATOR.findall(raw)]
                if matn:
                    r["matn"] = matn
                if narr:
                    r["narrators"] = narr
            # ترتيب الحقول: النص بعد loc
            if "notes" in r:
                r["notes"] = r.pop("notes")
        for r in self.records:
            if r["type"] == "hadith" and not re.search("[ء-ي]", r["text"]):
                r["text"] = ""
                r["editor_omitted"] = True  # الرقم في المتن والنص في حاشية المحقق (notes)
        self.records = [r for r in self.records if r["text"] or r.get("title") or r.get("editor_omitted")]
        if self.book_id == 28107:
            # الموطأ ت الأعظمي: قول مالك أو يحيى فقرة مرقّمة مستقلة، والأساس (1699) يُلحقه بالحديث قبله
            # ← يُضمّ إلى الحديث السابق في الباب نفسه، ويُحفظ رقمه في numbers.merged (تقسيم الأساس، للمقابلة)
            merged = []
            for r in self.records:
                prev = merged[-1] if merged else None
                plain = re.sub(r"[ً-ْٰ]", "", r["text"])
                if r["type"] == "hadith" and re.match(r"\[?(?:كمل|تم|تمت)\s", plain):
                    # خاتمة الكتاب «كَمُلَ كتاب الصلاة والحمد لله…» فقرة مرقّمة عند الأعظمي، ليست حديثًا
                    r["type"] = "other"
                    r["colophon"] = True
                if (r["type"] == "hadith" and prev is not None and prev["type"] == "hadith"
                        and re.match(r"(?:و?قال\s*[:،,]?\s*(?:و?قال\s*:?\s*)?(?:يحيى|مالك)|و?سئل\s+مالك"
                                     r"|قال\s*[:،,]?\s*و?سئل)", plain)):
                    prev["text"] += "\n" + r["text"]
                    prev["numbers"].setdefault("merged", []).extend(r["numbers"]["printed"])
                    if r.get("notes"):
                        prev.setdefault("notes", []).extend(r["notes"])
                    self.stats["azami_merged"] = self.stats.get("azami_merged", 0) + 1
                    continue
                merged.append(r)
            self.records = merged
        # عنوان المستوى الأول: كتاب إن تلته أحاديث قبل العنوان التالي أو جاء بعد أول حديث، وإلا فمقدمة
        tops = [i for i, r in enumerate(self.records) if r["type"] == "top"]
        seen = False
        for k, i in enumerate(tops):
            end = tops[k + 1] if k + 1 < len(tops) else len(self.records)
            has = any(r["type"] == "hadith" for r in self.records[i:end])
            self.records[i]["type"] = "kitab" if (has or seen) else "front"
            if has or seen:
                for r in self.records[i:end]:  # ما قبل أول حديث في الكتاب ليس مقدمة
                    if r["type"] == "front":
                        r["type"] = "other"
            seen = seen or has
        # أعد ترقيم الكتب والأبواب بالترتيب
        kitab, bab = {"n": 0, "title": None}, {"n": 0, "title": None}
        for i, r in enumerate(self.records, 1):
            r["seq"] = i
            if r["type"] == "kitab":
                kitab, bab = {"n": kitab["n"] + 1, "title": r["title"]}, {"n": 0, "title": None}
                r["kitab"] = dict(kitab)
            elif r["type"] == "bab":
                bab = {"n": bab["n"] + 1, "title": r["title"]}
            if r["type"] in ("bab", "hadith", "other"):
                r["kitab"], r["bab"] = dict(kitab), dict(bab)


def attach_fixes(ex, recs):
    """يُثبت كل إصلاح طُبّق في سجله (corrections)، ويحفظ الرقم المطبوع إن غُيّر الرقم."""
    n_fix = sum(len(v) for v in ex.fixes.values())
    if len(ex.fixes_applied) != n_fix:
        raise SystemExit(f"source fixes applied {len(ex.fixes_applied)} of {n_fix}")
    for f in ex.fixes_applied:
        if f.get("title"):
            title = clean(re.sub(r"<[^>]+>", "", f["replace"]))
            cands = [r for r in recs if r["type"] == "bab" and r.get("title") == title]
        else:
            cands = [r for r in recs if r["type"] == "hadith" and f["number"] in r["numbers"].get("printed", [])
                     and r["source"]["entry"] <= f["entry"] and ("kitab" not in f or r["kitab"]["n"] == f["kitab"])]
            cands = [max(cands, key=lambda r: r["source"]["entry"])] if cands else []
        if len(cands) != 1:
            raise SystemExit(f"source fix target not found: {f['collection']} {f['item']} {f.get('number')}")
        r = cands[0]
        r.setdefault("corrections", []).append({
            "item": f["item"], "from": clean(f["find"]), "to": clean(f["replace"]),
            "source": "decisions/source-fixes.json", "witnesses": f["witnesses"], "decision": f["decision"]})
        if f.get("printed_as"):
            r["numbers"]["printed_as"] = [f["printed_as"]]


def main(collection: str, book_id: str, witness: bool = False) -> int:
    src = ROOT / "base" / "shamela" / book_id / f"{book_id}.json"
    out_dir = ROOT / "text" / collection
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = json.loads(src.read_text(encoding="utf-8"))
    pages = raw["pages"]
    # الفهرس في ملف تراث تحت مفاتيح مرمّزة: قائمة {title, level, page} و page = رقم المدخل + 1
    toc = raw.get("ٙ", {}).get("ٛ", [])
    if not toc and isinstance(raw.get("٘", {}).get("ٚ"), list):
        # صيغة أحدث من ملفات تراث (الدارمي 21795): الفهرس تحت «٘» ← «ٚ»؛ لا يقع في الكتب التي فهرسها في «ٙ» ← «ٛ»
        toc = raw["٘"]["ٚ"]
    toc_top = {}
    if collection == "bazzar":
        # مسند البزار 12981: أول عنوان في الفهرس ابتلع نص الصفحة بعد نقاط الخرم («مسند أبي بكر الصديق ﵁. . . . . . . أبي بكر أبو أويس…»)
        # ← العنوان إلى أول النقاط
        toc = [dict(t, title=re.split(r"\s*(?:\.\s*){3,}", t["title"])[0]) for t in toc]
    for t in toc:
        if t.get("level") == 1 and collection != "adabmufrad":  # الأدب المفرد: المستوى الأول أبواب لا كتب
            toc_top.setdefault(t["page"] - 1, []).append(t["title"])
    if collection == "ibnjarud":
        # المنتقى لابن الجارود: الفهرس مستوى واحد هو الأبواب المرقّمة نفسها (لا كتب فوقها) ← لا سجلات «كتاب» منه
        toc_top = {}
    ex = Extractor(collection, book_id, toc_top)
    fixes_path = ROOT / "decisions" / "source-fixes.json"
    if fixes_path.exists():
        for f in json.loads(fixes_path.read_text(encoding="utf-8"))["fixes"]:
            if f["shamela"] == ex.book_id:
                ex.fixes.setdefault(f["entry"], []).append(f)
    for t in toc:
        if t.get("level") == 2:
            m = re.match(r"\s*\(([٠-٩]+)\)", t["title"])
            ex.toc_bab.setdefault(t["page"] - 1, []).append(m.group(1) if m else "")
    if collection in TABARANI:
        ex.toc_levels = [t.get("level") for t in toc]
    if collection == "ahmad":
        tops = [t for t in raw.get("ٙ", {}).get("ٛ", []) if t.get("level") == 1]
        ex.body_start = tops[1]["page"] - 1  # بعد «مقدمات»: أول مسند (مسند العشرة)
    if int(book_id) in ARNAOUT_W:
        # مقدمة التحقيق قبل أول كتاب (فيها قوائم مرقمة لا أحاديث)
        tops = [t for t in toc if t.get("level") == 1 and re.search(r"كتاب|أبواب", t["title"])]
        ex.body_start = tops[0]["page"] - 1
    if ex.book_id == 1424:
        # المستدرك ط الرسالة: مقدمة التحقيق قبل «مقدمة المؤلف» (فيها قوائم مرقمة وصور النسخ) ← front
        ex.body_start = next(t["page"] for t in toc if t.get("level") == 1 and "مقدمة المؤلف" in t["title"]) - 1
    if book_id == "735":
        # البخاري ت البغا (شاهد): المتن يبدأ عند أول كتاب مرقَّم «١ - بدء الوحي»
        ex.body_start = min(t["page"] - 1 for t in toc if t.get("level") == 1 and re.match(r"\s*١\s*-", t["title"]))
    if ex.book_id == 28107:
        # الموطأ ت الأعظمي: الكتاب من «وقوت الصلاة» إلى ما قبل «ترجمة رجال الموطأ» (فهرس المستوى الأول)
        tops = [t for t in toc if t.get("level") == 1]
        ex.body_start = next(t["page"] for t in tops if "وقوت" in t["title"]) - 2  # «٢ - <span>وُقُوت الصَّلَاةِ» قبله
        ex.body_end = next(t["page"] for t in tops if "ترجمة رجال" in t["title"]) - 1
    if ex.book_id == 333:
        # مصنف ابن أبي شيبة ت الشثري: المتن يبدأ عند أول كتاب بعد «مقدمة التحقيق» في فهرس المستوى الأول
        ex.body_start = next(t["page"] for t in toc if t.get("level") == 1 and "كتاب" in t["title"]) - 1
    if ex.book_id == 84:
        # مصنف عبد الرزاق ط التأصيل: المتن من «١ - كتاب الطهارة» إلى ما قبل «ثبت المصادر والمراجع»
        bare = lambda s: re.sub(r"[ً-ْٰ]", "", s)
        ex.body_start = next(i for i, p in enumerate(pages)
                             if re.search(r'data-type="title"[^>]*>\s*١\s*-\s*كتاب الطهارة', bare(p["text"])))
        ex.body_end = next(i for i, p in enumerate(pages) if re.search(r'data-type="title"[^>]*>\s*ثبت المصادر', bare(p["text"])))
    if ex.book_id == 36114:
        # الدارمي ت الزهراني: أول المسند «١ - باب* ما كان عليه الناس…»؛ ما قبله مقدمة التحقيق
        ex.body_start = next(i for i, p in enumerate(pages) if re.search(r"(^|\n)١ - باب", p["text"]))
    if ex.book_id == 148486:
        # البيهقي ت التركي: المتن من «مقدمة المصنف» إلى ما قبل «فهرس مراجع التحقيق» (فهرس المستوى الأول)
        tops = [t for t in toc if t.get("level") == 1]
        ex.body_start = next(t["page"] for t in tops if "مقدمة المصنف" in t["title"]) - 1
        ex.body_end = next(t["page"] for t in tops if "فهرس مراجع" in t["title"]) - 1
    if ex.book_id == 181:
        # مسند أبي يعلى ت السناري (شاهد): مقدمة التحقيق قبل «مسند أبي بكر الصديق» في فهرس المستوى الأول ← front
        ex.body_start = next(t["page"] for t in toc if t.get("level") == 1 and "مسند أبي بكر" in t["title"]) - 1
    if collection == "bazzar":
        ex.body_start = 1  # المدخل ٠ بطاقة الكتاب
    if collection == "bazzar" or ex.book_id == 181:
        ex.pre_fix =seq_misprints(pages, ex.body_start, lambda p: ex.book_id == 181 and ex.volume_front(p["page"], p["text"]))
    if ex.book_id in (121382, 537):
        # شاهدا ابن خزيمة ط3 وابن حبان 537: المتن من أول كتاب/قسم في فهرس المستوى الأول
        ex.body_start = next(t["page"] - 1 for t in toc if t.get("level") == 1 and re.match(r"\s*(كتاب|القسم)", t["title"]))
    for idx, p in enumerate(pages):
        ex.entry(idx, p)
    ex.finish()
    recs = ex.records
    attach_fixes(ex, recs)

    if ex.profile == "muslim":
        # التغطية بأرقام عبد الباقي (تتكرر لكل إسناد فلا يُعدّ تكرارها خطأ)
        main_nums = sorted({int(x) for r in recs if r["type"] == "hadith" and "abd_al_baqi" in r["numbers"]
                            for x in r["numbers"]["abd_al_baqi"].split("/")})
    else:
        main_nums = [n for r in recs if r["type"] == "hadith" and "sub" not in r["numbers"] for n in r["numbers"]["printed"]]
    dup = sorted(n for n, c in Counter(main_nums).items() if c > 1)
    have = set(main_nums) | ({n for r in recs if r["type"] == "hadith" for n in r["numbers"]["printed"]}
                             if ex.profile != "muslim" else set())
    top = max(main_nums) if main_nums else 0
    missing = [n for n in range(1, top + 1) if n not in have]
    if collection == "malik":
        # الموطأ: الترقيم في كل كتاب على حدة ← التكرار والنقص يُعدّان «كتاب:رقم»
        byk = {}
        for r in recs:
            if r["type"] == "hadith":
                for n in r["numbers"]["printed"]:
                    byk.setdefault(r["kitab"]["n"], []).append(n)
        dup = [f"{k}:{n}" for k, v in byk.items() for n, c in sorted(Counter(v).items()) if c > 1]
        missing = [f"{k}:{n}" for k, v in byk.items() for n in range(1, max(v) + 1) if n not in v]
    if collection in ("tabaranikabir", "bazzar"):
        # (ومسند البزار: الأجزاء ١–١٧ سلسلة (المفتاح ٠) والجزء ١٨ سلسلة مستقلة «18:الرقم»)
        # المعجم الكبير: سلسلة ترقيم للأجزاء ١–١٢ (المفتاح ٠) ولكل من الأجزاء ١٣ و١٧ فما بعده ← «الجزء:الرقم»
        bys = {}
        for r in recs:
            if r["type"] == "hadith" and "sub" not in r["numbers"]:
                for n in r["numbers"]["printed"]:
                    bys.setdefault(r["numbers"].get("series", 0), []).append(n)
            if r["type"] == "bab" and r.get("heading_number"):  # رقم مطبوع على عنوان الصحابي
                h = r["heading_number"]
                bys.setdefault(h.get("series", 0), []).append(h["printed"])
        dup = [f"{k}:{n}" for k, v in bys.items() for n, c in sorted(Counter(v).items()) if c > 1]
        missing = [f"{k}:{n}" for k, v in bys.items() for n in range(1, max(v) + 1) if n not in v]
        top = {k: max(v) for k, v in bys.items()}
    # --witness: طبعة ثانية للكتاب نفسه ← witness-<id>.jsonl بجوار الأساس، ولا يُمسّ ملف الأساس
    stem = f"witness-{book_id}" if witness else collection
    out = out_dir / f"{stem}.jsonl"
    with out.open("w", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    st = {"source": src.relative_to(ROOT).as_posix(), "records": len(recs),
          "by_type": dict(Counter(r["type"] for r in recs)),
          "hadith_main_numbers": len(main_nums), "hadith_sub_numbered": sum(1 for r in recs if r["type"] == "hadith" and "sub" in r["numbers"]),
          "multi_number_records": sum(1 for r in recs if r["type"] == "hadith" and len(r["numbers"]["printed"]) > 1),
          "from_margin": sum(1 for r in recs if r.get("from_margin")),
          "with_notes": sum(1 for r in recs if r.get("notes")),
          "empty_hadith_text": [r["numbers"]["printed"] for r in recs if r["type"] == "hadith" and not r["text"]],
          "max_number": top, "duplicate_numbers": dup, "missing_numbers": missing,
          "missing_count": len(missing),
          "kitab_titles_from_toc": sum(1 for r in recs if r.get("title_from") == "shamela_toc")}
    if ex.book_id in (148486, 7861):
        # البيهقي: فحوص ذاتية (ربط الحواشي، الأرقام المكررة المحذوفة، بقايا علامات أو أرقام في النص)
        hs = [r for r in recs if r["type"] == "hadith"]
        st["self_checks"] = {
            **{k: ex.stats.get(k, 0) for k in ("notes", "note_unlinked", "note_orphan", "note_continued",
                                                "skipped_entries", "w_repeated_number")},
            "notes_on_non_hadith": sum(1 for r in recs if r.get("notes") and r["type"] != "hadith"),
            "marker_left_in_text": sum(1 for r in recs if re.search("[⁅⁆⁣]", r.get("text", "") + (r.get("title") or ""))),
            "line_starting_with_number": [r["numbers"]["printed"] for r in hs
                                          if re.search(r"(?:^|\n)[٠-٩]+\s*-\s*\S", r["text"])][:50],
            "out_of_order": [(a["numbers"]["printed"][0], b["numbers"]["printed"][0])
                             for a, b in zip(hs, hs[1:]) if "sub" not in b["numbers"] and a["numbers"]["printed"]
                             and b["numbers"]["printed"] and b["numbers"]["printed"][0] < a["numbers"]["printed"][0]][:50],
            "longest_hadith": sorted(((len(r["text"]), r["numbers"]["printed"]) for r in hs), reverse=True)[:5]}
    if missing:
        st["missing_note"] = ("هذه الأرقام غير مكتوبة في ملف الشاملة نفسه؛ نصها مدموج في الحديث المجاور "
                              "(لم يُعدَّل شيء). تُراجع عند المقابلة بالمصدر المفتوح.")
    (out_dir / (f"{stem}-stats.json" if witness else "extract-stats.json")).write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(st, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], "--witness" in sys.argv[3:]))
