PY ?= python

.PHONY: test release pilot fetch-a check-a inventory shamela-core shamela-sunnah bukhari muslim abudawud tirmidhi nasai ibnmajah malik darimi ahmad additions tabarani tayalisi humaydi ibnjarud adabmufrad tahawi nasaikubra ibnabishaybah hakim daraqutni ibnkhuzaymah ibnhibban abdurrazzaq bayhaqi abuyala bazzar

# أبو داود: ت محيي الدين عبد الحميد (1726)، ومعه حكم الألباني في حقل grades
abudawud:
	$(PY) -I scripts/fetch_a.py abudawud
	$(PY) -I scripts/extract_shamela.py abudawud 1726
	$(PY) -I scripts/compare_ab.py abudawud
	$(PY) -I scripts/apply_decisions.py abudawud

# الترمذي: ت بشار عواد (7895)؛ شاكر 1435 شاهد ثانٍ لاحقًا
tirmidhi:
	$(PY) -I scripts/fetch_a.py tirmidhi
	$(PY) -I scripts/extract_shamela.py tirmidhi 7895
	$(PY) -I scripts/compare_ab.py tirmidhi

# النسائي (المجتبى): ط المصرية (829)؛ ط الرسالة 1339 شاهد ثانٍ محتمل
nasai:
	$(PY) -I scripts/fetch_a.py nasai
	$(PY) -I scripts/extract_shamela.py nasai 829
	$(PY) -I scripts/compare_ab.py nasai

# ابن ماجه: ت عبد الباقي (1198)، ومعه حكم الألباني وتعليق عبد الباقي وشرحه
ibnmajah:
	$(PY) -I scripts/fetch_a.py ibnmajah
	$(PY) -I scripts/extract_shamela.py ibnmajah 1198
	$(PY) -I scripts/compare_ab.py ibnmajah

# الموطأ: رواية يحيى ت عبد الباقي (1699)؛ الترقيم في كل كتاب على حدة، فالمقابلة بالنص (NO_KEY)
malik:
	$(PY) -I scripts/fetch_a.py malik
	$(PY) -I scripts/extract_shamela.py malik 1699
	$(PY) -I scripts/compare_ab.py malik

# الدارمي: ت حسين أسد (21795)؛ لا شاهد A، والزهراني 36114 شاهد ثانٍ لاحقًا
darimi:
	$(PY) -I scripts/extract_shamela.py darimi 21795

# مسند أحمد: ط الرسالة (25794)؛ لا شاهد A بعد
ahmad:
	$(PY) -I scripts/extract_shamela.py ahmad 25794

# مسلم: الطبعة التركية في الشاملة (711)
muslim:
	$(PY) -I scripts/fetch_a.py muslim
	$(PY) -I scripts/extract_shamela.py muslim 711
	$(PY) -I scripts/compare_ab.py muslim

# استخراج البخاري من الشاملة ثم مقابلته آليًا بـ fawazahmed0
bukhari:
	$(PY) -I scripts/extract_shamela.py bukhari 1681
	$(PY) -I scripts/compare_ab.py bukhari

# ===== الزيادات: الأساس ثم الشاهد الثاني (إن وُجد) ثم المقابلة =====
additions: tabarani tayalisi humaydi ibnjarud adabmufrad tahawi nasaikubra ibnabishaybah hakim daraqutni ibnkhuzaymah ibnhibban abdurrazzaq bayhaqi abuyala bazzar

tabarani:
	$(PY) -I scripts/extract_shamela.py tabaranikabir 1733
	$(PY) -I scripts/extract_shamela.py tabaraniawsat 28171
	$(PY) -I scripts/extract_shamela.py tabaranisaghir 13068

tayalisi:
	$(PY) -I scripts/extract_shamela.py tayalisi 1456

humaydi:
	$(PY) -I scripts/extract_shamela.py humaydi 8493

# الشاهد 13071 نسخة من الأساس نفسه، فطابوره صفر
ibnjarud:
	$(PY) -I scripts/extract_shamela.py ibnjarud 627
	$(PY) -I scripts/extract_shamela.py ibnjarud 13071 --witness
	$(PY) -I scripts/compare_witness.py ibnjarud 13071 --whole

