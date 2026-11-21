# open-hadith-data — دليل البيانات / Data guide

الإصدار 0.1.0 · 27 كتابًا · 251,348 حديثًا
Release 0.1.0 · 27 collections · 251,348 hadith records

يُبنى الإصدار بالأمر `make release` (أو `python -I scripts/export_release.py`) في `build/release/`.
The release is built with `make release` into `build/release/`.

---

## 1. الملفات / Files

| الملف / File | المحتوى / Content |
|---|---|
| `jsonl/<collection>.jsonl.gz` | سجل JSON لكل حديث، كامل الحقول / one JSON record per hadith, all fields |
| `csv/<collection>.csv.gz` | الأعمدة البسيطة فقط / flat columns only |
| `open-hadith-data.sqlite` | كل الكتب في قاعدة واحدة مع بحث FTS5 / everything in one SQLite DB with FTS5 search |
| `manifest.json` | الإصدار، والتاريخ، والأعداد، والطبعات، وsha256 كل ملف وحجمه / version, date, counts, editions, sha256 + size of every file |
| `README_DATA.md` | هذا الملف / this file |
| `LICENSE-DATA.md` | الرخصة / license |
| `open-hadith-data-0.1.0.zip` | الحزمة كاملة / the whole bundle |

الترميز UTF-8 في كل الملفات. ترتيب السجلات ترتيب الطبعة.
All files are UTF-8. Records follow the order of the printed edition.

---

## 2. الحقول / Fields

| الحقل / Field | النوع / Type | الشرح | Description |
|---|---|---|---|
| `id` | string | المعرّف الثابت (القسم 3) | stable id (section 3) |
| `collection` | string | مفتاح الكتاب، مثل `bukhari` | collection key |
| `number` | int \| null | أول رقم مطبوع للحديث في الطبعة | first printed number, or null |
| `numbers` | object | كل ترقيمات الطبعة: `printed` (قائمة)، و`abd_al_baqi` (ترقيم عبد الباقي)، و`series` (التسلسل العام)، و`sub` (رقم فرعي)، و`mulhaq` (الملحق)، و`printed_as` (الرقم كما طُبع إن خالف)، و`unnumbered`، و`misprint`، و`repeated_in_source` | all numberings in the edition: printed list, Abd al-Baqi numbering, running series, sub-number, appendix, number as misprinted, flags |
| `kitab` | {n, title} | الكتاب الذي فيه الحديث (n ترتيبه) | the book (chapter group) |
| `bab` | {n, title} | الباب (n=0 وtitle=null إن لم يكن باب) | the chapter; n=0 / null if none |
| `loc` | [{juz, page}] | الجزء والصفحة في الطبعة (أكثر من عنصر إن امتد الحديث على صفحات) | volume and page(s) in the edition |
| `edition` | {shamela_id, name} | الطبعة المعتمدة: معرّفها في الشاملة واسمها | base edition: Shamela id and name |
| `text` | string | نص الحديث كاملًا: سنده ومتنه | full text, isnad + matn |
| `text_plain` | string | النص مطبَّعًا للبحث (القسم 4) | normalised text for search (section 4) |
| `isnad` | string \| null | السند | chain of transmission |
| `matn` | string \| null | المتن | body text |
| `matn_confidence` | string \| null | ثقة الفصل بين السند والمتن (القسم 5) | confidence of the isnad/matn split |
| `matn_method` | string \| null | الطريقة التي فُصل بها | how the split was made |
| `narrators` | [{id, name}] | الرواة بترتيبهم في السند، في الكتب التي فيها ذلك فقط. المعرّف من الشاملة | narrators in chain order (only where the source tags them); ids from Shamela |
| `refs` | object | رقم الحديث في ترقيمات أخرى: `{"نظام": قيمة}` | numbers of this hadith in other numbering systems |
| `verse_refs` | [string] | الآيات المحال إليها، مثل `"التوبة: ١٠٨"` | Quran verses referenced |
| `taqasim` | [string] | ابن حبان وحده: موضعه في «التقاسيم والأنواع» | Ibn Hibban only: position in al-Taqasim |
| `abdullah_mark` | string | أحمد وحده: من زيادات ابنه عبد الله | Ahmad only: addition by his son Abdullah |
| `duplicate_fragment` | [string] | ابن حبان وحده: قطعة مكررة في المصدر | Ibn Hibban only: duplicated fragment |
| `corrected` | bool | هل صُحّح النص عن ملف الشاملة | whether the text was corrected |
| `corrections` | [{item, witnesses}] | البند المصحَّح والشهود عليه | the correction and its witnesses |

الحقول الثلاثة `taqasim` و`abdullah_mark` و`duplicate_fragment` لا تظهر إلا حيث وُجدت، وكذلك `narrators`.
`taqasim`, `abdullah_mark`, `duplicate_fragment` and `narrators` appear only where present.

