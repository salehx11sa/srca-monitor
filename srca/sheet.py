"""الاتصال بجدول Google عبر Apps Script: نسخة مقروءة من البيانات + بريد احتياطي + لوحة + تقييماتك."""
import json

from . import config
from .util import post, get, log

COLS = ["id", "وقت النشر (الرياض)", "المنصة", "الحساب", "الرابط", "الخلاصة", "النوع", "المشاعر", "الارتباط", "السبب",
        "المنطقة", "الأولوية", "التفاعل", "المجموعة", "نُبّه؟", "المصنّف", "النص", "السياق"]


def enabled():
    return bool(config.SHEET_URL and config.SHEET_SECRET)


def call(action, **payload):
    if not enabled():
        raise RuntimeError("NO_SHEET")
    r = post(config.SHEET_URL, retries=2, timeout=60,
             data=json.dumps({"secret": config.SHEET_SECRET, "action": action, **payload}, ensure_ascii=False).encode("utf-8"),
             headers={"Content-Type": "text/plain;charset=utf-8"})
    if r.status_code != 200:
        raise RuntimeError(f"SHEET HTTP{r.status_code}")
    try:
        d = r.json()
    except Exception:
        raise RuntimeError("SHEET bad response: " + r.text[:120])
    if not d.get("ok"):
        raise RuntimeError("SHEET error: " + str(d.get("error")))
    return d


def row(r):
    from .util import riyadh
    m = json.loads(r.get("metrics") or "{}")
    eng = " / ".join(f"{k}:{v}" for k, v in m.items() if v not in (None, "", 0)) if isinstance(m, dict) else ""
    return [r["id"], riyadh(r["created"]), r["platform"], r["author"], r["url"], r.get("summary") or "", r.get("ctype") or "",
            r.get("sentiment") or "", r.get("relevance") or "", r.get("reason") or "", r.get("region") or "",
            r.get("priority") or "", eng, r.get("cluster") or "", "نعم" if r.get("alerted") else "", r.get("classifier") or "",
            (r.get("text") or "")[:1500], _ctx(r)]


def _ctx(r):
    try:
        from .notify import ctx_plain
        return ctx_plain(r)
    except Exception:
        return ""


def append(rows):
    if rows:
        call("append", cols=COLS, rows=[row(r) for r in rows])


def status(**s):
    return call("status", set=s)


def get_status():
    return call("status").get("status", {})


def seen_ids(days=7):
    return call("seen", days=days).get("ids", [])


def feedback():
    return call("feedback").get("items", [])


def email(subject, html_body):
    return call("email", subject=subject, html=html_body)


def dashboard_url():
    return f"{config.SHEET_URL}?k={config.SHEET_SECRET}" if enabled() else ""