adabmufrad:
	$(PY) -I scripts/extract_shamela.py adabmufrad 12991
	$(PY) -I scripts/extract_shamela.py adabmufrad 9647 --witness
	$(PY) -I scripts/compare_witness.py adabmufrad 9647 --whole

tahawi:
	$(PY) -I scripts/extract_shamela.py tahawi 21108
	$(PY) -I scripts/extract_shamela.py tahawi 1547 --witness
	$(PY) -I scripts/compare_witness.py tahawi 1547 --whole --no-key

nasaikubra:
	$(PY) -I scripts/extract_shamela.py nasaikubra 8361

ibnabishaybah:
	$(PY) -I scripts/extract_shamela.py ibnabishaybah 333
	$(PY) -I scripts/extract_shamela.py ibnabishaybah 9944 --witness
	$(PY) -I scripts/compare_witness.py ibnabishaybah 9944 --whole --no-key --text-key

# تلخيص الذهبي في الشاهد 2266 وحده
hakim:
	$(PY) -I scripts/extract_shamela.py hakim 1424
	$(PY) -I scripts/extract_shamela.py hakim 2266 --witness
	$(PY) -I scripts/compare_witness.py hakim 2266 --whole

daraqutni:
	$(PY) -I scripts/extract_shamela.py daraqutni 9771

ibnkhuzaymah:
	$(PY) -I scripts/extract_shamela.py ibnkhuzaymah 1446
	$(PY) -I scripts/extract_shamela.py ibnkhuzaymah 121382 --witness
	$(PY) -I scripts/compare_witness.py ibnkhuzaymah 121382 --whole

ibnhibban:
	$(PY) -I scripts/extract_shamela.py ibnhibban 1729
	$(PY) -I scripts/extract_shamela.py ibnhibban 537 --witness
	$(PY) -I scripts/compare_witness.py ibnhibban 537 --whole --key-from concordance.ihsan --order-by-key

abdurrazzaq:
	$(PY) -I scripts/extract_shamela.py abdurrazzaq 13174
	$(PY) -I scripts/extract_shamela.py abdurrazzaq 84 --witness
	$(PY) -I scripts/compare_witness.py abdurrazzaq 84 --whole --no-key --kitab-by-title --shingle-key

# السنن الكبير: ت التركي (148486)، والشاهد ط العلمية (7861) بترقيم مختلف
bayhaqi:
	$(PY) -I scripts/extract_shamela.py bayhaqi 148486
	$(PY) -I scripts/extract_shamela.py bayhaqi 7861 --witness
	$(PY) -I scripts/compare_witness.py bayhaqi 7861 --whole --no-key

# مسند أبي يعلى: ت حسين أسد (12520)، والشاهد ت السناري (181)؛ حدود المسانيد مختلفة فالمقابلة --whole
abuyala:
	$(PY) -I scripts/extract_shamela.py abuyala 12520
	$(PY) -I scripts/extract_shamela.py abuyala 181 --witness
	$(PY) -I scripts/compare_witness.py abuyala 181 --whole

# مسند البزار (12981)؛ لا شاهد ثانٍ
bazzar:
	$(PY) -I scripts/extract_shamela.py bazzar 12981

# يُستكمل مع تقدّم خطوات التجربة (3 فما بعدها تنتظر مصوّرة الجزء الأول)
pilot: fetch-a check-a
	$(PY) scripts/finalize_readings.py
	$(PY) scripts/align.py
	$(PY) scripts/build_review.py

fetch-a:
	$(PY) scripts/fetch_a.py

check-a:
	$(PY) scripts/check_a.py

inventory:
	$(PY) scripts/epub_inventory.py

shamela-core:
	$(PY) scripts/fetch_turath.py core

shamela-sunnah:
	$(PY) scripts/fetch_turath.py cat 6

# فحص الانحدار: يعيد استخراج كل الكتب ويطابق بصمات المخرجات (tests/expected.sha256)
test:
	bash tests/regression.sh

# إصدار البيانات العام (build/release/): النص بلا حركات افتراضيًّا؛ نسخة مشكولة بـ --keep-vowels
release:
	$(PY) -I scripts/export_release.py
