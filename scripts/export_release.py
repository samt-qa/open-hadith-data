"""يبني إصدار البيانات العام open-hadith-data في build/release/.

الاستعمال:
    python -I scripts/export_release.py                 # الافتراضي: النص بلا حركات
    python -I scripts/export_release.py --keep-vowels   # نسخة مشكولة في build/release-vowelled/

المخرجات: jsonl/<col>.jsonl.gz، وcsv/<col>.csv.gz، وopen-hadith-data.sqlite (مع FTS5)،
وmanifest.json، وopen-hadith-data-<version>.zip.

قواعد الحقوق: السجل يُبنى بقائمة بيضاء من الحقول، ثم يُفحص آليًّا فلا يدخله حقل محظور
(notes، grades، sharh، meter، colophon، text_source، editor_omitted، from_margin)؛ ويفشل البناء إن وُجد.
التشكيل من عمل محققي الطبعات، فالافتراضي إزالته من كل نص (text، isnad، matn، العناوين، أسماء الرواة).
"""
import argparse
import csv
import datetime
import gzip
import hashlib
import io
import json
import re
import shutil
import sqlite3
import sys
import zipfile
from collections import Counter, OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from hadith_ids import COLLECTIONS, load  # noqa: E402

VERSION = "0.1.0"
EXPECTED_TOTAL = 251348
FORBIDDEN = {"notes", "grades", "sharh", "meter", "colophon", "text_source", "editor_omitted", "from_margin"}

AR_NAMES = {
    "bukhari": "صحيح البخاري", "muslim": "صحيح مسلم", "abudawud": "سنن أبي داود",
    "tirmidhi": "سنن الترمذي", "nasai": "سنن النسائي (المجتبى)", "ibnmajah": "سنن ابن ماجه",
    "malik": "موطأ مالك", "darimi": "مسند الدارمي", "ahmad": "مسند أحمد",
    "tabaranikabir": "المعجم الكبير للطبراني", "tabaraniawsat": "المعجم الأوسط للطبراني",
    "tabaranisaghir": "المعجم الصغير للطبراني", "tayalisi": "مسند أبي داود الطيالسي",
    "humaydi": "مسند الحميدي", "ibnjarud": "المنتقى لابن الجارود", "adabmufrad": "الأدب المفرد",
    "tahawi": "شرح معاني الآثار", "nasaikubra": "السنن الكبرى للنسائي",
    "ibnabishaybah": "مصنف ابن أبي شيبة", "hakim": "المستدرك على الصحيحين",
    "daraqutni": "سنن الدارقطني", "ibnkhuzaymah": "صحيح ابن خزيمة",
    "ibnhibban": "صحيح ابن حبان (الإحسان)", "abdurrazzaq": "مصنف عبد الرزاق",
    "bayhaqi": "السنن الكبرى للبيهقي", "abuyala": "مسند أبي يعلى", "bazzar": "مسند البزار",
}
# طبعات غير مدرجة في MANIFEST.tsv (الاسم من Docs/hadith-pilot-spec.md 13.3)
EDITION_FALLBACK = {1681: "صحيح البخاري - ط السلطانية (مصوّرة طوق النجاة)"}

# الحركات وعلامات الضبط: تنوين وفتحة وضمة وكسرة وشدة وسكون وما يلحقها، والألف الخنجرية، وعلامات المصحف
HARAKAT = re.compile("[ؐ-ًؚ-ٰٟۖ-ۜ۟-۪ۨ-ۭ࣓-ࣿ]")
TATWEEL = "ـ"
ALEF = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه", TATWEEL: None})
WS = re.compile(r"\s+")


def strip_vowels(s):
    return HARAKAT.sub("", s) if isinstance(s, str) else s


def normalize(s):
    """text_plain: بلا حركات ولا تطويل، أ إ آ ٱ ← ا، ى ← ي، ة ← ه، مسافات موحدة."""
    if not s:
        return "" if s is not None else None
    return WS.sub(" ", HARAKAT.sub("", s).translate(ALEF)).strip()


