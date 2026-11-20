# المساهمة / Contributing

شكرًا لاهتمامك. أنفع ما يقدَّم لهذا المشروع **الإبلاغ عن خطأ في نص**، مع ذكر الدليل.

## الإبلاغ عن خطأ في نص / Reporting a text error

افتح بلاغًا باستعمال قالب **«خطأ في نص حديث»**، واذكر فيه:

1. **الموضع:** الكتاب ورقم الحديث، مثل `bukhari` 1234.
2. **النص كما هو عندنا، والصواب** في رأيك.
3. **الدليل:** طبعة مطبوعة (اسمها والجزء والصفحة)، أو مخطوط، أو طبعة رقمية أخرى. **لا يُقبل تصحيح بلا شاهد.**

لا يُغيَّر نص في الموضع نفسه أبدًا. كل تصحيح يُضاف سجلًّا في `decisions/source-fixes.json`، فيه النص قبله وبعده والشهود والقرار، ويُطبَّق عند الاستخراج.

## تعديل الكود / Changing code

- كل قاعدة استخراج جديدة تُحرَس بمعرّف الكتاب (`self.book_id`) أو مفتاحه (`self.collection`)، حتى لا تمسّ كتابًا آخر.
- شغّل `make test` قبل الطلب، ويجب أن تبقى البصمات كلها مطابقة.
- إن كان تغيير المخرجات مقصودًا، فشغّل `bash tests/regression.sh --update`، واشرح في الطلب ما الذي تغيّر ولماذا.
- استعمل `python -I` مع الملفات المنزَّلة.

## English summary

The most valuable contribution is a **text error report with evidence**: use the *Text error* issue template. Give the location, the current and proposed readings, and a citable witness (printed edition with volume and page, or another edition).

Corrections never edit text in place. Each one becomes an entry in `decisions/source-fixes.json`.

For code changes:
- Guard every new rule by book id or collection key.
- Make sure `make test` passes.
- If an output change is intended, regenerate the fingerprints with `--update` and explain why in the PR.
