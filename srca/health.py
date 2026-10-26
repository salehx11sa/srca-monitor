"""منبّه الأعطال: يقرأ نتيجة كل دورة، وإذا تعطل جزء «بصمت» يرسل لصالح رسالة واحدة بصوت، ورسالة هادئة لما يرجع.
بلا تكرار: كل عطل = رسالة عند بدايته + رسالة عند رجوعه فقط. الرسائل لصالح وحده (لا تروح للزملاء).

ما يغطيه (إضافة على Healthchecks اللي ينبّه إذا وقف التابلت كله):
  - X يشتغل ناقص: حد الطلبات (429)، أو تجاوز الوقت، أو على البديل، أو متوقف.
  - X يرد بلا أي تغريدة لساعات (غير طبيعي).
  - الجدول ما يتحدث.
  - الملخص اليومي (إشارة «النظام شغّال» اليومية) فات موعده لأي سبب ← يُرسل في أول دورة بعده.
"""
from collections import Counter

from . import notify, store
from .util import now, iso, parse_dt, RIYADH

WINDOW = 6            # آخر 6 دورات (3 ساعات)
X_BAD_MIN = 4         # 4 دورات ناقصة من آخر 6 = عطل
X_EMPTY_MIN = 6       # 6 دورات متتالية بلا أي تغريدة = عطل
X_OK_BACK = 3         # 3 دورات سليمة متتالية = رجع
SHEET_BAD_MIN = 3     # 3 دورات متتالية والجدول ما يتحدث = عطل
SHEET_OK_BACK = 3     # 3 دورات متتالية سليمة = رجع
BAD = ("429", "time", "fallback", "down")

WHY = {
    "429": "منصة X توقّف حساب الرصد مؤقتًا لأنه يطلب كثير، فصار يجمع جزء من التغريدات كل دورة، وممكن يتأخر عليك شي أو يفوتك.",
    "time": "جمع X صار ياخذ وقت أطول من المسموح، فجزء من التغريدات ما ينجمع.",
    "fallback": "حساب الرصد في X ما يشتغل (غالبًا انتهت جلسة الدخول)، والرصد ماشي على بحث بديل أضعف بكثير.",
    "down": "X متوقف تمامًا هو والبحث البديل.",
    "empty": "X ما جاب ولا تغريدة من 3 ساعات، وهذا غير طبيعي.",
}
TODO = {
    "429": "غالبًا يرجع لحاله خلال ساعات.",
    "time": "غالبًا ضغط مؤقت ويرجع لحاله.",
    "fallback": "يحتاج تحديث مفتاح حساب الرصد في X (الخطوات في ملف «إصلاح X التابلت»).",
    "down": "يحتاج تحديث مفتاح حساب الرصد في X (الخطوات في ملف «إصلاح X التابلت»).",
    "empty": "ممكن جلسة حساب الرصد فيها مشكلة.",
}
SHORT = {"429": "حد الطلبات", "time": "تجاوز الوقت", "fallback": "على البديل", "down": "متوقف", "empty": "بلا نتائج",
         "ok": "سليم"}


def _t(s):
    """وقت مفهوم: «5:35 ص» لليوم، و«أمس 11:20 م» أو «24/10 11:20 م» لما قبله."""
    d = parse_dt(s) if isinstance(s, str) else s
    if not d:
        return ""
    d = d.astimezone(RIYADH)
    h = d.hour % 12 or 12
    out = f"{h}:{d.minute:02d} {'ص' if d.hour < 12 else 'م'}"
    days = (now().astimezone(RIYADH).date() - d.date()).days
    return out if days == 0 else f"أمس {out}" if days == 1 else f"{d:%d/%m} {out}"


def x_state(src):
    """حالة X في هذه الدورة: ok | empty | 429 | time | fallback | down — أو None (لا يُحكم عليها)."""
    if not src:
        return None
    how = src.get("how") or ""
    if how.startswith("skip"):
        return None
    if how.startswith("fallback"):
        return "fallback"
    if how.startswith(("down", "nokey")):
        return "down"
    if not how.startswith("primary"):
        return None
    if "PARTIAL_429" in how:
        return "429"
    if "PARTIAL_TIME" in how:
        return "time"
    return "ok" if (src.get("n") or 0) > 0 else "empty"


def _send(title, msg, loud):
    # بصوت عادي (أولوية 0) عند العطل، وهادئ عند الرجوع — ولصالح وحده
    notify.send(title, msg, notify.NORMAL if loud else notify.QUIET, team=False)


