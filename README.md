<div align="center">

# open-hadith-data

**Verified Arabic hadith texts — the Nine Books and 18 further collections — extracted to structured JSON and cross-checked against independent editions.**

<p dir="rtl">نصوص كتب الحديث بالعربية في صيغة JSON منظَّمة، كلٌّ منها مقابَل بطبعة أخرى مستقلة، وكل تصحيح موثَّق بشهوده.</p>

[![Code: MIT](https://img.shields.io/badge/code-MIT-blue.svg)](LICENSE)
[![Data: CC BY 4.0](https://img.shields.io/badge/data-CC%20BY%204.0-lightgrey.svg)](LICENSE-DATA.md)
![Collections](https://img.shields.io/badge/collections-27-green.svg)
![Hadith](https://img.shields.io/badge/hadith-251%2C348-green.svg)
![Documented fixes](https://img.shields.io/badge/source%20fixes-66-orange.svg)

[الكتب](#الكتب--collections) · [بنية السجل](#بنية-السجل--record-format) · [البناء](#البناء--build) · [المساهمة](CONTRIBUTING.md) · [الرخصة](#الرخصة--license)

</div>

---

## ما الذي يميّزه / What makes it different

- **مقابلة بالشواهد / Witness collation:** كل كتاب يُستخرج من طبعة أساس، ثم يُقابَل حرفًا بحرف بطبعة ثانية مستقلة. وللكتب الستة شاهد ثالث هو [fawazahmed0/hadith-api](https://github.com/fawazahmed0/hadith-api). كل فرق يدخل طابور مراجعة، ولا يُصحَّح شيء آليًّا.
- **تصحيحات موثَّقة / Documented corrections:** عيوب المصدر الثابتة تُصلَح من ملف واحد هو [`decisions/source-fixes.json`](decisions/source-fixes.json). لكل إصلاح النص قبله وبعده، والشهود، والقرار. والسجل المصحَّح يحمل حقل `corrections`.
- **قابل لإعادة البناء / Reproducible:** المخرجات كلها تُولَّد بالسكربتات (`make <book>`)، وفحص الانحدار يطابق بصمات 57 ملفًا من المخرجات (`make test`).
- **الفصل بين النص وما حوله / Text kept separate:** حواشي المحققين في `notes`، وأحكامهم في `grades.<المحقق>`، ولا يدخل شيء منها في `text`.

## الكتب / Collections

| المفتاح | الكتاب | الأحاديث |
|---|---|---:|
| `bukhari` | صحيح البخاري | 7,481 |
| `muslim` | صحيح مسلم | 7,733 |
| `abudawud` | سنن أبي داود | 5,274 |
| `tirmidhi` | سنن الترمذي | 4,344 |
| `nasai` | سنن النسائي (المجتبى) | 5,765 |
| `ibnmajah` | سنن ابن ماجه | 4,341 |
| `malik` | موطأ مالك | 1,903 |
| `darimi` | مسند الدارمي | 3,545 |
| `ahmad` | مسند أحمد | 27,768 |
| `tabaranikabir` / `tabaraniawsat` / `tabaranisaghir` | معاجم الطبراني | 21,922 / 9,477 / 1,192 |
| `tayalisi` | مسند الطيالسي | 2,891 |
| `humaydi` | مسند الحميدي | 1,332 |
| `ibnjarud` | المنتقى لابن الجارود | 1,199 |
| `adabmufrad` | الأدب المفرد | 1,324 |
| `tahawi` | شرح معاني الآثار | 7,434 |
| `nasaikubra` | السنن الكبرى للنسائي | 11,972 |
| `ibnabishaybah` | مصنف ابن أبي شيبة | 40,757 |
| `hakim` | المستدرك على الصحيحين | 9,149 |
| `daraqutni` | سنن الدارقطني | 4,825 |
| `ibnkhuzaymah` | صحيح ابن خزيمة | 3,066 |
| `ibnhibban` | صحيح ابن حبان | 7,399 |
| `abdurrazzaq` | مصنف عبد الرزاق | 19,400 |
| `bayhaqi` | السنن الكبرى للبيهقي | 21,846 |
| `abuyala` | مسند أبي يعلى | 7,565 |
| `bazzar` | مسند البزار | 10,444 |

الطبعة المعتمدة لكل كتاب وشاهده في [`Docs/hadith-pilot-spec.md`](Docs/hadith-pilot-spec.md) (القسم 13.3)، وتقرير كل كتاب في [`reports/`](reports/).

## التنزيل / Download

حمّل آخر إصدار من صفحة [Releases](../../releases). فيه:

- `jsonl/<book>.jsonl.gz`: سجل لكل حديث، ومعه السند والمتن مفصولين، وأرقامه في الترقيمات الأخرى.
- `open-hadith-data.sqlite`: قاعدة جاهزة للتطبيقات، فيها بحث نصي عربي (FTS5).
- `csv/<book>.csv.gz`: للتحليل في الجداول.

دليل الحقول والأمثلة في [`Docs/DATA.md`](Docs/DATA.md). نص الإصدار بلا تشكيل، وبلا حواشي المحققين ولا أحكامهم.

## بنية السجل / Record format

سطر JSON لكل سجل (`text/<key>/<key>.jsonl`):

```json
{
  "seq": 9,
  "type": "hadith",
  "collection": "bayhaqi",
  "source": {"shamela": 148486, "entry": 184},
  "numbers": {"printed": [1]},
  "kitab": {"n": 1, "title": "كتاب الطهارة"},
  "bab": {"n": 1, "title": "باب التطهر بماء البحر"},
  "loc": [{"juz": 1, "page": 9}],
  "text": "…",
  "notes": ["…"],
  "grades": {"…": "…"},
  "corrections": []
}
```

قيم `type`: `hadith` و`kitab` و`bab` و`other`. وحقول إضافية بحسب الكتاب، مثل `numbers.printed_as` للرقم المطبوع خطأً، و`sharh` و`meter` و`colophon`.

## البناء / Build

```bash
python scripts/fetch_turath.py core     # تنزيل طبعات الكتب
make bukhari                            # استخراج كتاب ومقابلته
make additions                          # كتب الزيادات
make test                               # فحص الانحدار
```

يحتاج Python 3 و`make` وbash. ملفات المصدر الخام لا تُحفظ في المستودع؛ تُنزَّل بالسكربتات، وبصماتها في [`PROVENANCE.md`](PROVENANCE.md).

## المصادر والحقوق / Sources & rights

- النصوص مأخوذة من [المكتبة الشاملة](https://shamela.ws) عبر [تراث](https://app.turath.io). المصادر كلها مسجّلة في [`PROVENANCE.md`](PROVENANCE.md).
- **متون الأحاديث** ملك عام.
- **حواشي المحققين وأحكامهم** (`notes`، `grades`) **وتشكيل الطبعات وترقيمها** من عمل أصحابها، ولهم حقوقهم. لذلك لا يُنشر ملف بيانات قبل فصل نسخة نشر خالية منها.

## الرخصة / License

- **الكود** (`scripts/`، `tests/`، `Makefile`): رخصة [MIT](LICENSE).
- **البيانات والقرارات والتوثيق:** رخصة [CC BY 4.0](LICENSE-DATA.md). استعملها كما شئت بشرط ذكر المشروع.
- **متون الأحاديث:** ملك عام. **وعمل المحققين المعاصرين:** حقٌّ لأصحابه. التفصيل في [`LICENSE-DATA.md`](LICENSE-DATA.md).

للاستشهاد بالمشروع انظر [`CITATION.cff`](CITATION.cff). وللإبلاغ عن خطأ في نص استعمل [قالب البلاغ](../../issues/new/choose).


## ☕ ادعم المشروع / Support the project

إذا أفادك هذا المشروع، يمكنك دعم تطويره عبر PayPal.
If this project helps you, you can support its development via PayPal.

[![PayPal](https://img.shields.io/badge/PayPal-Support-00457C?logo=paypal&logoColor=white)](https://paypal.me/SamtSoftware)

👉 https://paypal.me/SamtSoftware