المخطط الكامل: `Docs/record.schema.json` (JSON Schema 2020-12).
Full schema: `Docs/record.schema.json`.

---

## 3. المعرّفات وثباتها / Identifiers

- الصيغة `<collection>:<n>`، وn أول رقم مطبوع للحديث: `bukhari:1`.
- إن تكرر الرقم نفسه في الكتاب: الأول `muslim:5`، والتالي `muslim:5.2`، ثم `.3`.
- الحديث بلا رقم: `<collection>:u<seq>`، وseq ترتيبه في ملف الاستخراج.
- المعرّف ثابت ما دامت الطبعة ثابتة واستخراجها ثابتًا، ويحرسه فحص الانحدار (`make test`). لن يتغير معرّف في الإصدارات 0.x إلا بتغيير الطبعة، ويُذكر ذلك في سجل التغييرات.

- Format `<collection>:<n>` where n is the first printed number.
- Repeated numbers get `.2`, `.3`… in file order; unnumbered records get `u<seq>`.
- Ids are stable as long as the edition and the extraction are unchanged (guarded by the regression test). An id changes only if the base edition changes, and that will be announced.

---

## 4. التطبيع والتشكيل / Normalisation and vocalisation

**التشكيل:** نص الإصدار الافتراضي **بلا حركات**، لأن التشكيل من عمل محققي الطبعات. يسري ذلك على `text` و`isnad` و`matn` والعناوين وأسماء الرواة. يُقطع السند والمتن من النص المشكول، ثم تُزال الحركات. ومن أراد النسخة المشكولة بناها بنفسه بالأمر `python -I scripts/export_release.py --keep-vowels`، فتخرج في `build/release-vowelled/`، وحقوق تشكيلها لأصحاب الطبعات.

**Vocalisation:** the default release is **unvocalised**, because the harakat are the editors' work. This applies to `text`, `isnad`, `matn`, titles and narrator names. The isnad/matn split is made on the vocalised text, then the harakat are removed. A vocalised build can be made locally with `--keep-vowels`, and its vocalisation remains the editors' property.

**`text_plain`:** حذف الحركات والتطويل، و`أ إ آ ٱ` ← `ا`، و`ى` ← `ي`، و`ة` ← `ه`، وتوحيد المسافات. طبِّع استعلامك بالقواعد نفسها قبل البحث.
**`text_plain`:** no harakat or tatweel; `أ إ آ ٱ → ا`, `ى → ي`, `ة → ه`; whitespace collapsed. Normalise queries the same way.

---

## 5. ثقة المتن / Matn confidence

يفصل `scripts/matn.py` كل حديث إلى سند ومتن. السند والمتن مقطعان حرفيان من النص المشكول، ثم تُزال الحركات (القسم 4). الحقل `matn_method`:

- **`source`:** المتن معلَّم في ملف المصدر نفسه، ووُجد في النص حرفيًّا. ثقته `high` دائمًا. (في البخاري ومسلم والترمذي والنسائي والطيالسي وابن الجارود.)
- **`heuristic`:** فصل آلي بقواعد صريحة على صيغ الأداء («حدثنا»، «أخبرنا»، «عن»…) وعلامات القول، وعلامة التنصيص «.

ومستويات `matn_confidence` في الطريقة الآلية:

- **`high`:** ذكر النبي ﷺ بعد آخر صيغة أداء («قال رسول الله ﷺ»…)، أو اتفاق القرينة اللفظية وعلامة « على الموضع نفسه.
- **`medium`:** قرينة واحدة متوسطة: فعل قول بعد السند، أو «أن النبي ﷺ»، أو نقطتا القول، أو علامة « وحدها.
- **`low`:** قرينة ضعيفة («أنّ» وحدها، أو إحالة مثل «مثله/نحوه»، أو متن من ثلاث كلمات فأقل)، أو تعارض القرينتين. استعمله بحذر.
- **`null`:** لم يُفصل الحديث (لا قرينة، أو أثر بلا سند)، فـ`isnad` و`matn` فارغان، والنص كله في `text`.

توزيع القيم في كل إصدار مسجَّل في `manifest.json` تحت `matn`. و`text` هو المرجع دائمًا، والفصل مساعد. ومقاييس دقة الطريقة الآلية على المعيار الذهبي: `python -I scripts/matn.py --eval`.

`matn_method` is `source` when the source file marks the matn itself (always `high`), or `heuristic` for rule-based splitting on transmission formulas, speech markers and the « quotation mark. Heuristic confidence: **high** = the Prophet ﷺ is named right after the last transmission formula, or lexical and quotation cues agree; **medium** = one moderate cue (speech verb, "anna al-nabi", colon, or « alone); **low** = weak cue, a back-reference ("mithlahu"), a matn of ≤3 words, or conflicting cues; **null** = no split. The distribution is recorded in `manifest.json` → `matn`. `text` is always authoritative.

