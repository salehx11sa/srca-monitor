"""تيك توك عبر خدمة Apify (بدون متصفح على التابلت)؛ بديله بحث الويب site:tiktok.com.
كل دورة (30 دقيقة) تبحث كل الكلمات، وتجيب لكل كلمة أحدث 2–3 فيديوهات (config.TIKTOK_COUNTS).
التكلفة: ~0.0003$ للفيديو × 9 × 48 دورة ⇒ ~3.9$ شهريًا داخل الرصيد المجاني (5$)، مع حارس يوقفه قبل نفاد الرصيد."""
import re
from datetime import timedelta

from .. import config, store
from ..util import get, item, log, now, parse_dt, post
from . import websearch

ACTOR = "xmolodtsov~tiktok-search-scraper"
API = "https://api.apify.com/v2"
KEEP_HOURS = 48      # لا نُدخل فيديوهات أقدم من يومين (أول تشغيل لا يغرقك بالقديم)
BUDGET_MARGIN = 0.30  # يتوقف إذا بقي أقل من 0.30$ من الرصيد الشهري


class SourceDown(Exception):
    pass


def _h():
    return {"Authorization": "Bearer " + config.APIFY_TOKEN}


def _budget_ok():
    try:
        r = get(API + "/users/me/limits", headers=_h(), retries=1, timeout=20)
        if r.status_code == 401:
            raise SourceDown("NO_KEY bad token")
        d = r.json().get("data", {})
        used = float((d.get("current") or {}).get("monthlyUsageUsd") or 0)
        cap = float((d.get("limits") or {}).get("maxMonthlyUsageUsd") or 5)
        store.kv_set("apify_usage", {"used": round(used, 3), "cap": cap})
        return used < cap - BUDGET_MARGIN
    except SourceDown:
        raise
    except Exception as e:
        log.warning("تيك توك: تعذر قراءة الرصيد: %s", e)
        return True


def _g(d, *path):
    for p in path:
        if not isinstance(d, dict):
            return None
        d = d.get(p)
    return d


def _to_item(v, q):
    url = v.get("webVideoUrl") or v.get("postPage") or v.get("url") or ""
    vid = str(v.get("id") or "")
    if not vid:
        m = re.search(r"/video/(\d+)", url)
        vid = m.group(1) if m else ""
    if not vid:
        return None
    author = (_g(v, "authorMeta", "name") or _g(v, "channel", "username") or _g(v, "author", "uniqueId") or "")
    name = (_g(v, "authorMeta", "nickName") or _g(v, "channel", "name") or _g(v, "author", "nickname") or "")
    if not url:
        url = f"https://www.tiktok.com/@{author}/video/{vid}"
    created = parse_dt(v.get("createTimeISO") or v.get("uploadedAtFormatted") or v.get("createTime") or v.get("uploadedAt"))
    text = v.get("text") or v.get("title") or v.get("desc") or ""
    m = {"like": v.get("diggCount", v.get("likes")), "rep": v.get("commentCount", v.get("comments")),
         "rt": v.get("shareCount", v.get("shares")), "views": v.get("playCount", v.get("views"))}
    return item("tiktok", vid, url, text, created, author, name, query=q, metrics=m)


def _search(q, n):
    body = {"keywords": [q], "maxItems": n, "sortType": "DATE_POSTED", "includeSearchKeywords": True, "location": "SA"}
    r = post(f"{API}/acts/{ACTOR}/run-sync-get-dataset-items", params={"timeout": 240, "maxTotalChargeUsd": 0.003},
             json=body, headers=_h(), retries=1, timeout=280)
    if r.status_code == 401:
        raise SourceDown("NO_KEY bad token")
    if r.status_code not in (200, 201):
        raise SourceDown(f"HTTP{r.status_code} {r.text[:120]}")
    data = r.json()
    if not isinstance(data, list):
        raise SourceDown("BAD_RESPONSE")
    return data


def primary(cut_dt):
    if not config.APIFY_TOKEN:
        raise SourceDown("NO_KEY")
    if not _budget_ok():
        raise SourceDown("BUDGET رصيد Apify الشهري قارب النفاد")
    oldest_ok = now() - timedelta(hours=KEEP_HOURS)
    out, done, errs = [], [], []
    for q in config.TIKTOK_TERMS:
        try:
            data = _search(q, config.TIKTOK_COUNTS.get(q, 2))
        except SourceDown as e:
            if "NO_KEY" in str(e):
                raise
            errs.append(f"{q}: {e}")
            continue
        n = 0
        for v in data:
            if not isinstance(v, dict) or v.get("errorCode") or v.get("error"):
                continue
            it = _to_item(v, q)
            if it and parse_dt(it["created"]) >= oldest_ok:
                out.append(it)
                n += 1
        done.append(f"{q}:{len(data)}/{n}")
    if not done:
        raise SourceDown("ALL_FAILED " + " | ".join(errs)[:200])
    log.info("تيك توك: %s%s", "، ".join(done), (" | أخطاء: " + "، ".join(errs)) if errs else "")
    extra = _web_extra()
    return out + extra, {"status": "apify " + " ".join(done) + (f" +web:{len(extra)}" if extra else "")}


def _web_extra():
    """بحث إضافي عبر Tavily مرتين في اليوم: يلقط فيديوهات فاتت Apify، وكلمات إضافية. أي خطأ هنا لا يوقف تيك توك."""
    last = store.kv_get("tiktok_web_at")
    if last and now() - parse_dt(last) < timedelta(hours=config.TIKTOK_WEB_EVERY_H - 0.5):
        return []
    if not websearch.available():
        return []
    store.kv_set("tiktok_web_at", now().strftime("%Y-%m-%dT%H:%M:%SZ"))
    try:
        res = websearch.search([f'site:tiktok.com "{t}"' for t in config.TIKTOK_WEB_TERMS],
                               platform="tiktok", freshness=websearch.WEEK)
    except Exception as e:
        log.warning("تيك توك (بحث الويب): %s", e)
        return []
    res = [i for i in res if "/video/" in i["url"]]
    log.info("تيك توك (بحث الويب): %s فيديو", len(res))
    return res


def fallback(cut_dt):
    qs = [f'site:tiktok.com "{t}"' for t in config.TIKTOK_TERMS[:3]]
    res = websearch.search(qs, platform="tiktok")
    return [i for i in res if "/video/" in i["url"] or "/@" in i["url"]]