def has_forbidden(obj):
    """يعيد أول مفتاح محظور في أي مستوى من الكائن، أو None."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in FORBIDDEN:
                return k
            f = has_forbidden(v)
            if f:
                return f
    elif isinstance(obj, list):
        for v in obj:
            f = has_forbidden(v)
            if f:
                return f
    return None


def load_matn_splitter():
    try:
        from matn import split  # scripts/matn.py
        return split
    except Exception as e:  # غير موجود بعد أو فشل استيراده
        print(f"تنبيه: تعذّر استيراد scripts/matn.py ({type(e).__name__}: {e}); "
              "isnad وmatn وmatn_confidence ستكون فارغة، وأعد البناء بعد اكتماله.")
        return None


def load_concordance(path):
    conc = {}
    if not path.exists():
        print(f"تنبيه: {path.relative_to(ROOT)} غير موجود؛ الحقل refs سيكون {{}}.")
        return conc
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            conc.setdefault(d["id"], {}).update(d.get("refs") or {})
    print(f"concordance: {len(conc):,} سجلًّا من {path.relative_to(ROOT)}")
    return conc


def load_edition_names():
    names = dict(EDITION_FALLBACK)
    with open(ROOT / "base" / "shamela" / "MANIFEST.tsv", encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            try:
                names.setdefault(int(row["id"]), row["name"])
            except (ValueError, KeyError):
                pass
    return names


def build_record(r, col, editions, split, conc, keep_vowels, stats):
    v = (lambda s: s) if keep_vowels else strip_vowels
    printed = (r.get("numbers") or {}).get("printed") or []
    sid = r["source"]["shamela"]
    isnad = matn = conf = method = None
    if split is not None:
        try:
            res = split(r) or {}
            isnad, matn = res.get("isnad"), res.get("matn")
            conf, method = res.get("confidence"), res.get("method")
        except Exception as e:
            stats["split_errors"] += 1
            if stats["split_errors"] <= 3:
                print(f"تنبيه: split فشل في {r['id']}: {type(e).__name__}: {e}")
    stats["matn_confidence"][str(conf)] += 1
    stats["matn_method"][str(method)] += 1
    corrections = [
        {"item": c.get("item") or (c.get("decision") or {}).get("rule") or c.get("diff_id"),
         "witnesses": c.get("witnesses") or ([c["source"]] if c.get("source") else [])}
        for c in r.get("corrections") or []
    ]
    out = OrderedDict()
    out["id"] = r["id"]
    out["collection"] = col
    out["number"] = printed[0] if printed else None
    out["numbers"] = r.get("numbers") or {}
    out["kitab"] = {"n": r["kitab"]["n"], "title": v(r["kitab"]["title"])}
    out["bab"] = {"n": r["bab"]["n"], "title": v(r["bab"]["title"])}
    out["loc"] = r.get("loc") or []
    out["edition"] = {"shamela_id": sid, "name": editions.get(sid)}
    out["text"] = v(r["text"])
    out["text_plain"] = normalize(r["text"])
    out["isnad"] = v(isnad)
    out["matn"] = v(matn)
    out["matn_confidence"] = conf
    out["matn_method"] = method
    if r.get("narrators"):
        out["narrators"] = [{"id": n["id"], "name": v(n["name"])} for n in r["narrators"]]
    out["refs"] = conc.get(r["id"], {})
    out["verse_refs"] = r.get("verse_refs") or []
    if "taqasim" in r:
        out["taqasim"] = r["taqasim"]
    if "abdullah_mark" in r:
        out["abdullah_mark"] = r["abdullah_mark"]
    if "duplicate_fragment" in r:
        out["duplicate_fragment"] = [v(x) for x in r["duplicate_fragment"]]
    out["corrected"] = bool(corrections)
    out["corrections"] = corrections
    bad = has_forbidden(out)
    if bad:
        sys.exit(f"خطأ: الحقل المحظور «{bad}» في السجل {r['id']}")
    if not keep_vowels and HARAKAT.search(out["text"] or ""):
        sys.exit(f"خطأ: حركات باقية في text للسجل {r['id']}")
    return out


CSV_COLS = ["id", "collection", "number", "kitab_n", "kitab_title", "bab_n", "bab_title", "juz", "page",
            "edition_id", "text", "text_plain", "isnad", "matn", "matn_confidence", "matn_method",
            "corrected"]


def flat(rec):
    loc0 = rec["loc"][0] if rec["loc"] else {}
    return {
        "id": rec["id"], "collection": rec["collection"], "number": rec["number"],
        "kitab_n": rec["kitab"]["n"], "kitab_title": rec["kitab"]["title"],
        "bab_n": rec["bab"]["n"], "bab_title": rec["bab"]["title"],
        "juz": loc0.get("juz"), "page": loc0.get("page"), "edition_id": rec["edition"]["shamela_id"],
        "text": rec["text"], "text_plain": rec["text_plain"], "isnad": rec["isnad"], "matn": rec["matn"],
        "matn_confidence": rec["matn_confidence"], "matn_method": rec["matn_method"],
        "corrected": int(rec["corrected"]),
    }


SCHEMA_SQL = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE collections (
  key TEXT PRIMARY KEY, name_ar TEXT NOT NULL, edition_id INTEGER, edition_name TEXT,
  hadith_count INTEGER NOT NULL, ord INTEGER NOT NULL);
CREATE TABLE hadiths (
  rowid INTEGER PRIMARY KEY, id TEXT NOT NULL UNIQUE, collection TEXT NOT NULL REFERENCES collections(key),
  ord INTEGER NOT NULL, number INTEGER, numbers TEXT NOT NULL,
  kitab_n INTEGER, kitab_title TEXT, bab_n INTEGER, bab_title TEXT,
  juz INTEGER, page INTEGER, loc TEXT NOT NULL, edition_id INTEGER,
  text TEXT NOT NULL, text_plain TEXT NOT NULL,
  isnad TEXT, matn TEXT, matn_plain TEXT, matn_confidence TEXT, matn_method TEXT,
  narrators TEXT, refs TEXT NOT NULL, verse_refs TEXT NOT NULL, extra TEXT,
  corrected INTEGER NOT NULL, corrections TEXT NOT NULL);
CREATE INDEX hadiths_col_num ON hadiths(collection, number);
CREATE INDEX hadiths_col_kitab ON hadiths(collection, kitab_n, bab_n);
CREATE TABLE kutub (
  collection TEXT NOT NULL, n INTEGER NOT NULL, title TEXT, hadith_count INTEGER NOT NULL,
  first_id TEXT, PRIMARY KEY (collection, n));
CREATE TABLE abwab (
  collection TEXT NOT NULL, kitab_n INTEGER NOT NULL, n INTEGER NOT NULL, title TEXT,
  hadith_count INTEGER NOT NULL, first_id TEXT, PRIMARY KEY (collection, kitab_n, n));
CREATE TABLE hadith_narrators (
  hadith_id TEXT NOT NULL, narrator_id INTEGER, name TEXT, position INTEGER NOT NULL,
  PRIMARY KEY (hadith_id, position));
CREATE INDEX hadith_narrators_nid ON hadith_narrators(narrator_id);
CREATE TABLE hadith_refs (hadith_id TEXT NOT NULL, system TEXT NOT NULL, value TEXT NOT NULL);
CREATE INDEX hadith_refs_sv ON hadith_refs(system, value);
CREATE INDEX hadith_refs_h ON hadith_refs(hadith_id);
CREATE VIRTUAL TABLE hadiths_fts USING fts5(
  text_plain, matn_plain, content='hadiths', content_rowid='rowid', tokenize='unicode61');
"""