---

## 6. ما استُبعد ولماذا / What is excluded and why

| الحقل في المصدر | سبب الاستبعاد | Reason |
|---|---|---|
| `notes` | حواشي المحققين | editors' footnotes |
| `grades` | أحكام المحققين على الأحاديث (الألباني، والأرنؤوط، وغيرهما) | modern editors' gradings |
| `sharh` | شرح المحقق | editor's commentary |
| `meter` | بحور الشعر من إضافة المحقق | editor's annotation of poetic meter |
| `colophon` | خاتمة الطبعة، خارج نص الحديث | edition colophon, not hadith text |
| `text_source` | نص ملف الشاملة قبل التصحيح (النص المصحَّح في `text`) | pre-correction source text |
| `editor_omitted` | علامة لما حذفه المحقق، خارج النص | editor-omission flag |
| `from_margin` | ما أُخذ من الهامش | material taken from the margin |

يُبنى السجل بقائمة بيضاء من الحقول، ثم يفحص السكربت كل سجل آليًّا، فيفشل البناء إن وُجد فيه حقل من هذه. وكذلك يُستبعد التشكيل افتراضيًّا (القسم 4). ونصوص الأحاديث نفسها تراث ملك عام، وبنية السجلات والتصحيحات بالرخصة CC BY 4.0 (انظر `LICENSE-DATA.md`).

Records are built from a whitelist and every record is checked automatically; the build fails if any excluded field appears. Hadith texts are public domain; the record structure and corrections are CC BY 4.0 (see `LICENSE-DATA.md`).

---

## 7. SQLite

| الجدول / Table | الأعمدة / Columns |
|---|---|
| `collections` | key, name_ar, edition_id, edition_name, hadith_count, ord |
| `hadiths` | rowid, id, collection, ord, number, numbers (JSON), kitab_n, kitab_title, bab_n, bab_title, juz, page, loc (JSON), edition_id, text, text_plain, isnad, matn, matn_plain, matn_confidence, matn_method, narrators (JSON), refs (JSON), verse_refs (JSON), extra (JSON: taqasim / abdullah_mark / duplicate_fragment), corrected, corrections (JSON) |
| `kutub` | collection, n, title, hadith_count, first_id |
| `abwab` | collection, kitab_n, n, title, hadith_count, first_id |
| `hadith_narrators` | hadith_id, narrator_id, name, position |
| `hadith_refs` | hadith_id, system, value |
| `hadiths_fts` | FTS5 على / over `text_plain`, `matn_plain` (external content = `hadiths`) |
| `meta` | key, value |

---

## 8. أمثلة / Examples

### Python: قراءة jsonl.gz

```python
import gzip, json

with gzip.open("jsonl/bukhari.jsonl.gz", "rt", encoding="utf-8") as f:
    for line in f:
        h = json.loads(line)
        print(h["id"], h["kitab"]["title"], h["text"][:60])
        break
```

### SQL: البحث النصي / full-text search

```sql
-- طبّع الاستعلام كما طُبّع text_plain (بلا همزات على الألف، ى→ي، ة→ه)
SELECT h.id, h.kitab_title, snippet(hadiths_fts, 0, '[', ']', '…', 12) AS hit
FROM hadiths_fts JOIN hadiths h ON h.rowid = hadiths_fts.rowid
WHERE hadiths_fts MATCH 'انما الاعمال بالنيات'
ORDER BY h.rowid;

-- عبارة متصلة / exact phrase, matn only
SELECT h.id FROM hadiths_fts JOIN hadiths h ON h.rowid = hadiths_fts.rowid
WHERE hadiths_fts MATCH 'matn_plain : "الدين النصيحه"';

-- أحاديث راوٍ معيّن / hadiths of a narrator
SELECT hadith_id, position FROM hadith_narrators WHERE narrator_id = 2478;

-- عدد الأحاديث في كل كتاب / counts
SELECT key, name_ar, hadith_count FROM collections ORDER BY ord;
```

### Python + SQLite

```python
import sqlite3
db = sqlite3.connect("open-hadith-data.sqlite")
for (hid,) in db.execute("SELECT h.id FROM hadiths_fts JOIN hadiths h ON h.rowid=hadiths_fts.rowid "
                         "WHERE hadiths_fts MATCH ? LIMIT 5", ("الدين النصيحه",)):
    print(hid)
```

---

## 9. النسبة / Citation

> open-hadith-data by samt-qa — https://github.com/samt-qa/open-hadith-data — CC BY 4.0
