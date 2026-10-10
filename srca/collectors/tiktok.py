"""تيك توك: بحث بحساب الرصد (كوكيز) والتقاط ردود البحث؛ بديله بحث الويب site:tiktok.com."""
import time, urllib.parse

from .. import config
from ..util import item, parse_dt, log
from .browser import chrome
from . import websearch


class SourceDown(Exception):
    pass


def _cookies():
    out = []
    for part in config.TIKTOK_COOKIES.split(";"):
        if "=" in part:
            k, v = part.strip().split("=", 1)
            out.append({"name": k, "value": v, "domain": ".tiktok.com", "path": "/", "secure": True, "sameSite": "Lax"})
    return out


def _parse(j, q):
    out = []
    lst = j.get("item_list") or [d.get("item") for d in j.get("data", []) if isinstance(d, dict) and d.get("item")]
    for v in lst or []:
        if not v or not v.get("id"):
            continue
        au = v.get("author") or {}
        st = v.get("stats") or {}
        uid = au.get("uniqueId", "")
        out.append(item("tiktok", v["id"], f"https://www.tiktok.com/@{uid}/video/{v['id']}", v.get("desc", ""),
                        parse_dt(v.get("createTime")), uid, au.get("nickname", ""), query=q,
                        metrics={"like": st.get("diggCount"), "rep": st.get("commentCount"),
                                 "rt": st.get("shareCount"), "views": st.get("playCount")}))
    return out


def primary(cut_dt):
    if not config.TIKTOK_COOKIES:
        raise SourceDown("NO_ACCOUNT")
    out, captured = [], []
    with chrome(_cookies()) as c:
        p = c.new_page()

        def on(r):
            if "/api/search/" in r.url and ("item" in r.url or "general" in r.url):
                try:
                    captured.append(r.json())
                except Exception:
                    pass
        p.on("response", on)
        for q in config.TIKTOK_TERMS:
            captured.clear()
            p.goto("https://www.tiktok.com/search/video?q=" + urllib.parse.quote(q), timeout=60000)
            time.sleep(8)
            for j in captured:
                out += _parse(j, q)
            time.sleep(3)
        if not out and "login" in p.url:
            raise SourceDown("LOGIN_REQUIRED")
    if not out:
        raise SourceDown("NO_RESULTS_CAPTURED")
    return [i for i in out if parse_dt(i["created"]) >= cut_dt]


def fallback(cut_dt):
    qs = [f'site:tiktok.com "{t}"' for t in config.TIKTOK_TERMS[:3]]
    res = websearch.search(qs, platform="tiktok")
    return [i for i in res if "/video/" in i["url"] or "/@" in i["url"]]
