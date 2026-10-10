"""التنبيهات: Pushover أساسي ← تيليجرام ← البريد. بلا تكرار أبدًا (لا أولوية 2)."""
import html as _h

from . import config, sheet, store
from .util import post, log

URGENT, NORMAL, QUIET = 1, 0, -1


def _pushover(title, msg, pri, url=None, url_title=None):
    if not (config.PUSHOVER_TOKEN and config.PUSHOVER_USER):
        raise RuntimeError("NO_PUSHOVER")
    data = {"token": config.PUSHOVER_TOKEN, "user": config.PUSHOVER_USER, "title": title[:250], "message": msg[:1024],
            "priority": max(-1, min(1, pri)), "html": 1}
    if pri == URGENT:
        data["sound"] = "siren"
    if url:
        data["url"], data["url_title"] = url[:512], (url_title or "افتح")[:100]
    r = post("https://api.pushover.net/1/messages.json", data=data, retries=2)
    if r.status_code != 200:
        raise RuntimeError(f"PUSHOVER HTTP{r.status_code} {r.text[:120]}")


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


def line(r):
    pr = r.get("priority") or "اعتيادي"
    head = f"<b>{pr}</b> — {r.get('ctype') or ''} — {pretty_platform(r['platform'])}"
    return f"{head}\n{_h.escape(r.get('summary') or r.get('text', '')[:120])} <a href=\"{_h.escape(r['url'])}\">افتح</a>"
