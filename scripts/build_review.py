"""الخطوة 8: يولّد review/index.html — ملف واحد ساكن بلا خادم، من اليمين، يصلح للجوال.

يضمّن قائمة المراجعة داخل الصفحة. الصور تُحمَّل بمسار نسبي من work/pages/.
القرارات تُحفظ في المتصفح (localStorage) وتُصدَّر ملف decisions.jsonl بزر.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "review" / "queue.jsonl"
OUT = ROOT / "review" / "index.html"

HTML = r"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>مراجعة الفروق — تجربة البخاري</title>
<style>
:root{--bg:#f6f3ec;--card:#fffdf8;--ink:#1d1b16;--mute:#6b6557;--line:#d9d2c0;--a:#1f5f8b;--p:#7a3e12;--b:#3d6b35;--hl:#ffe9a8;--warn:#a0341a}
@media (prefers-color-scheme:dark){:root{--bg:#17150f;--card:#211e16;--ink:#ece6d6;--mute:#a59d88;--line:#3a3527;--a:#7fb8e0;--p:#e0a573;--b:#9ccb92;--hl:#5a4a12;--warn:#ef8a6e}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.7 "Segoe UI",Tahoma,sans-serif}
header{position:sticky;top:0;z-index:5;background:var(--card);border-bottom:1px solid var(--line);padding:8px 12px}
header h1{font-size:17px;margin:0 0 6px}
.bar{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.bar button,.bar select{font:inherit;font-size:14px;padding:5px 10px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--ink)}
.bar button.on{background:var(--ink);color:var(--bg)}
#prog{font-size:13px;color:var(--mute);margin-inline-start:auto}
main{max-width:900px;margin:0 auto;padding:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;margin:0 0 16px;overflow:hidden}
.card.done{border-color:var(--b)}
.meta{display:flex;flex-wrap:wrap;gap:8px;padding:8px 12px;font-size:13px;color:var(--mute);border-bottom:1px solid var(--line)}
.tag{padding:0 8px;border-radius:10px;border:1px solid var(--line)}
.tag.lv{color:var(--ink);font-weight:600}
.tag.unc{color:var(--warn);border-color:var(--warn)}
.crop{position:relative;height:210px;overflow:hidden;background:#ddd;border-bottom:1px solid var(--line);cursor:zoom-in}
.crop img{position:absolute;top:0;left:0;max-width:none}
.crop .mark{position:absolute;left:0;right:0;top:50%;height:0;border-top:2px dashed rgba(200,40,40,.55);pointer-events:none}
.body{padding:10px 12px}
.ar{font-family:"Amiri","Scheherazade New","Traditional Arabic","Sakkal Majalla","Times New Roman",serif;font-size:25px;line-height:2.1}
.row{display:grid;grid-template-columns:2.2em 1fr;gap:8px;align-items:baseline;padding:4px 0;border-bottom:1px dotted var(--line)}
.row b{font:600 14px sans-serif}
.row.A b{color:var(--a)}.row.P b{color:var(--p)}.row.B b{color:var(--b)}
.ctx{color:var(--mute)}
mark{background:var(--hl);color:inherit;padding:0 4px;border-radius:4px}
.empty{color:var(--mute);font:14px sans-serif}
.detail,.opinion,.note0{font-size:14px;margin:8px 0;padding:6px 10px;border-radius:6px;background:var(--bg)}
.opinion b{color:var(--warn)}
.choices{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
.choices button{font:inherit;font-size:15px;padding:6px 14px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--ink);cursor:pointer}
.choices button.sel{background:var(--ink);color:var(--bg)}
.choices button:disabled{opacity:.35;cursor:default}
textarea,input[type=text]{width:100%;font:inherit;margin-top:8px;padding:6px 8px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--ink)}
textarea.custom{display:none;font-family:inherit;font-size:22px}
.ex{display:grid;grid-template-columns:1fr 1fr;gap:2px 14px}
dialog{max-width:100vw;max-height:100vh;padding:0;border:0}
dialog img{display:block;max-width:none;width:160vw}
@media (min-width:800px){dialog img{width:1100px}}
</style>
</head>
<body>
<header>
<h1>مراجعة الفروق — صحيح البخاري، الصفحات ٦–٢٥ (تجربة)</h1>
<div class="bar">
<select id="flv"><option value="">كل المستويات</option><option>L5</option><option>L4</option><option>L3</option><option>L2</option></select>
<select id="fkind"><option value="">كل الأنواع</option></select>
<button id="fopen">غير المحسوم فقط</button>
<button id="export">تصدير decisions.jsonl</button>
<span id="prog"></span>
</div>
</header>
<main id="list"></main>
<dialog id="dlg"><img id="dimg" alt=""></dialog>
<script>
const QUEUE = __QUEUE__;
const KEY = "open-hadith-text:pilot:decisions";
const KIND = {substitution:"إبدال",omission_in_P:"سقط في المطبوع (أو زيادة في A)",addition_in_P:"زيادة في المطبوع (أو سقط في A)",spelling:"إملاء",tashkeel_different:"حركة مختلفة",tashkeel_missing:"حركات ناقصة (مجمّعة)",no_match_in_A:"لا مطابق في A",in_A_not_in_P:"في A وليس في القراءة"};
let dec = {}; try { dec = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch(e) {}
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(dec)); } catch(e) {} progress(); };
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const el = (t, c, h) => { const e = document.createElement(t); if (c) e.className = c; if (h != null) e.innerHTML = h; return e; };
function progress(){ const n = QUEUE.filter(q => dec[q.diff_id] && dec[q.diff_id].choice).length; document.getElementById("prog").textContent = `محسوم ${n} من ${QUEUE.length}`; }
function reading(q, w){
  const r = q.readings[w];
  if (r == null) return '<span class="empty">— لا يوجد —</span>';
  if (q.kind === "no_match_in_A" || q.kind === "in_A_not_in_P") return esc(r) || '<span class="empty">(نص فارغ)</span>';
  return `<span class="ctx">${esc(q.context_before||"")}</span> <mark>${esc(r) || "∅"}</mark> <span class="ctx">${esc(q.context_after||"")}</span>`;
}
function place(img, q){
  const box = img.parentElement, W = box.clientWidth, even = q.crop.page % 2 === 0;
  const fx0 = even ? 340 : 290, fw = 1085, s = W / fw;
  img.style.width = (img.naturalWidth * s) + "px";
  const y = (150 + q.crop.y_frac * 1810) * s;
  img.style.left = (-fx0 * s) + "px";
  img.style.top = (box.clientHeight / 2 - y) + "px";
}
function card(q){
  const c = el("section", "card"); c.dataset.id = q.diff_id;
  const m = el("div", "meta");
  m.innerHTML = `<span class="tag lv">${q.level}</span><span class="tag">${KIND[q.kind]||q.kind}</span><span>${q.diff_id}</span>` +
    (q.crop ? `<span>ص ${q.crop.page} · السطر التقريبي ${q.approx_line}</span>` : "") +
    (q.p_uncertain ? `<span class="tag unc">القارئ شكّ في هذا الموضع</span>` : "");
  c.append(m);
  if (q.image && q.crop){
    const b = el("div", "crop"), img = new Image();
    img.loading = "lazy"; img.alt = "صورة الصفحة " + q.crop.page; img.src = "../" + q.image;
    img.onload = () => place(img, q);
    b.append(img, el("div", "mark"));
    b.onclick = () => { document.getElementById("dimg").src = img.src; document.getElementById("dlg").showModal(); };
    c.append(b);
  }
  const body = el("div", "body");
  if (q.kind === "tashkeel_missing"){
    const d = q.detail;
    body.append(el("div", "detail", `حروف مشكولة في A وغير مشكولة في المطبوع: <b>${d.missing_in_P}</b> · مشكولة في المطبوع وغير مشكولة في A: <b>${d.missing_in_A}</b>. أمثلة (A ثم P):`));
    const ex = el("div", "ex ar");
    d.examples.forEach(e => { ex.append(el("span", "", esc(e.A)), el("span", "", esc(e.P))); });
    body.append(ex);
  } else {
    for (const w of ["A","B","P"]){
      if (w === "B" && q.readings.B == null) continue;
      const r = el("div", "row " + w); r.append(el("b", "", w), el("div", "ar", reading(q, w))); body.append(r);
    }
    if (Array.isArray(q.detail)) body.append(el("div", "detail", q.detail.map(esc).join("<br>")));
  }
  if (q.note) body.append(el("div", "note0", esc(q.note)));
  if (q.agent_opinion){
    const o = q.agent_opinion;
    body.append(el("div", "opinion", `<b>رأي الوكيل (لا يُطبَّق):</b> ${esc(o.choice)} · الثقة: ${esc(o.confidence)}<br>${esc(o.why||"")}`));
  }
  const ch = el("div", "choices"), ta = el("textarea", "custom ar"), note = el("input"); note.type = "text"; note.placeholder = "ملاحظة";
  ta.placeholder = "النص الصحيح كما في الصورة";
  const cur = dec[q.diff_id] || {};
  const opts = [["A","A"],["B","B"],["P","P (المطبوع)"],["custom","نص آخر"],["defer","تأجيل"]];
  const upd = () => {
    ch.querySelectorAll("button").forEach(b => b.classList.toggle("sel", (dec[q.diff_id]||{}).choice === b.dataset.v));
    ta.style.display = (dec[q.diff_id]||{}).choice === "custom" ? "block" : "none";
    c.classList.toggle("done", !!(dec[q.diff_id]||{}).choice);
  };
  for (const [v, label] of opts){
    const b = el("button", "", label); b.dataset.v = v;
    if ((v === "A" || v === "B" || v === "P") && q.readings[v] == null && q.kind !== "tashkeel_missing") b.disabled = true;
    if (v === "B" && q.readings.B == null) b.disabled = true;
    b.onclick = () => {
      const d = dec[q.diff_id] = dec[q.diff_id] || {};
      d.choice = d.choice === v ? null : v; d.decided_at = new Date().toISOString(); save(); upd();
    };
    ch.append(b);
  }
  ta.value = cur.custom_text || ""; note.value = cur.note || "";
  ta.oninput = () => { (dec[q.diff_id] = dec[q.diff_id] || {}).custom_text = ta.value; save(); };
  note.oninput = () => { (dec[q.diff_id] = dec[q.diff_id] || {}).note = note.value; save(); };
  body.append(ch, ta, note); c.append(body); upd();
  return c;
}
let onlyOpen = false;
function render(){
  const lv = document.getElementById("flv").value, kd = document.getElementById("fkind").value, list = document.getElementById("list");
  list.textContent = "";
  QUEUE.filter(q => (!lv || q.level === lv) && (!kd || q.kind === kd) && (!onlyOpen || !(dec[q.diff_id]||{}).choice)).forEach(q => list.append(card(q)));
  progress();
}
const fk = document.getElementById("fkind");
[...new Set(QUEUE.map(q => q.kind))].forEach(k => { const o = el("option", "", KIND[k]||k); o.value = k; fk.append(o); });
document.getElementById("flv").onchange = render; fk.onchange = render;
document.getElementById("fopen").onclick = e => { onlyOpen = !onlyOpen; e.target.classList.toggle("on", onlyOpen); render(); };
document.getElementById("dlg").onclick = e => e.currentTarget.close();
document.getElementById("export").onclick = () => {
  const lines = QUEUE.filter(q => (dec[q.diff_id]||{}).choice).map(q => { const d = dec[q.diff_id];
    return JSON.stringify({diff_id: q.diff_id, choice: d.choice, custom_text: d.choice === "custom" ? (d.custom_text || "") : null, note: d.note || "", decided_by: "owner", decided_at: d.decided_at}); });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([lines.join("\n") + "\n"], {type: "application/x-ndjson"}));
  a.download = "decisions.jsonl"; a.click();
};
window.addEventListener("resize", () => document.querySelectorAll(".crop img").forEach(i => { const q = QUEUE.find(x => x.diff_id === i.closest(".card").dataset.id); if (i.naturalWidth) place(i, q); }));
render();
</script>
</body>
</html>
"""


def main() -> int:
    queue = [json.loads(line) for line in QUEUE.read_text(encoding="utf-8").splitlines() if line.strip()]
    data = json.dumps(queue, ensure_ascii=False).replace("</", "<\\/")
    OUT.write_text(HTML.replace("__QUEUE__", data), encoding="utf-8")
    print(len(queue), "items ->", OUT.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