def j(x):
    return json.dumps(x, ensure_ascii=False, separators=(",", ":"))


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def human(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB":
            return f"{n:,.1f} {u}" if u != "B" else f"{n} B"
        n /= 1024


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--keep-vowels", action="store_true", help="نسخة مشكولة (في build/release-vowelled/)")
    ap.add_argument("--out", help="مجلد المخرجات")
    ap.add_argument("--date", help="تاريخ الإصدار YYYY-MM-DD (الافتراضي اليوم)")
    ap.add_argument("--only", nargs="*", help="كتب بعينها (للتجربة؛ يعطّل فحص العدد الكلي)")
    args = ap.parse_args()
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except Exception:
            pass

    out = Path(args.out) if args.out else ROOT / "build" / ("release-vowelled" if args.keep_vowels else "release")
    date = args.date or datetime.date.today().isoformat()
    cols = args.only or COLLECTIONS
    if out.exists():
        shutil.rmtree(out)
    (out / "jsonl").mkdir(parents=True)
    (out / "csv").mkdir()

    editions = load_edition_names()
    split = load_matn_splitter()
    conc = load_concordance(ROOT / "build" / "concordance.jsonl")

    db_path = out / "open-hadith-data.sqlite"
    db = sqlite3.connect(db_path)
    db.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;" + SCHEMA_SQL)

    stats = {"split_errors": 0, "matn_confidence": Counter(), "matn_method": Counter()}
    counts, eds, ids_seen = OrderedDict(), OrderedDict(), set()
    rowid = 0
    for ci, col in enumerate(cols):
        kutub, abwab, narr_rows, ref_rows, rows = OrderedDict(), OrderedDict(), [], [], []
        ed_ids = Counter()
        jpath = out / "jsonl" / f"{col}.jsonl.gz"
        cpath = out / "csv" / f"{col}.csv.gz"
        with open(jpath, "wb") as jraw, gzip.GzipFile(fileobj=jraw, mode="wb", mtime=0) as jgz, \
                open(cpath, "wb") as craw, gzip.GzipFile(fileobj=craw, mode="wb", mtime=0) as cgz:
            jw = io.TextIOWrapper(jgz, encoding="utf-8", newline="\n")
            cw_t = io.TextIOWrapper(cgz, encoding="utf-8", newline="")
            cw = csv.DictWriter(cw_t, fieldnames=CSV_COLS)
            cw.writeheader()
            n = 0
            for r in load(col):
                if r.get("type") != "hadith":
                    continue
                rec = build_record(r, col, editions, split, conc, args.keep_vowels, stats)
                if rec["id"] in ids_seen:
                    sys.exit(f"خطأ: معرّف مكرر {rec['id']}")
                ids_seen.add(rec["id"])
                n += 1
                rowid += 1
                ed_ids[rec["edition"]["shamela_id"]] += 1
                jw.write(j(rec) + "\n")
                fr = flat(rec)
                cw.writerow(fr)
                extra = {k: rec[k] for k in ("taqasim", "abdullah_mark", "duplicate_fragment") if k in rec}
                rows.append((
                    rowid, rec["id"], col, n, rec["number"], j(rec["numbers"]),
                    fr["kitab_n"], fr["kitab_title"], fr["bab_n"], fr["bab_title"], fr["juz"], fr["page"],
                    j(rec["loc"]), fr["edition_id"], rec["text"], rec["text_plain"],
                    rec["isnad"], rec["matn"], normalize(rec["matn"]), None if rec["matn_confidence"] is None
                    else str(rec["matn_confidence"]), rec["matn_method"],
                    j(rec["narrators"]) if "narrators" in rec else None, j(rec["refs"]), j(rec["verse_refs"]),
                    j(extra) if extra else None, int(rec["corrected"]), j(rec["corrections"])))
                kn, bn = rec["kitab"]["n"], rec["bab"]["n"]
                k = kutub.setdefault(kn, [rec["kitab"]["title"], 0, rec["id"]])
                k[1] += 1
                b = abwab.setdefault((kn, bn), [rec["bab"]["title"], 0, rec["id"]])
                b[1] += 1
                for pos, nr in enumerate(rec.get("narrators") or [], 1):
                    narr_rows.append((rec["id"], nr["id"], nr["name"], pos))
                for system, val in rec["refs"].items():
                    for x in (val if isinstance(val, list) else [val]):
                        ref_rows.append((rec["id"], system, str(x)))
            jw.flush(); jw.detach()
            cw_t.flush(); cw_t.detach()
        sid = ed_ids.most_common(1)[0][0] if ed_ids else None
        counts[col] = n
        eds[col] = {"shamela_id": sid, "name": editions.get(sid)}
        db.executemany(f"INSERT INTO hadiths VALUES ({','.join('?' * 27)})", rows)
        db.executemany("INSERT INTO kutub VALUES (?,?,?,?,?)",
                       [(col, kn, t, c, f) for kn, (t, c, f) in kutub.items()])
        db.executemany("INSERT INTO abwab VALUES (?,?,?,?,?,?)",
                       [(col, kn, bn, t, c, f) for (kn, bn), (t, c, f) in abwab.items()])
        db.executemany("INSERT INTO hadith_narrators VALUES (?,?,?,?)", narr_rows)
        db.executemany("INSERT INTO hadith_refs VALUES (?,?,?)", ref_rows)
        db.execute("INSERT INTO collections VALUES (?,?,?,?,?,?)",
                   (col, AR_NAMES.get(col, col), sid, editions.get(sid), n, ci + 1))
        print(f"{col:15} {n:7,}  ط {sid}")

    total = sum(counts.values())
    db.execute("INSERT INTO hadiths_fts(hadiths_fts) VALUES ('rebuild')")
    db.executemany("INSERT INTO meta VALUES (?,?)", [
        ("version", VERSION), ("date", date), ("vowels", "kept" if args.keep_vowels else "stripped"),
        ("total", str(total)), ("license", "CC BY 4.0 (structure); texts public domain; see LICENSE-DATA.md")])
    db.commit()

    # ===== الفحوص =====
    problems = []
    if not args.only and total != EXPECTED_TOTAL:
        problems.append(f"العدد الكلي {total:,} لا يطابق {EXPECTED_TOTAL:,}")
    if len(ids_seen) != total:
        problems.append("المعرّفات غير فريدة")
    db_cols = {r[1] for t in ("hadiths", "collections", "kutub", "abwab", "hadith_narrators", "hadith_refs")
               for r in db.execute(f"PRAGMA table_info({t})")}
    if db_cols & FORBIDDEN:
        problems.append(f"أعمدة محظورة في SQLite: {db_cols & FORBIDDEN}")
    if db.execute("SELECT count(*) FROM hadiths").fetchone()[0] != total:
        problems.append("عدد صفوف hadiths لا يطابق")
    if "bukhari" in cols:
        hit = [r[0] for r in db.execute(
            "SELECT h.id FROM hadiths_fts f JOIN hadiths h ON h.rowid=f.rowid "
            "WHERE hadiths_fts MATCH 'انما الاعمال بالنيات' AND h.collection='bukhari' ORDER BY h.rowid")]
        print(f"FTS «انما الاعمال بالنيات» في البخاري: {len(hit)} نتيجة، أولها {hit[:3]}")
        if "bukhari:1" not in hit:
            problems.append("بحث FTS لم يجد bukhari:1")
    db.execute("PRAGMA optimize")
    db.close()
    with sqlite3.connect(db_path) as db2:
        db2.execute("VACUUM")
    # إعادة فحص jsonl.gz المكتوبة نفسها: لا مفتاح محظور في أي سجل
    rescanned = 0
    for col in cols:
        with gzip.open(out / "jsonl" / f"{col}.jsonl.gz", "rt", encoding="utf-8") as f:
            for line in f:
                bad = has_forbidden(json.loads(line))
                rescanned += 1
                if bad:
                    problems.append(f"حقل محظور {bad} في {col}")
                    break
    if rescanned != total:
        problems.append(f"أُعيد فحص {rescanned:,} سجلًّا لا {total:,}")
    if problems:
        sys.exit("فشل البناء:\n- " + "\n- ".join(problems))
    print(f"الفحوص: العدد {total:,} ok، المعرّفات فريدة ok، لا حقول محظورة ({rescanned:,} سجلًّا) ok")
    if split is None:
        print("تنبيه: matn وisnad فارغة (matn.py غير متاح).")
    if stats["split_errors"]:
        print(f"تنبيه: split فشل في {stats['split_errors']:,} سجلًّا.")

    # ===== README وLICENSE والبيان والحزمة =====
    shutil.copyfile(ROOT / "Docs" / "DATA.md", out / "README_DATA.md")
    shutil.copyfile(ROOT / "LICENSE-DATA.md", out / "LICENSE-DATA.md")
    files = sorted([p for p in out.rglob("*") if p.is_file()], key=lambda p: p.relative_to(out).as_posix())
    manifest = OrderedDict([
        ("name", "open-hadith-data"), ("version", VERSION), ("date", date),
        ("source", "https://github.com/samt-qa/open-hadith-data"),
        ("vowels", "kept" if args.keep_vowels else "stripped"),
        ("total", total), ("counts", counts), ("editions", eds),
        ("matn", {"splitter": "scripts/matn.py" if split else None,
                  "confidence": dict(stats["matn_confidence"]), "method": dict(stats["matn_method"])}),
        ("refs_source", "build/concordance.jsonl" if conc else None),
        ("excluded_fields", sorted(FORBIDDEN)),
        ("files", OrderedDict((p.relative_to(out).as_posix(),
                               {"bytes": p.stat().st_size, "sha256": sha256(p)}) for p in files)),
    ])
    with open(out / "manifest.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write("\n")
    suffix = "-vowelled" if args.keep_vowels else ""
    zpath = out / f"open-hadith-data-{VERSION}{suffix}.zip"
    zdt = tuple(int(x) for x in date.split("-")) + (0, 0, 0)
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in files + [out / "manifest.json"]:
            rel = p.relative_to(out).as_posix()
            zi = zipfile.ZipInfo(f"open-hadith-data-{VERSION}{suffix}/{rel}", date_time=zdt)
            zi.compress_type = zipfile.ZIP_STORED if p.suffix == ".gz" else zipfile.ZIP_DEFLATED
            with open(p, "rb") as src, z.open(zi, "w") as dst:
                shutil.copyfileobj(src, dst, 1 << 20)

    print("\nالأحجام:")
    for p in sorted(out.rglob("*")):
        if p.is_file():
            print(f"  {human(p.stat().st_size):>10}  {p.relative_to(out).as_posix()}")
    print(f"sha256 الحزمة: {sha256(zpath)}")


if __name__ == "__main__":
    main()
