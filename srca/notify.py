"""التنبيهات: Pushover أساسي ← تيليجرام ← البريد. بلا تكرار أبدًا (لا أولوية 2)."""
import html as _h
import json
import re

from . import config, sheet, store
from .util import post, log

# عاجل = أولوية 1 بصفارة، مهم = أولوية 1 بالصوت العادي (منفرد)، اعتيادي = 0، هادئ = -1
URGENT, IMPORTANT, NORMAL, QUIET = 2, 1, 0, -1


def _fit(msg, n=1024):
    """يقص الرسالة الطويلة عند حد منشور كامل (لا يقطع رابطًا في نصفه)."""
    if len(msg) <= n:
        return msg
    cut = msg.rfind("\n\n", 0, n - 40)
    return (msg[:cut] if cut > 0 else msg[:n - 40].rsplit("<", 1)[0]) + "\n\n…والباقي في اللوحة."


def _pushover(title, msg, pri, url=None, url_title=None):
    if not (config.PUSHOVER_TOKEN and config.PUSHOVER_USER):
        raise RuntimeError("NO_PUSHOVER")
    data = {"token": config.PUSHOVER_TOKEN, "user": config.PUSHOVER_USER, "title": title[:250], "message": _fit(msg),
            "priority": max(-1, min(1, pri)), "html": 1}
    if pri == URGENT:
        data["sound"] = "siren"
    if url:
        data["url"], data["url_title"] = url[:512], (url_title or "افتح")[:100]
    r = post("https://api.pushover.net/1/messages.json", data=data, retries=2)
    if r.status_code != 200:
        raise RuntimeError(f"PUSHOVER HTTP{r.status_code} {r.text[:120]}")
    if pri == QUIET:  # الرسائل التقنية لصالح وحده
        return
    for key in config.PUSHOVER_TEAM:  # الزملاء: فشل أحدهم لا يوقف شيئًا ولا يحوّل القناة
        if key == config.PUSHOVER_USER:
            continue
        try:
            rt = post("https://api.pushover.net/1/messages.json", data={**data, "user": key}, retries=2)
            if rt.status_code != 200:
                log.warning("تعذر تنبيه زميل (%s…): HTTP%s", key[:5], rt.status_code)
        except Exception as e:
            log.warning("تعذر تنبيه زميل (%s…): %s", key[:5], str(e)[:80])


def _telegram(title, msg, pri, url=None, url_title=None):
    if not (config.TELEGRAM_BOT and config.TELEGRAM_CHAT):
        raise RuntimeError("NO_TELEGRAM")
    text = f"<b>{_h.escape(title)}</b>\n{msg}" + (f'\n<a href="{_h.escape(url)}">{_h.escape(url_title or "افتح")}</a>' if url else "")
    r = post(f"https://api.telegram.org/bot{config.TELEGRAM_BOT}/sendMessage", retries=2,
             json={"chat_id": config.TELEGRAM_CHAT, "text": text[:4000], "parse_mode": "HTML",
                   "disable_notification": pri == QUIET, "disable_web_page_preview": True})
    if r.status_code != 200:
        raise RuntimeError(f"TELEGRAM HTTP{r.status_code}")


def _email(title, msg, pri, url=None, url_title=None):
    body = f"<div dir='rtl' style='font-family:Tahoma,Arial;font-size:15px;line-height:1.8'>{msg.replace(chr(10), '<br>')}"
    if url:
        body += f"<p><a href='{_h.escape(url)}'>{_h.escape(url_title or 'افتح')}</a></p>"
    sheet.email(title, body + "</div>")


CHAIN = [("Pushover", _pushover), ("تيليجرام", _telegram), ("البريد", _email)]


def send(title, msg, pri=NORMAL, url=None, url_title=None):
    """يرسل عبر أول قناة تعمل. إذا تعطلت الأساسية يُبلَّغ مرة واحدة عبر البديل."""
    errors = []
    for i, (name, fn) in enumerate(CHAIN):
        try:
            fn(title, msg, pri, url, url_title)
            prev = store.kv_get("notify_channel", "Pushover")
            if prev != name:
                store.kv_set("notify_channel", name)
                if i > 0:  # تحوّل لبديل: رسالة واحدة توضح
                    try:
                        fn("تنبيه عن الرصد", f"قناة {CHAIN[0][0]} لا تعمل الآن، فالتنبيهات تصلك هنا مؤقتًا.", QUIET)
                    except Exception:
                        pass
            return name
        except Exception as e:
            errors.append(f"{name}: {str(e)[:80]}")
    log.error("كل قنوات التنبيه فشلت: %s", errors)
    return None


