"""الخطوة 5 (الشق الآلي): يحوّل مسوّدات القراءة العمياء إلى ملفات القراءة بالشكل 5.1.

المسوّدة يكتبها القارئ وفيها مواضع الشك بين ⟦ ⟧؛ هنا تُزال العلامتان وتُحسب offset/length.
لا يغيّر شيئًا من النص المقروء.
"""
import datetime
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DRAFT = ROOT / "work" / "readings" / "bukhari" / "j01" / "draft"
OUT = ROOT / "work" / "readings" / "bukhari" / "j01"
PAGES = ROOT / "work" / "pages" / "bukhari" / "j01"
READER = "Claude Fable 5.2 (claude-fable-5-2)، وكيل فرعي بلا اطلاع على base/"


def unmark(marked: str, notes: list[str]):
    text, unc, pos, k = [], [], 0, 0
    for part in re.split(r"(⟦[^⟧]*⟧)", marked):
        if part.startswith("⟦"):
            inner = part[1:-1]
            unc.append({"offset": pos, "length": len(inner), "note": notes[k] if k < len(notes) else ""})
            k += 1
            part = inner
        text.append(part)
        pos += len(part)
    return "".join(text), unc


def main() -> int:
    manifest = {p["pdf_index"]: p for p in json.loads((PAGES / "manifest.json").read_text(encoding="utf-8"))["pages"]}
    n = 0
    for f in sorted(DRAFT.glob("p*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        page = d["page"]
        segs = []
        for s in d["segments"]:
            text, unc = unmark(s["text_marked"], s.get("uncertain_notes", []))
            segs.append({"seq": s["seq"], "kind": s["kind"], "printed_number": s.get("printed_number"),
                         "text": text, "uncertain": unc,
                         "continues_from_prev_page": bool(s.get("continues_from_prev_page")),
                         "continues_to_next_page": bool(s.get("continues_to_next_page")),
                         **({"segment_note": s["segment_note"]} if s.get("segment_note") else {})})
        out = {
            "collection": "bukhari", "edition": "sultaniyya-1311", "juz": 1, "page": page,
            "pdf_file": "sources/bukhari/sultaniyya/j01.pdf", "pdf_index": page,
            "image": f"work/pages/bukhari/j01/i{page:03d}.jpg", "image_sha256": manifest[page]["sha256"],
            "printed_page_number_seen": d.get("printed_page_number_seen"),
            "segments": segs, "margin_notes_present": bool(d.get("margin_notes_present")),
            **({"page_note": d["page_note"]} if d.get("page_note") else {}),
            "reader": READER,
            "read_at": datetime.datetime.fromtimestamp(f.stat().st_mtime).astimezone().isoformat(timespec="seconds"),
        }
        (OUT / f.name).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        n += 1
    print(n, "reading files written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
