"""بحث الويب (بديل لـ X وتيك توك وريديت، ومصدر للمنتديات).
اختُبر: Bing وDuckDuckGo يقدّمان نتائج مشوّهة لعناوين السيرفرات (يتجاهلان site: وعلامات التنصيص)،
لذلك نستخدم واجهات رسمية بمفتاح: Tavily (الأساسي: 1000 بحث/شهر مجانًا بدون بطاقة)، أو Brave، أو Google Programmable Search.
حارس الاستهلاك: 30 بحثًا في اليوم و950 في الشهر كحد أقصى، فلا يُستنزف الرصيد ولا يُدفع شيء.
بدون مفتاح يُعدّ المصدر «غير متاح» ويُبلَّغ عنه مرة واحدة."""
import os, re

from ..util import get, post, item, h, parse_dt, now

TAVILY_KEY = os.environ.get("TAVILY_API_KEY", "").strip()
BRAVE_KEY = os.environ.get("BRAVE_API_KEY", "").strip()
CSE_KEY = os.environ.get("GOOGLE_CSE_KEY", "").strip()
CSE_ID = os.environ.get("GOOGLE_CSE_ID", "").strip()

WEEK, DAY = "pw", "pd"


class NoBackend(Exception):
    pass


DAY_CAP, MONTH_CAP = 30, 950


def available():
    return bool(TAVILY_KEY or BRAVE_KEY or (CSE_KEY and CSE_ID))


def _spend(n=1):
    """يحسب الاستهلاك؛ يرجع False إذا تجاوزنا الحد اليومي أو الشهري."""
    from .. import store
    t = now()
    u = store.kv_get("websearch_usage", {}) or {}
    m, d = t.strftime("%Y-%m"), t.strftime("%Y-%m-%d")
    if u.get("m") != m:
        u = {"m": m, "mn": 0}
    if u.get("d") != d:
        u.update(d=d, dn=0)
    if u["dn"] + n > DAY_CAP or u["mn"] + n > MONTH_CAP:
        return False
    u["dn"] += n
    u["mn"] += n
    store.kv_set("websearch_usage", u)
    return True


def _tavily(q, freshness):
    inc = re.findall(r"(?<!-)site:(\S+)", q)
    exc = re.findall(r"-site:(\S+)", q)
    clean = re.sub(r"-?site:\S+", " ", q).replace(" OR ", " ")
    clean = re.sub(r"\s+", " ", clean).strip() or q
    body = {"query": clean, "search_depth": "basic", "max_results": 20,
            "time_range": "day" if freshness == DAY else "week"}
    if inc:
        body["include_domains"] = inc
    if exc:
        body["exclude_domains"] = exc
    r = post("https://api.tavily.com/search", json=body, headers={"Authorization": "Bearer " + TAVILY_KEY},
             retries=1, timeout=40)
    r.raise_for_status()
    return [(x.get("url", ""), x.get("title", ""), x.get("content", ""), parse_dt(x.get("published_date")))
            for x in r.json().get("results", [])]


def _mk(platform, u, title, snip, d, q):
    m = re.search(r"/(?:video|status)/(\d+)", u)
    return item(platform, m.group(1) if m else h(u), u, (title + " — " + snip).strip(" —"), d, query="web:" + q,
                via="websearch")


def search(queries, platform="web", freshness=WEEK, ctx=None):
    if not available():
        raise NoBackend("NO_SEARCH_KEY")
    out, errors = [], 0
    for q in queries:
        if not _spend():
            raise NoBackend("BUDGET حد البحث اليومي/الشهري")
        try:
            if TAVILY_KEY:
                for u, t, c, d in _tavily(q, freshness):
                    if u:
                        out.append(_mk(platform, u, t, c, d, q))
            elif BRAVE_KEY:
                r = get("https://api.search.brave.com/res/v1/web/search",
                        params={"q": q, "freshness": freshness, "count": 20, "country": "SA", "search_lang": "ar"},
                        headers={"X-Subscription-Token": BRAVE_KEY, "Accept": "application/json"})
                r.raise_for_status()
                for x in r.json().get("web", {}).get("results", []):
                    out.append(_mk(platform, x["url"], x.get("title", ""), re.sub("<[^>]+>", "", x.get("description", "")),
                                   parse_dt(x.get("page_age")), q))
            else:
                r = get("https://www.googleapis.com/customsearch/v1",
                        params={"q": q, "key": CSE_KEY, "cx": CSE_ID, "dateRestrict": "d1" if freshness == DAY else "w1",
                                "num": 10, "gl": "sa", "hl": "ar"})
                r.raise_for_status()
                for x in r.json().get("items", []):
                    out.append(_mk(platform, x["link"], x.get("title", ""), x.get("snippet", ""), None, q))
        except Exception:
            errors += 1
    if errors == len(queries):
        raise RuntimeError("websearch all failed")
    return out
