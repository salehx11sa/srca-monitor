"""X: يدخل بكوكيز حساب الرصد، يحقن أداة الجمع، ويرجع المنشورات بالشكل الموحد. قراءة فقط."""
import time
from pathlib import Path

from .. import config
from ..util import item, log, parse_dt
from .browser import chrome

JS = (Path(__file__).parent / "x_collector.js").read_text(encoding="utf-8")


class SourceDown(Exception):
    pass


def _cookies(token):
    ck = [{"name": "auth_token", "value": token, "domain": ".x.com", "path": "/", "secure": True,
           "httpOnly": True, "sameSite": "Lax"}]
    if config.X_CT0 and token == config.X_AUTH_TOKEN:
        ck.append({"name": "ct0", "value": config.X_CT0, "domain": ".x.com", "path": "/", "secure": True,
                   "httpOnly": False, "sameSite": "Lax"})
    return ck


def _to_item(t):
    url = f"https://x.com/{t.get('sn')}/status/{t['id']}"
    return item("x", t["id"], url, t.get("tx", ""), parse_dt(t.get("t")), t.get("sn", ""), t.get("nm", ""),
                quoted=t.get("qt", ""), location=t.get("loc", ""), metrics=t.get("m", {}), media=t.get("md", ""),
                query="".join(t.get("qs", [])), reply_to=t.get("rp", ""), reply_id=t.get("rpId", ""),
                retweet=t.get("rt", False), verified=t.get("vt", ""), followers=t.get("fo"))


def _run_with(token, cut_unix, keys=None):
    with chrome(_cookies(token)) as ctx:
        pg = ctx.new_page()
        pg.goto("https://x.com/home", wait_until="domcontentloaded", timeout=60000)
        # ننتظر استقرار الصفحة: X أحيانًا يحوّل بعد التحميل (تسجيل دخول/تحقق من جهاز جديد)
        last, stable = pg.url, 0
        for _ in range(20):
            time.sleep(1.5)
            stable = stable + 1 if pg.url == last else 0
            last = pg.url
            if stable >= 4:
                break
        if "/home" not in pg.url:
            raise SourceDown("LOGIN_REQUIRED " + pg.url.split("?")[0])
        for attempt in range(3):
            try:
                pg.evaluate(JS)
                break
            except Exception as e:
                if "context was destroyed" not in str(e) and "navigation" not in str(e).lower():
                    raise
                pg.wait_for_load_state("domcontentloaded", timeout=30000)
                time.sleep(4)
                if "/home" not in pg.url:
                    raise SourceDown("LOGIN_REQUIRED " + pg.url.split("?")[0])
        else:
            raise SourceDown("X_PAGE_UNSTABLE " + pg.url.split("?")[0])
        opts = {"pagesCap": config.X_PAGES_CAP}
        if keys:
            opts["keys"] = keys
        res = None
        for attempt in range(3):
            res = pg.evaluate("([c,o])=>SRCA.run(c,o)", [cut_unix, opts])
            if res.get("stopped") != "429":
                break
            wait = int(res.get("reset") or 0) - time.time() + 5
            if wait > 720:
                break
            log.info("X: حد الطلبات، انتظار %ss", int(max(wait, 30)))
            time.sleep(max(wait, 30))
        qlog = pg.evaluate("SRCA.log")
        tweets = pg.evaluate("SRCA.all()")
        rl = pg.evaluate("SRCA.lastRL")
    bad = sum(1 for x in qlog if str(x.get("status", "")).startswith(("TIMEOUT", "HTTP")))
    status = "DONE" if res.get("stopped") == "DONE" else "PARTIAL_429"
    if qlog and bad > len(qlog) / 2:
        status = "FAILED_QUERIES"
    return [_to_item(t) for t in tweets if t.get("id")], {"status": status, "queries": qlog, "rl": rl}


def collect(cut_dt, keys=None):
    tokens = [t for t in (config.X_AUTH_TOKEN, config.X_AUTH_TOKEN_2) if t]
    if not tokens:
        raise SourceDown("NO_ACCOUNT")
    err = None
    for i, tok in enumerate(tokens):
        try:
            items, st = _run_with(tok, int(cut_dt.timestamp()), keys)
            st["account"] = "primary" if i == 0 else "backup"
            if st["status"] == "FAILED_QUERIES":
                err = SourceDown("FAILED_QUERIES")
                continue
            return items, st
        except SourceDown as e:
            err = e
            log.warning("X: الحساب %s متعطل: %s", i + 1, e)
    raise err or SourceDown("UNKNOWN")


def fallback(cut_dt):
    """بديل X: بحث الويب site:x.com (أبطأ وأقل، لكنه لا يتوقف)."""
    from . import websearch
    qs = ['site:x.com "الهلال الأحمر السعودي"', 'site:x.com "هيئة الهلال الأحمر"', 'site:x.com @mediasrca']
    return [i for i in websearch.search(qs, platform="x", freshness=websearch.DAY) if "/status/" in i["url"]]
