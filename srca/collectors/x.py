"""X: يدخل بكوكيز حساب الرصد، يحقن أداة الجمع، ويرجع المنشورات بالشكل الموحد. قراءة فقط."""
import json, time
from pathlib import Path

from .. import config
from ..util import item, log, parse_dt
from .browser import chrome

BUDGET = 12 * 60  # أقصى وقت لجمع X في التشغيلة الواحدة (ثانية)
PARENT_CAP = 6     # أقصى عدد تغريدات أصلية تُجلب لسياق الردود في التشغيلة الواحدة
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
                retweet=t.get("rt", False), verified=t.get("vt", ""), followers=t.get("fo"),
                parent_author=(t.get("pp") or {}).get("sn", ""), parent_text=(t.get("pp") or {}).get("tx", ""),
                root_id=(t.get("pr") or {}).get("id", ""), root_author=(t.get("pr") or {}).get("sn", ""),
                root_text=(t.get("pr") or {}).get("tx", ""))


def _parents(pg, db):
    """سياق الردود: يجلب التغريدة اللي جاء عليها الرد + أصل النقاش (أول تغريدة في السلسلة)،
    ليصلك تنبيه الرد ومعه «ردًا على» و«أصل النقاش». الأصل الجديد يدخل الرصد كمنشور عادي
    (فإن كان يخص الهيئة ولم يُنبَّه عنه، يصلك تنبيهه هو أيضًا)."""
    from .. import store
    from ..classify import rules
    want = {}
    for t in list(db.values()):
        pid = t.get("rpId")
        if not pid or pid in want:
            continue
        ok, _ = rules.prefilter({"text": t.get("tx", ""), "quoted": t.get("qt", ""), "author": t.get("sn", "")})
        if ok:
            want[pid] = t.get("rp", "")
    if not want:
        return {}
    out = {}
    try:  # المحفوظ سابقًا لا يُجلب مرة ثانية
        for r in store.rows("id IN (%s)" % ",".join("?" * len(want)), tuple("x:" + p for p in want)):
            try:
                ex = json.loads(r.get("extra") or "{}")
            except Exception:
                ex = {}
            root = None
            if ex.get("root_id"):
                root = {"id": ex["root_id"], "sn": ex.get("root_author", ""), "tx": ex.get("root_text", "")}
            out[r["id"][2:]] = {"sn": r["author"], "tx": r["text"], "root": root, "known": True}
    except Exception as e:
        log.info("X: تعذر قراءة الأصول المحفوظة: %s", str(e)[:80])
    fetched = 0
    for pid, sn in want.items():
        if pid in out:
            continue
        if pid in db and not db[pid].get("rpId"):  # الأصل نفسه موجود في نتائج البحث وهو بداية النقاش
            out[pid] = db[pid]
            continue
        if fetched >= PARENT_CAP:
            continue
        fetched += 1
        try:
            with pg.expect_response(lambda r: "TweetDetail" in r.url and r.request.method == "GET", timeout=25000) as info:
                pg.goto(f"https://x.com/{sn or 'i'}/status/{pid}", wait_until="domcontentloaded", timeout=45000)
            tw = pg.evaluate("j => SRCA.parse(j)", info.value.json())
            focal = next((t for t in tw if t.get("id") == pid), None)
            if not focal:
                continue
            focal["qs"] = ["parent"]
            if focal.get("rpId"):  # التغريدة نفسها رد ← أصل النقاش هو أول تغريدة بلا «رد على»
                root = next((t for t in tw if not t.get("rpId") and t.get("id") != pid), None)
                if root:
                    root["qs"] = ["parent"]
                    focal["root"] = root
            out[pid] = focal
        except Exception as e:
            log.info("X: تعذر جلب أصل الرد %s: %s", pid, str(e)[:80])
    return out


def _attach_parents(db, parents):
    add = []
    for t in list(db.values()):
        p = parents.get(t.get("rpId"))
        if not p:
            continue
        t["pp"] = {"sn": p.get("sn", ""), "tx": (p.get("tx") or "")[:500]}
        root = p.get("root")
        if root and root.get("id") and root["id"] != t.get("id"):
            t["pr"] = {"id": root["id"], "sn": root.get("sn", ""), "tx": (root.get("tx") or "")[:500]}
            if root.get("t"):
                add.append(root)
        if not p.get("known") and p.get("id"):
            add.append(p)
    for p in add:  # الأصول الجديدة تدخل الرصد كمنشورات عادية
        if p["id"] not in db:
            q = {k: v for k, v in p.items() if k not in ("root", "known")}
            if p.get("root") and p["root"].get("id"):
                q["pr"] = {"id": p["root"]["id"], "sn": p["root"].get("sn", ""), "tx": (p["root"].get("tx") or "")[:500]}
            db[p["id"]] = q


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
        waited, t0 = 0, time.time()
        while queue:
            if time.time() - t0 > BUDGET:
                log.warning("X: انتهت الميزانية الزمنية، متبقي %s استعلام", len(queue))
                stopped = "BUDGET"
                break
            it = queue[0]
            raw = qs[it["k"]] + f" since_time:{cut_unix}" + (f" until_time:{it['until']}" if it["until"] else "")
            status, j, rs, rem = _search(pg, raw)
            if rem is not None:
                rl = f"{rem}/{rs}"
            if status == 429:
                wait = int(rs or 0) - time.time() + 5
                if wait > 300 or waited >= 1:
                    stopped, reset = "429", rs
                    break
                waited += 1
                log.info("X: حد الطلبات، انتظار %ss", int(max(wait, 30)))
                time.sleep(max(wait, 30))
                continue
            if status != 200 or not j:
                if status == "TIMEOUT" and not db and it["tries"] >= 1 and len(qlog) == 0:
                    raise SourceDown("NO_SEARCH_RESPONSE " + pg.url.split("?")[0])
                if time.time() - t0 > BUDGET:
                    stopped = "BUDGET"
                    break
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
        if db and stopped != "BUDGET":
            try:
                _attach_parents(db, _parents(pg, db))
            except Exception as e:
                log.warning("X: تعذر جلب سياق الردود: %s", str(e)[:120])
    bad = sum(1 for x in qlog if str(x.get("status", "")).startswith(("TIMEOUT", "HTTP")))
    status = "DONE" if stopped == "DONE" else ("PARTIAL_429" if stopped == "429" else "PARTIAL_TIME")
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
