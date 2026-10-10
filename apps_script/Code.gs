/**
 * رصد الهلال — جسر Google Sheets (يُلصق مرة واحدة في Apps Script داخل جدول جديد).
 * يقدّم: حفظ المنشورات المرصودة، حالة النظام، تقييماتك (مهم/مستبعد)، بريد احتياطي، ولوحة متابعة بهوية الهيئة.
 * الإعداد: شغّل الدالة setup() مرة واحدة، ثم Deploy > New deployment > Web app (Execute as: Me, Who has access: Anyone).
 */
const SH_ITEMS = 'الرصد', SH_FB = 'التقييمات', SH_STATUS = 'الحالة';

function setup() {
  const p = PropertiesService.getScriptProperties();
  if (!p.getProperty('SECRET')) p.setProperty('SECRET', Utilities.getUuid().replace(/-/g, ''));
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  [SH_ITEMS, SH_FB, SH_STATUS].forEach(n => { if (!ss.getSheetByName(n)) ss.insertSheet(n); });
  const fb = ss.getSheetByName(SH_FB);
  if (fb.getLastRow() === 0) fb.appendRow(['id', 'التقييم', 'الوقت', 'الحساب', 'النص']);
  ss.getSheets().forEach(s => s.setRightToLeft(true));
  MailApp.getRemainingDailyQuota();
  Logger.log('SHEET_SECRET=' + p.getProperty('SECRET'));
}

function secret_() { return PropertiesService.getScriptProperties().getProperty('SECRET'); }
function json_(o) { return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON); }

function doPost(e) {
  let d;
  try { d = JSON.parse(e.postData.contents); } catch (err) { return json_({ ok: false, error: 'bad json' }); }
  if (!d.secret || d.secret !== secret_()) return json_({ ok: false, error: 'forbidden' });
  const lock = LockService.getScriptLock(); lock.waitLock(20000);
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    if (d.action === 'append') {
      const sh = ss.getSheetByName(SH_ITEMS);
      if (sh.getLastRow() === 0) { sh.appendRow(d.cols); sh.setFrozenRows(1); }
      const have = new Set(sh.getLastRow() > 1 ? sh.getRange(2, 1, sh.getLastRow() - 1, 1).getValues().map(r => String(r[0])) : []);
      const rows = d.rows.filter(r => !have.has(String(r[0])));
      if (rows.length) sh.getRange(sh.getLastRow() + 1, 1, rows.length, rows[0].length).setValues(rows);
      return json_({ ok: true, added: rows.length });
    }
    if (d.action === 'status') {
      const p = PropertiesService.getScriptProperties();
      if (d.set) {
        p.setProperty('STATUS', JSON.stringify(d.set));
        const sh = ss.getSheetByName(SH_STATUS); sh.clear();
        sh.appendRow(['آخر فحص', d.set.last_run || '']); sh.appendRow(['يعمل من', d.set.runner === 'backup' ? 'التشغيل الاحتياطي' : 'السيرفر']);
        Object.keys(d.set.sources || {}).forEach(k => sh.appendRow([k, d.set.sources[k]]));
      }
      return json_({ ok: true, status: JSON.parse(p.getProperty('STATUS') || '{}') });
    }
    if (d.action === 'seen') {
      const sh = ss.getSheetByName(SH_ITEMS);
      const ids = sh.getLastRow() > 1 ? sh.getRange(2, 1, sh.getLastRow() - 1, 1).getValues().map(r => String(r[0])) : [];
      return json_({ ok: true, ids: ids.slice(-5000) });
    }
    if (d.action === 'feedback') {
      const sh = ss.getSheetByName(SH_FB);
      const v = sh.getLastRow() > 1 ? sh.getRange(2, 1, sh.getLastRow() - 1, 5).getValues() : [];
      return json_({ ok: true, items: v.slice(-200).map(r => ({ id: r[0], verdict: r[1], at: String(r[2]), author: r[3], text: r[4] })) });
    }
    if (d.action === 'email') {
      MailApp.sendEmail({ to: Session.getEffectiveUser().getEmail(), subject: d.subject, htmlBody: d.html });
      return json_({ ok: true });
    }
    return json_({ ok: false, error: 'unknown action' });
  } finally { lock.releaseLock(); }
}

/** يُستدعى من أزرار اللوحة */
function rate(k, id, verdict) {
  if (k !== secret_()) throw new Error('forbidden');
  const ss = SpreadsheetApp.getActiveSpreadsheet(), items = ss.getSheetByName(SH_ITEMS);
  const f = items.getRange('A:A').createTextFinder(id).matchEntireCell(true).findNext();
  let author = '', text = '';
  if (f) { const r = items.getRange(f.getRow(), 1, 1, 17).getValues()[0]; author = r[3]; text = r[16]; }
  ss.getSheetByName(SH_FB).appendRow([id, verdict, new Date().toISOString(), author, String(text).slice(0, 500)]);
  return true;
}

