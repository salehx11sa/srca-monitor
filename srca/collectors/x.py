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


def _search(pg, raw):
    """يفتح صفحة البحث (الأحدث) مباشرة ويلتقط رد SearchTimeline. يرجع (status, json, reset)."""
    from urllib.parse import quote
    url = "https://x.com/search?q=" + quote(raw) + "&src=typed_query&f=live"
    try:
        with pg.expect_response(lambda r: "SearchTimeline" in r.url and r.request.method == "GET", timeout=30000) as info:
            pg.goto(url, wait_until="domcontentloaded", timeout=60000)
        r = info.value
        j = None
        try:
            j = r.json()
        except Exception:
            pass
        return r.status, j, r.headers.get("x-rate-limit-reset"), r.headers.get("x-rate-limit-remaining")
    except Exception as e:
        if "/search" not in pg.url:
            raise SourceDown("LOGIN_REQUIRED " + pg.url.split("?")[0])
        return "TIMEOUT", None, None, None


def _run_with(token, cut_unix, keys=None):
    """كل استعلام يُفتح كصفحة مستقلة (أثبت من التنقل الداخلي الذي قد يعيد تحميل الصفحة)."""
    db, qlog, rl, stopped, reset = {}, [], None, "DONE", None
    with chrome(_cookies(token)) as ctx:
        ctx.add_init_script(JS)  # أداة التحليل متاحة في كل صفحة
        pg = ctx.new_page()
        pg.goto("https://x.com/home", wait_until="domcontentloaded", timeout=60000)
        time.sleep(5)
        if "/home" not in pg.url:
            raise SourceDown("LOGIN_REQUIRED " + pg.url.split("?")[0])
        qs = pg.evaluate("SRCA.QS")
        queue = [{"k": k, "until": None, "pages": 0, "got": 0, "tries": 0} for k in (keys or list(qs))]
        waited = 0
        while queue:
            it = queue[0]
            raw = qs[it["k"]] + f" since_time:{cut_unix}" + (f" until_time:{it['until']}" if it["until"] else "")
            status, j, rs, rem = _search(pg, raw)
            if rem is not None:
                rl = f"{rem}/{rs}"
            if status == 429:
                wait = int(rs or 0) - time.time() + 5
                if wait > 720 or waited >= 2:
                    stopped, reset = "429", rs
                    break
                waited += 1
                log.info("X: حد الطلبات، انتظار %ss", int(max(wait, 30)))
                time.sleep(max(wait, 30))
                continue
            if status != 200 or not j:
                it["tries"] += 1
                if it["tries"] >= 3:
                    qlog.append({"k": it["k"], "status": "TIMEOUT" if status == "TIMEOUT" else f"HTTP{status}", "pages": it["pages"]})
                    queue.pop(0)
                continue
            it["pages"] += 1
            tw = pg.evaluate("j => SRCA.parse(j)", j)
            for t in tw:
                if parse_dt(t["t"]).timestamp() < cut_unix:
                    continue
                if t["id"] not in db:
                    t["qs"] = [it["k"]]
                    db[t["id"]] = t
                    it["got"] += 1
                elif it["k"] not in db[t["id"]]["qs"]:
                    db[t["id"]]["qs"].append(it["k"])
            oldest = int(min(parse_dt(t["t"]).timestamp() for t in tw)) if tw else 0
            done = not tw or oldest <= cut_unix or it["pages"] >= config.X_PAGES_CAP or (it["until"] and oldest >= it["until"])
            if done:
                qlog.append({"k": it["k"], "pages": it["pages"], "got": it["got"],
                             "status": "end" if not tw else "cut" if oldest <= cut_unix else "CAP"})
                queue.pop(0)
            else:
                it["until"] = oldest
    bad = sum(1 for x in qlog if str(x.get("status", "")).startswith(("TIMEOUT", "HTTP")))
    status = "DONE" if stopped == "DONE" else "PARTIAL_429"
    if qlog and bad > len(qlog) / 2:
        status = "FAILED_QUERIES"
    return [_to_item(t) for t in db.values() if t.get("id")], {"status": status, "queries": qlog, "rl": rl}


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