def check(detail, sheet_ok=None):
    """يُستدعى بعد كل دورة للتابلت. يرجع قائمة بما أُرسل (للسجل والاختبار)."""
    st = store.kv_get("health") or {}
    sent = []
    t_now = iso(now())

    # ---- X ----
    s = x_state((detail.get("sources") or {}).get("x"))
    if s:
        hist = (st.get("x_hist") or []) + [[t_now, s]]
        hist = hist[-12:]
        st["x_hist"] = hist
        last = [h[1] for h in hist[-WINDOW:]]
        alert = st.get("x_alert")
        if not alert:
            bad = [h for h in hist[-WINDOW:] if h[1] in BAD]
            empty_run = len(last) >= X_EMPTY_MIN and all(x == "empty" for x in last[-X_EMPTY_MIN:])
            if len(bad) >= X_BAD_MIN or empty_run:
                why = "empty" if empty_run else Counter(h[1] for h in bad).most_common(1)[0][0]
                since = (hist[-X_EMPTY_MIN][0] if empty_run else bad[0][0])
                _send("⚠️ عطل في الرصد",
                      f"{WHY[why]}\nبدأ تقريبًا الساعة {_t(since)}.\n{TODO[why]} وبيوصلك تنبيه أول ما يرجع طبيعي.", True)
                st["x_alert"] = {"why": why, "since": since, "at": t_now}
                sent.append("x_alert:" + why)
        elif len(last) >= X_OK_BACK and all(x == "ok" for x in last[-X_OK_BACK:]):
            back = hist[-X_OK_BACK][0]
            _send("✅ رجع الرصد طبيعي",
                  f"X رجع يجمع كامل من الساعة {_t(back)} (كان {SHORT.get(alert.get('why'), 'ناقص')} "
                  f"من {_t(alert.get('since'))}).", False)
            st["x_alert"] = None
            sent.append("x_back")

    # ---- الجدول ----
    if sheet_ok is not None:
        if sheet_ok:
            st["sheet_bad"], st["sheet_since"] = 0, None
            st["sheet_ok_n"] = (st.get("sheet_ok_n") or 0) + 1
            if st.get("sheet_alert") and st["sheet_ok_n"] >= SHEET_OK_BACK:
                _send("✅ رجع الرصد طبيعي", "الجدول واللوحة رجعوا يتحدثون.", False)
                sent.append("sheet_back")
                st["sheet_alert"] = False
        else:
            st["sheet_ok_n"] = 0
            st["sheet_bad"] = (st.get("sheet_bad") or 0) + 1
            st["sheet_since"] = st.get("sheet_since") or t_now
            if st["sheet_bad"] >= SHEET_BAD_MIN and not st.get("sheet_alert"):
                _send("⚠️ عطل في الرصد",
                      f"الجدول ما يتحدث من الساعة {_t(st['sheet_since'])}.\n"
                      "الرصد والتنبيهات شغّالة عادي، بس الجدول واللوحة متأخرة.\n"
                      "لو جاتك بعدها رسالة «استلم الرصد الاحتياطي» فسببها الجدول، والتابلت شغّال.",
                      True)
                st["sheet_alert"] = True
                sent.append("sheet_alert")

    store.kv_set("health", st)
    return sent


def note():
    """سطر قصير للملخص اليومي إذا فيه عطل قائم (فارغ إذا كل شي سليم)."""
    st = store.kv_get("health") or {}
    out = []
    a = st.get("x_alert")
    if a:
        out.append(f"X {SHORT.get(a.get('why'), 'ناقص')} من {_t(a.get('since'))}")
    if st.get("sheet_alert"):
        out.append(f"الجدول ما يتحدث من {_t(st.get('sheet_since'))}")
    return ("⚠️ " + "، ".join(out)) if out else ""


def summary(detail, status, sheet_ok=None):
    """ملخص الدورة بسطر واحد يُرسل مع نبضة Healthchecks — يظهر في سجل الفحص هناك (تشخيص بدون التابلت)."""
    names = {"x": "X", "tiktok": "تيك توك", "news": "الأخبار", "youtube": "يوتيوب", "telegram": "تيليجرام",
             "apps": "التطبيقات", "reddit": "ريديت", "web": "المنتديات", "maps": "الخرائط"}
    parts = []
    for k, v in (detail.get("sources") or {}).items():
        how = (v.get("how") or "").split(" (")[0][:70]
        parts.append(f"{names.get(k, k)}: {how} n={v.get('n', 0)}")
    tail = (f"الحالة {status} | جديد {detail.get('new', 0)} | مرشح {detail.get('candidates', 0)} | "
            f"مرتبط {detail.get('relevant', 0)} | تنبيهات مهمة {detail.get('urgent', 0)} اعتيادي {detail.get('grouped', 0)}"
            f" | التصنيف {','.join(detail.get('classifier') or []) or '-'}")
    if detail.get("deferred"):
        tail += f" | مؤجل {detail['deferred']}"
    if sheet_ok is not None:
        tail += " | الجدول " + ("✔" if sheet_ok else "✖")
    n = note()
    return ("\n".join(parts) + "\n" + tail + (("\n" + n) if n else ""))[:9000]


def daily_guard():
    """الملخص اليومي = إشارتك اليومية أن النظام شغّال. إذا فات موعده (8:00) لأي سبب، يُرسل في أول دورة بعد 8:15.
    يرجع True إذا أرسل الآن."""
    t = now().astimezone(RIYADH)
    today = t.strftime("%Y-%m-%d")
    last = store.kv_get("daily_sent")
    if last is None:  # أول تشغيل بهذه النسخة: بعد 8:00 نعتبر ملخص اليوم وصل (لا نكرره)، وقبلها ننتظره
        from datetime import timedelta
        store.kv_set("daily_sent", today if t.hour >= 8 else (t - timedelta(days=1)).strftime("%Y-%m-%d"))
        return False
    if last == today or (t.hour, t.minute) < (8, 15):
        return False
    from . import reports
    reports.report("daily")
    store.kv_set("daily_sent", today)
    return True