function data(k) {
  if (k !== secret_()) throw new Error('forbidden');
  const ss = SpreadsheetApp.getActiveSpreadsheet(), sh = ss.getSheetByName(SH_ITEMS);
  const n = sh.getLastRow() - 1;
  const rows = n > 0 ? sh.getRange(Math.max(2, sh.getLastRow() - 799), 1, Math.min(n, 800), 17).getDisplayValues() : [];
  const fb = {}; const f = ss.getSheetByName(SH_FB);
  if (f.getLastRow() > 1) f.getRange(2, 1, f.getLastRow() - 1, 2).getValues().forEach(r => fb[r[0]] = r[1]);
  return { rows: rows.reverse(), fb, status: JSON.parse(PropertiesService.getScriptProperties().getProperty('STATUS') || '{}') };
}

function doGet(e) {
  const k = (e.parameter || {}).k || '';
  if (k !== secret_()) return HtmlService.createHtmlOutput('<p dir="rtl" style="font-family:Tahoma">الرابط غير صحيح.</p>');
  const t = HtmlService.createTemplate(PAGE); t.k = k;
  return t.evaluate().setTitle('لوحة رصد الهلال').addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

const PAGE = `<!doctype html><html dir="rtl" lang="ar"><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@300;500;800&display=swap" rel="stylesheet">
<style>
:root{--navy:#101332;--red:#CE2E26;--green:#42924B;--gold:#F1B944;--violet:#513A87;--bg:#f5f5f8;--card:#fff;--fg:#14162e;--mut:#5d6079;--line:#e3e4ec}
@media(prefers-color-scheme:dark){:root{--bg:#0b0d24;--card:#14173a;--fg:#eceef8;--mut:#a3a6c4;--line:#262a55}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font-family:"Frutiger LT Arabic",Tajawal,Tahoma,sans-serif;font-weight:300}
header{background:var(--navy);color:#fff;padding:18px 16px}header h1{margin:0;font-weight:800;font-size:1.5rem}
header p{margin:4px 0 0;color:#c9cbe3;font-size:.9rem}.wrap{max-width:1100px;margin:0 auto;padding:16px}
.kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-top:12px}
.kpi{background:rgba(255,255,255,.08);border-radius:10px;padding:8px 12px}.kpi b{display:block;font-size:1.4rem;color:var(--gold);font-weight:800}
.kpi span{font-size:.8rem;color:#c9cbe3}.bar{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0 14px}
select,input{font:inherit;padding:6px 10px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--fg)}
.it{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin-bottom:8px}
.it .top{display:flex;flex-wrap:wrap;gap:6px;align-items:center;font-size:.8rem;color:var(--mut)}
.chip{border-radius:999px;padding:1px 9px;font-weight:500;font-size:.75rem}
.r1{background:#fbe7e6;color:#a3241e}.r2{background:#fdf3dc;color:#8a6110}.r3{background:#eef0f6;color:#5d6079}
.ok{background:#ece8f6;color:#513A87}.pv{background:transparent;color:var(--mut);border:1px solid var(--line)}
.it h3{margin:6px 0 4px;font-size:1rem;font-weight:500}.it .tx{color:var(--mut);font-size:.85rem;max-height:4.6em;overflow:hidden}
.act{display:flex;gap:6px;margin-top:8px}.act button,.act a{font:inherit;font-size:.8rem;border:1px solid var(--line);background:transparent;color:var(--fg);border-radius:8px;padding:4px 10px;cursor:pointer;text-decoration:none}
.act button.on{background:var(--navy);color:#fff}.st{font-size:.8rem;color:var(--mut);margin-top:6px}
@media(max-width:560px){.kpis{grid-template-columns:repeat(2,1fr)}}
</style></head><body>
<header><h1>لوحة رصد هيئة الهلال الأحمر السعودي</h1><p id="st">جارٍ التحميل…</p><div class="kpis" id="k"></div></header>
<div class="wrap"><div class="bar">
<select id="fr"><option value="">كل الارتباط</option><option>مؤكد</option><option>محتمل</option></select>
<select id="fp"><option value="">كل المنصات</option></select>
<select id="fs"><option value="">كل المشاعر</option><option>إيجابي</option><option>سلبي</option><option>مختلط</option><option>محايد</option></select>
<select id="fpr"><option value="">كل الأولويات</option><option>عاجل</option><option>مهم</option><option>اعتيادي</option></select>
<input id="q" placeholder="بحث في النص"></div><div id="list"></div></div>
<script>
const K='<?= k ?>';let D={rows:[],fb:{}};
const P={x:'X',tiktok:'تيك توك',news:'الأخبار',youtube:'يوتيوب',telegram:'تيليجرام',app:'تقييم تطبيق',reddit:'ريديت',web:'موقع/منتدى',maps:'خرائط قوقل'};
function esc(s){return String(s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function draw(){const fr=fr_.value,fp=fp_.value,fs=fs_.value,fpr=fpr_.value,q=q_.value.trim();
 const R=D.rows.filter(r=>(!fr||r[8]==fr)&&(!fp||r[2]==fp)&&(!fs||r[7]==fs)&&(!fpr||r[11]==fpr)&&(!q||(r[5]+r[16]).includes(q)));
 list.innerHTML=R.slice(0,300).map(r=>{const v=D.fb[r[0]]||'';const pc=r[11]=='عاجل'?'r1':r[11]=='مهم'?'r2':'r3';
 return '<div class="it"><div class="top"><span class="chip '+pc+'">'+esc(r[11]||'—')+'</span><span class="chip '+(r[8]=='مؤكد'?'ok':'pv')+'">'+esc(r[8])+'</span>'
 +'<span>'+esc(P[r[2]]||r[2])+'</span><span>'+esc(r[1])+'</span><span>@'+esc(r[3])+'</span><span>'+esc(r[6])+'</span><span>'+esc(r[7])+'</span></div>'
 +'<h3>'+esc(r[5])+'</h3><div class="tx">'+esc(r[16])+'</div>'
 +'<div class="act"><a href="'+esc(r[4])+'" target="_blank">افتح</a><button class="'+(v=='مهم'?'on':'')+'" onclick="rate(\\''+r[0]+'\\',\\'مهم\\',this)">مهم</button>'
 +'<button class="'+(v=='مستبعد'?'on':'')+'" onclick="rate(\\''+r[0]+'\\',\\'مستبعد\\',this)">مستبعد</button></div></div>'}).join('')||'<p>لا نتائج.</p>';}
function rate(id,v,b){b.classList.add('on');D.fb[id]=v;google.script.run.withFailureHandler(()=>{b.classList.remove('on')}).rate(K,id,v)}
const fr_=document.getElementById('fr'),fp_=document.getElementById('fp'),fs_=document.getElementById('fs'),fpr_=document.getElementById('fpr'),q_=document.getElementById('q');
[fr_,fp_,fs_,fpr_].forEach(e=>e.onchange=draw);q_.oninput=draw;
google.script.run.withSuccessHandler(d=>{D=d;const now=Date.now(),day=864e5;
 const c24=d.rows.filter(r=>r[8]=='مؤكد'&&now-new Date(r[1].replace(' ','T')+':00+03:00')<day).length;
 const c7=d.rows.filter(r=>r[8]=='مؤكد'&&now-new Date(r[1].replace(' ','T')+':00+03:00')<7*day).length;
 const neg=d.rows.filter(r=>r[8]=='مؤكد'&&r[7]=='سلبي'&&now-new Date(r[1].replace(' ','T')+':00+03:00')<7*day).length;
 const pv=d.rows.filter(r=>r[8]=='محتمل'&&now-new Date(r[1].replace(' ','T')+':00+03:00')<7*day).length;
 k.innerHTML=[[c24,'مؤكد آخر 24 ساعة'],[c7,'مؤكد آخر 7 أيام'],[neg,'سلبي آخر 7 أيام'],[pv,'محتمل يحتاج نظرة']].map(x=>'<div class="kpi"><b>'+x[0]+'</b><span>'+x[1]+'</span></div>').join('');
 const s=d.status||{};const lr=s.last_run?new Date(s.last_run).toLocaleString('ar-SA',{timeZone:'Asia/Riyadh'}):'—';
 const N={x:'X',tiktok:'تيك توك',news:'الأخبار',youtube:'يوتيوب',telegram:'تيليجرام',apps:'التطبيقات',reddit:'ريديت',web:'المنتديات',maps:'الخرائط'};const bad=Object.entries(s.sources||{}).filter(x=>x[1]=='fallback'||x[1]=='down').map(x=>N[x[0]]||x[0]);const off=Object.entries(s.sources||{}).filter(x=>x[1]=='nokey').map(x=>N[x[0]]||x[0]);
 st.textContent='آخر فحص: '+lr+' — يعمل من '+(s.runner=='backup'?'التشغيل الاحتياطي':'السيرفر')+(bad.length?' — على البديل أو متوقفة: '+bad.join('، '):' — المصادر المفعّلة تعمل')+(off.length?' — غير مفعّل بعد: '+off.join('، '):'');
 [...new Set(d.rows.map(r=>r[2]))].forEach(p=>{const o=document.createElement('option');o.value=p;o.textContent=P[p]||p;fp_.appendChild(o)});draw();}).data(K);
</script></body></html>`;

/** تشغيل مرة لتفعيل كل الصلاحيات */
function authAll() { MailApp.getRemainingDailyQuota(); SpreadsheetApp.getActiveSpreadsheet().getName(); Logger.log('ok'); }
