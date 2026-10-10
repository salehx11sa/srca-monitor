"""الملخص اليومي والتقرير الأسبوعي والشهري — بلغة بسيطة."""
import html as _h
from collections import Counter
from datetime import timedelta

from . import notify, sheet, store
from .util import now, riyadh, RIYADH, iso

PRI_ORDER = {"عاجل": 0, "مهم": 1, "اعتيادي": 2, "": 3}


def _period(hours):
    return store.rows("created >= ? AND relevance IN ('مؤكد','محتمل')", (store.since(hours),))


def _health_line():
    bad = [r["source"] for r in store.db().execute("SELECT * FROM source_state WHERE mode IN ('fallback','down')")]
    off = [r["source"] for r in store.db().execute("SELECT * FROM source_state WHERE mode='nokey'")]
    last = store.last_runs(1)
    t = riyadh(last[0]["finished"] or last[0]["started"]) if last else "—"
    names = {"x": "X", "tiktok": "تيك توك", "news": "الأخبار", "youtube": "يوتيوب", "telegram": "تيليجرام",
             "apps": "التطبيقات", "reddit": "ريديت", "web": "المنتديات", "maps": "الخرائط"}
    s = f"النظام شغّال ✔ — آخر فحص {t[-5:]}"
    if bad:
        s += " — يعمل بالبديل أو متوقف: " + "، ".join(names.get(b, b) for b in bad)
    if off:
        s += " — غير مفعّل بعد: " + "، ".join(names.get(b, b) for b in off)
    return s


def _stats(rows):
    c = Counter(r["relevance"] for r in rows)
    s = Counter(r["sentiment"] for r in rows if r["relevance"] == "مؤكد")
    p = Counter(notify.pretty_platform(r["platform"]) for r in rows)
    return c, s, p


def _table(rows):
    tr = "".join(
        f"<tr><td>{riyadh(r['created'])}</td><td>{_h.escape(notify.pretty_platform(r['platform']))}</td>"
        f"<td>{_h.escape(r['priority'] or '')}</td><td>{_h.escape(r['relevance'])}</td><td>{_h.escape(r['ctype'] or '')}</td>"
        f"<td>{_h.escape(r['sentiment'] or '')}</td><td>{_h.escape(r['summary'] or r['text'][:140])}</td>"
        f"<td><a href='{_h.escape(r['url'])}'>افتح</a></td></tr>" for r in rows)
    return ("<table border='1' cellpadding='6' style='border-collapse:collapse;font-size:13px'>"
            "<tr style='background:#101332;color:#fff'><th>الوقت</th><th>المنصة</th><th>الأولوية</th><th>الارتباط</th>"
            "<th>النوع</th><th>المشاعر</th><th>الخلاصة</th><th>الرابط</th></tr>" + tr + "</table>")


def report(kind="daily"):
    hours = {"daily": 24, "weekly": 24 * 7, "monthly": 24 * 30}[kind]
    label = {"daily": "الملخص اليومي", "weekly": "التقرير الأسبوعي", "monthly": "التقرير الشهري"}[kind]
    rows = sorted(_period(hours), key=lambda r: (PRI_ORDER.get(r["priority"] or "", 3), r["created"]))
    rows_seen, clusters = [], set()
    for r in rows:  # قصة واحدة = سطر واحد
        k = r["cluster"] or r["id"]
        if k not in clusters:
            clusters.add(k); rows_seen.append(r)
    c, s, p = _stats(rows_seen)
    date = now().astimezone(RIYADH).strftime("%Y-%m-%d")
    head = (f"خلال {'24 ساعة' if kind == 'daily' else 'أسبوع' if kind == 'weekly' else 'شهر'}: "
            f"{c.get('مؤكد', 0)} منشور عن الهيئة، و{c.get('محتمل', 0)} محتمل يحتاج نظرة.")
    if c.get("مؤكد"):
        head += f"\nالمشاعر: إيجابي {s.get('إيجابي', 0)}، سلبي {s.get('سلبي', 0)}، محايد {s.get('محايد', 0) + s.get('مختلط', 0)}."
    if p:
        head += "\nالمصادر: " + "، ".join(f"{k} {v}" for k, v in p.most_common())
    if kind != "daily":
        prev = store.rows("created >= ? AND created < ? AND relevance='مؤكد'",
                          (iso(now() - timedelta(hours=2 * hours)), store.since(hours)))
        head += f"\nمقارنة بالفترة السابقة: {c.get('مؤكد', 0)} مقابل {len(prev)}."
    top = [r for r in rows_seen if r["relevance"] == "مؤكد" and r["priority"] in ("عاجل", "مهم")][:3] or \
        [r for r in rows_seen if r["relevance"] == "مؤكد"][:3]
    short = head + ("\n\nالأبرز:\n" + "\n".join(notify.line(r) for r in top) if top else "\n\nلا شيء لافت.") + \
        "\n\n" + _health_line()
    title = f"{label} لرصد الهلال — {date}"
    notify.send(title, short, notify.NORMAL, sheet.dashboard_url() or None, "افتح اللوحة")
    if sheet.enabled() and rows_seen:  # النسخة الكاملة بالبريد
        try:
            sheet.email(title, f"<div dir='rtl' style='font-family:Tahoma,Arial'><p>{head.replace(chr(10), '<br>')}</p>"
                               f"{_table(rows_seen)}<p>{_health_line()}</p></div>")
        except Exception:
            pass
    return short
