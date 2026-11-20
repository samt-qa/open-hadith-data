#!/usr/bin/env bash
# فحص الانحدار: يعيد الاستخراج والمقابلة لكل الكتب، ثم يطابق بصمات المخرجات بـ tests/expected.sha256.
# أي فرق يعني أن تعديلًا في السكربتات غيّر نصًّا لم يكن مقصودًا.
# الاستعمال: bash tests/regression.sh        (من جذر المشروع؛ يحتاج base/shamela منزَّلة)
#            bash tests/regression.sh --update   (بعد تغيير مقصود: يحدّث البصمات)
set -u
cd "$(dirname "$0")/.."
PY="${PY:-python}"
run() { "$PY" -I "$@" >/dev/null 2>&1 || echo "FAILED: $*"; }

# الكتب التسعة
for c in "bukhari 1681" "muslim 711" "abudawud 1726" "tirmidhi 7895" "nasai 829" "ibnmajah 1198" "malik 1699" "darimi 21795" "ahmad 25794"; do
  set -- $c; run scripts/extract_shamela.py $1 $2
done
run scripts/apply_decisions.py abudawud
for w in "tirmidhi 1435" "nasai 1339" "abudawud 117359" "ibnmajah 98138" "ahmad 98139" "muslim 1727" "bukhari 735" "malik 28107" "darimi 36114"; do
  set -- $w; run scripts/extract_shamela.py $1 $2 --witness
done
for c in bukhari muslim abudawud tirmidhi nasai ibnmajah malik; do
  run scripts/compare_ab.py $c
  [ $c = abudawud ] && run scripts/apply_decisions.py abudawud
done

# الزيادات
for b in "tabaranikabir 1733" "tabaraniawsat 28171" "tabaranisaghir 13068" "tayalisi 1456" "humaydi 8493" "ibnjarud 627" "adabmufrad 12991" "tahawi 21108" "nasaikubra 8361" "ibnabishaybah 333" "hakim 1424" "daraqutni 9771" "ibnkhuzaymah 1446" "ibnhibban 1729" "abdurrazzaq 13174" "bayhaqi 148486" "abuyala 12520" "bazzar 12981"; do
  set -- $b; run scripts/extract_shamela.py $1 $2
done
for w in "adabmufrad 9647" "tahawi 1547" "ibnjarud 13071" "ibnabishaybah 9944" "hakim 2266" "ibnkhuzaymah 121382" "ibnhibban 537" "abdurrazzaq 84" "bayhaqi 7861" "abuyala 181"; do
  set -- $w; run scripts/extract_shamela.py $1 $2 --witness
done
run scripts/compare_witness.py abdurrazzaq 84 --whole --no-key --kitab-by-title --shingle-key
run scripts/compare_witness.py ibnabishaybah 9944 --whole --no-key --text-key
run scripts/compare_witness.py bayhaqi 7861 --whole --no-key
run scripts/compare_witness.py abuyala 181 --whole

if [ "${1:-}" = "--update" ]; then
  cut -c67- tests/expected.sha256 | xargs sha256sum > tests/expected.sha256.new && mv tests/expected.sha256.new tests/expected.sha256
  echo "updated $(wc -l < tests/expected.sha256) fingerprints"
else
  sha256sum --quiet -c tests/expected.sha256 && echo "OK: all $(wc -l < tests/expected.sha256) outputs identical"
fi
