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


_HEAVY = {"media", "image", "font"}


def primary(cut_dt):
    if not config.TIKTOK_COOKIES:
        raise SourceDown("NO_ACCOUNT")
    out, captured, errors = [], [], []
    with chrome(_cookies()) as c:
        p = c.new_page()
        # التابلت يشغّل المتصفح بعملية واحدة؛ فيديوهات تيك توك الثقيلة تُسقطه.
        # نحتاج فقط ردود البحث (JSON)، فنمنع الفيديو والصور والخطوط.
        try:
            p.route("**/*", lambda route: route.abort() if route.request.resource_type in _HEAVY else route.continue_())
        except Exception as e:
            log.warning("تيك توك: تعذر منع الوسائط: %s", e)

        def on(r):
            if "/api/search/" in r.url and ("item" in r.url or "general" in r.url):
                try:
                    captured.append(r.json())
                except Exception:
                    pass
        p.on("response", on)
        for q in config.TIKTOK_TERMS:
            captured.clear()
            try:
                p.goto("https://www.tiktok.com/search/video?q=" + urllib.parse.quote(q), timeout=60000,
                       wait_until="domcontentloaded")
                time.sleep(8)
            except Exception as e:
                errors.append(f"{type(e).__name__}: {str(e)[:120]}")
                log.warning("تيك توك «%s»: %s", q, errors[-1])
            for j in list(captured):
                out += _parse(j, q)
            if errors and "closed" in errors[-1].lower():
                break  # المتصفح سقط؛ نكتفي بما جُمع ويُعاد تشغيله في الدورة القادمة
            time.sleep(3)
        try:
            if not out and "login" in p.url:
                raise SourceDown("LOGIN_REQUIRED")
        except SourceDown:
            raise
        except Exception:
            pass
    if not out:
        raise SourceDown("NO_RESULTS_CAPTURED" + (" | " + errors[-1] if errors else ""))
    return [i for i in out if parse_dt(i["created"]) >= cut_dt]


def fallback(cut_dt):
    qs = [f'site:tiktok.com "{t}"' for t in config.TIKTOK_TERMS[:3]]
    res = websearch.search(qs, platform="tiktok")
    return [i for i in res if "/video/" in i["url"] or "/@" in i["url"]]