def pretty_platform(p):
    return {"x": "X", "tiktok": "تيك توك", "news": "الأخبار", "youtube": "يوتيوب", "telegram": "تيليجرام",
            "app": "تقييم تطبيق", "reddit": "ريديت", "web": "موقع/منتدى", "maps": "خرائط قوقل", "linkedin": "لينكدإن"}.get(p, p)


def extra(r):
    ex = r.get("extra") or {}
    if isinstance(ex, str):
        try:
            ex = json.loads(ex)
        except Exception:
            ex = {}
    return ex if isinstance(ex, dict) else {}


_MENTIONS = re.compile(r"^(?:\s*@\w+)+\s*")


def _snip(native_id, raw, n=90):
    """نص مختصر للتغريدة الأصلية: ملخص الذكاء إن وُجد (يحذف التفاصيل الحساسة)، وإلا النص بلا المنشنات."""
    txt = ""
    try:
        got = store.rows("id=?", ("x:" + native_id,))
        if got and got[0].get("summary"):
            txt = got[0]["summary"]
    except Exception:
        pass
    if not txt:
        txt = _MENTIONS.sub("", re.sub(r"https?://\S+", "", raw or ""))
    txt = " ".join(txt.split())
    return (txt[:n] + "…") if len(txt) > n else txt


def context(r):
    """سطور السياق لأي رد: اللي انكتب عليه الرد، وأصل النقاش إذا كان الرد على رد."""
    ex, out = extra(r), []
    if r.get("platform") != "x" or not ex.get("reply_id"):
        return out
    who = ex.get("parent_author") or ex.get("reply_to") or ""
    out.append({"k": "↩︎ ردًا على", "who": who, "url": f"https://x.com/{who or 'i'}/status/{ex['reply_id']}",
                "txt": _snip(ex["reply_id"], ex.get("parent_text")), "root": False})
    if ex.get("root_id") and ex["root_id"] != ex["reply_id"]:
        who = ex.get("root_author") or ""
        out.append({"k": "🧵 أصل النقاش", "who": who, "url": f"https://x.com/{who or 'i'}/status/{ex['root_id']}",
                    "txt": _snip(ex["root_id"], ex.get("root_text")), "root": True})
    return out


def ctx_html(c):
    return f"{c['k']} @{_h.escape(c['who'])}" + (f": {_h.escape(c['txt'])}" if c["txt"] else "") + \
        f" <a href=\"{_h.escape(c['url'])}\">افتح</a>"


def ctx_plain(r):
    return "\n".join(f"{c['k']} @{c['who']}: {c['txt']} — {c['url']}" for c in context(r))


def line(r, ctx=True):
    pr = r.get("priority") or "اعتيادي"
    head = f"<b>{pr}</b> — {r.get('ctype') or ''} — {pretty_platform(r['platform'])}"
    out = f"{head}\n{_h.escape(r.get('summary') or r.get('text', '')[:120])} <a href=\"{_h.escape(r['url'])}\">افتح</a>"
    if ctx:  # الرد يجي ومعه التغريدة الأصلية وأصل النقاش
        for c in context(r):
            out += "\n" + ctx_html(c)
    return out


def conv_key(r):
    """مفتاح النقاش: أصل النقاش للرد، أو المنشور نفسه إذا كان بداية نقاش."""
    ex = extra(r)
    if r.get("platform") != "x":
        return ""
    return ex.get("root_id") or ex.get("reply_id") or r["id"].split(":", 1)[-1]


def group_body(g, key):
    """رسالة واحدة لعدة منشورات من نفس النقاش: كل منشور بسطره، والسياق مرة واحدة تحت."""
    has_root = any(r["id"] == "x:" + key for r in g)
    g = sorted(g, key=lambda r: (r["id"] != "x:" + key, r.get("created") or ""))
    body = "\n\n".join(line(r, ctx=False) for r in g[:5])
    if len(g) > 5:
        body += f"\n\nو{len(g) - 5} غيرها في اللوحة."
    if not has_root:
        cs = [c for r in g for c in context(r)]
        roots = [c for c in cs if c["root"]]
        pick = roots[:1] or cs[:1]
        if pick:
            body += "\n\n" + ctx_html(pick[0])
    return body
