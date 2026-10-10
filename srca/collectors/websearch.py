"""بحث الويب (بديل لـ X وتيك توك وريديت، ومصدر للمنتديات).
اختُبر: Bing وDuckDuckGo يقدّمان نتائج مشوّهة لعناوين السيرفرات (يتجاهلان site: وعلامات التنصيص)،
لذلك نستخدم واجهات رسمية مجانية بمفتاح: Brave Search (2000 بحث/شهر) أو Google Programmable Search (100/يوم).
بدون مفتاح يُعدّ المصدر «غير متاح» ويُبلَّغ عنه مرة واحدة."""
import os, re

from ..util import get, item, h, parse_dt

BRAVE_KEY = os.environ.get("BRAVE_API_KEY", "").strip()
CSE_KEY = os.environ.get("GOOGLE_CSE_KEY", "").strip()
CSE_ID = os.environ.get("GOOGLE_CSE_ID", "").strip()

WEEK, DAY = "pw", "pd"


class NoBackend(Exception):
    pass


def available():
    return bool(BRAVE_KEY or (CSE_KEY and CSE_ID))


def _mk(platform, u, title, snip, d, q):
    m = re.search(r"/(?:video|status)/(\d+)", u)
    return item(platform, m.group(1) if m else h(u), u, (title + " — " + snip).strip(" —"), d, query="web:" + q,
                via="websearch")


def search(queries, platform="web", freshness=WEEK, ctx=None):
    if not available():
        raise NoBackend("NO_SEARCH_KEY")
    out, errors = [], 0
    for q in queries:
        try:
            if BRAVE_KEY:
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
