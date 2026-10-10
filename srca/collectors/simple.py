"""مصادر لا تحتاج تسجيل دخول: الأخبار، يوتيوب، قنوات تيليجرام، تقييمات التطبيقات، ريديت، المنتديات، خرائط قوقل.
كل مصدر له دالة أساسية وبديل؛ المنسّق في main يحوّل للبديل تلقائيًا."""
import html, json, re, urllib.parse
from datetime import timedelta

import feedparser

from .. import config
from ..util import get, item, h, now, parse_dt, log
from . import websearch


class SourceDown(Exception):
    pass


def _feed(url):
    r = get(url)
    if r.status_code != 200:
        raise SourceDown(f"HTTP{r.status_code}")
    f = feedparser.parse(r.content)
    if f.bozo and not f.entries:
        raise SourceDown("BAD_FEED")
    return f.entries


# ---------- الأخبار ----------
NEWS_Q = ['"الهلال الأحمر السعودي"', '"هيئة الهلال الأحمر" السعودية', '"الهلال الأحمر" إسعاف (الرياض OR جدة OR مكة OR الدمام)',
          '"Saudi Red Crescent"']


def news_primary(cut_dt):
    out = []
    for q in NEWS_Q:
        en = q.startswith('"Saudi')
        url = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(q + " when:2d")
               + ("&hl=en-US&gl=US&ceid=US:en" if en else "&hl=ar&gl=SA&ceid=SA:ar"))
        for e in _feed(url):
            d = parse_dt(e.get("published"))
            if d and d < cut_dt:
                continue
            src = (e.get("source") or {}).get("title", "")
            out.append(item("news", h(e.link), e.link, html.unescape(e.title), d, src, src, query=q,
                            summary=re.sub("<[^>]+>", " ", e.get("summary", ""))[:300]))
    return out


def news_fallback(cut_dt):
    out = []
    for q in NEWS_Q:
        url = "https://www.bing.com/news/search?q=" + urllib.parse.quote(q) + "&format=rss&setlang=ar&cc=SA"
        for e in _feed(url):
            d = parse_dt(e.get("published"))
            if d and d < cut_dt:
                continue
            link = e.link
            m = re.search(r"[?&]url=([^&]+)", link)
            if m:
                link = urllib.parse.unquote(m.group(1))
            out.append(item("news", h(link), link, html.unescape(e.title) + " — " + re.sub("<[^>]+>", " ", e.get("summary", ""))[:300],
                            d, "", "", query="bing:" + q))
    return out


# ---------- يوتيوب ----------
YT_Q = ["الهلال الأحمر السعودي", "هيئة الهلال الأحمر", "الاسعاف السعودي تجربتي"]


def _rel_time(s):
    m = re.search(r"(\d+)\s*(seconds?|s|minutes?|min|m|hours?|h|days?|d|weeks?|w|months?|mo|years?|y)\b", s or "")
    if not m:
        return None
    n, u = int(m.group(1)), m.group(2)
    if u.startswith("mo"):
        mult = 720
    elif u.startswith("mi") or u == "m":
        mult = 1 / 60
    else:
        mult = {"s": 1 / 3600, "h": 1, "d": 24, "w": 168, "y": 8760}[u[0]]
    return now() - timedelta(hours=n * mult)


def youtube_primary(cut_dt):
    out = []
    if config.YOUTUBE_KEY:
        for q in YT_Q:
            r = get("https://www.googleapis.com/youtube/v3/search", params={
                "part": "snippet", "q": q, "type": "video", "order": "date", "maxResults": 25, "regionCode": "SA",
                "publishedAfter": cut_dt.strftime("%Y-%m-%dT%H:%M:%SZ"), "key": config.YOUTUBE_KEY})
            if r.status_code != 200:
                raise SourceDown(f"API{r.status_code}")
            for v in r.json().get("items", []):
                sn = v["snippet"]
                vid = v["id"]["videoId"]
                out.append(item("youtube", vid, f"https://www.youtube.com/watch?v={vid}",
                                sn["title"] + " — " + sn.get("description", ""), parse_dt(sn["publishedAt"]),
                                sn.get("channelId", ""), sn.get("channelTitle", ""), query=q))
        return out
    for q in YT_Q:  # بلا مفتاح: صفحة البحث (فلتر هذا الأسبوع)
        r = get("https://www.youtube.com/results", params={"search_query": q, "sp": "EgQIAxAB", "hl": "en", "gl": "SA"},
                headers={"Accept-Language": "en"})
        m = re.search(r"var ytInitialData = (\{.*?\});</script>", r.text)
        if not m:
            raise SourceDown("NO_DATA")
        found = []

        def walk(o):
            if isinstance(o, dict):
                if "videoRenderer" in o:
                    found.append(o["videoRenderer"])
                for x in o.values():
                    walk(x)
            elif isinstance(o, list):
                for x in o:
                    walk(x)
        walk(json.loads(m.group(1)))
        for v in found:
            d = _rel_time(v.get("publishedTimeText", {}).get("simpleText", ""))
            if not d or d < cut_dt - timedelta(hours=2):
                continue
            title = "".join(x.get("text", "") for x in v.get("title", {}).get("runs", []))
            desc = "".join(x.get("text", "") for s in v.get("detailedMetadataSnippets", [])
                           for x in s.get("snippetText", {}).get("runs", []))
            ch = (v.get("ownerText", {}).get("runs") or [{}])[0]
            out.append(item("youtube", v["videoId"], f"https://www.youtube.com/watch?v={v['videoId']}",
                            title + (" — " + desc if desc else ""), d,
                            ch.get("navigationEndpoint", {}).get("browseEndpoint", {}).get("canonicalBaseUrl", ""),
                            ch.get("text", ""), query=q,
                            metrics={"views": v.get("viewCountText", {}).get("simpleText", "")}))
    return out


def youtube_fallback(cut_dt):
    qs = [f'site:youtube.com "{q}"' for q in YT_Q[:2]]
    return [i for i in websearch.search(qs, platform="youtube", freshness=websearch.WEEK) if "watch" in i["url"]]


# ---------- قنوات تيليجرام العامة ----------
TG_REL = re.compile(r"الهلال الأحمر|الهلال الاحمر|هيئة الهلال|Red Crescent|الإسعاف|الاسعاف|إسعاف|اسعاف|المسعف", re.I)


def telegram_primary(cut_dt):
    out, ok = [], 0
    for ch in config.TELEGRAM_CHANNELS:
        r = get(f"https://t.me/s/{ch}")
        if r.status_code != 200:
            continue
        ok += 1
        for b in r.text.split("tgme_widget_message_wrap")[1:]:
            mp, mt, md = (re.search(r'data-post="([^"]+)"', b), re.search(r"tgme_widget_message_text[^>]*>(.*?)</div>", b, re.S),
                          re.search(r'datetime="([^"]+)"', b))
            if not (mp and mt):
                continue
            post, dt = mp.group(1), parse_dt(md.group(1)) if md else None
            text = html.unescape(re.sub("<[^>]+>", " ", mt.group(1))).strip()
            if not TG_REL.search(text) or (dt and dt < cut_dt):
                continue
            out.append(item("telegram", post.replace("/", "_"), f"https://t.me/{post}", text, dt, ch, ch))
    if config.TELEGRAM_CHANNELS and not ok:
        raise SourceDown("ALL_CHANNELS_DOWN")
    return out


def telegram_fallback(cut_dt):
    raise SourceDown("NO_FALLBACK")  # لا بديل مجاني موثوق لبحث تيليجرام؛ يُبلَّغ عن التعطل فقط


# ---------- تقييمات التطبيقات ----------
def apps_primary(cut_dt):
    from google_play_scraper import reviews, Sort
    out = []
    for app in config.PLAY_APPS:
        try:
            res, _ = reviews(app, lang="ar", country="sa", sort=Sort.NEWEST, count=40)
        except Exception as e:
            log.warning("Google Play %s: %s", app, e)
            continue
        for rv in res:
            d = rv["at"].replace(tzinfo=None)
            d = parse_dt(d.isoformat() + "+03:00") if d else None
            if d and d < cut_dt:
                continue
            out.append(item("app", "gp_" + rv["reviewId"],
                            f"https://play.google.com/store/apps/details?id={app}&reviewId={rv['reviewId']}",
                            f"[{rv['score']}★] {rv['content']}", d, rv.get("userName", ""), rv.get("userName", ""),
                            query=app, app=app, score=rv["score"], reply=rv.get("replyContent")))
    # App Store: نحدد التطبيقات من نفس المعرّفات إن وُجدت نسخة iOS
    for app in config.PLAY_APPS:
        try:
            lk = get("https://itunes.apple.com/lookup", params={"bundleId": app, "country": "sa"}).json()
            for a in lk.get("results", []):
                feed = get(f"https://itunes.apple.com/sa/rss/customerreviews/id={a['trackId']}/sortBy=mostRecent/json").json()
                for e in feed.get("feed", {}).get("entry", [])[1:] if isinstance(feed.get("feed", {}).get("entry"), list) else []:
                    d = parse_dt(e.get("updated", {}).get("label"))
                    if d and d < cut_dt:
                        continue
                    rid = e.get("id", {}).get("label", "")
                    out.append(item("app", "as_" + rid, f"https://apps.apple.com/sa/app/id{a['trackId']}",
                                    f"[{e.get('im:rating', {}).get('label')}★] {e.get('title', {}).get('label', '')} — {e.get('content', {}).get('label', '')}",
                                    d, e.get("author", {}).get("name", {}).get("label", ""), "", query=app))
        except Exception:
            pass
    return out


def apps_fallback(cut_dt):
    raise SourceDown("NO_FALLBACK")


# ---------- ريديت والمنتديات ----------
def reddit_primary(cut_dt):
    out = []
    for q in ['"Saudi Red Crescent"', '"الهلال الأحمر السعودي"', 'ambulance Saudi']:
        r = get("https://www.reddit.com/search.rss", params={"q": q, "sort": "new", "t": "week"})
        if r.status_code != 200:
            raise SourceDown(f"HTTP{r.status_code}")
        for e in feedparser.parse(r.content).entries:
            d = parse_dt(e.get("updated") or e.get("published"))
            if d and d < cut_dt:
                continue
            out.append(item("reddit", h(e.link), e.link, html.unescape(e.title) + " — " +
                            re.sub("<[^>]+>", " ", e.get("summary", ""))[:400], d,
                            e.get("author", ""), e.get("author", ""), query=q))
    return out


def reddit_fallback(cut_dt):
    return websearch.search(['site:reddit.com "Saudi Red Crescent"', 'site:reddit.com "الهلال الأحمر السعودي"'],
                            platform="reddit")


def web_primary(cut_dt):
    """المنتديات والمواقع العامة: بحث ويب لآخر 24 ساعة بدون المواقع المرصودة مسبقًا."""
    qs = ['"الهلال الأحمر السعودي" -site:x.com -site:tiktok.com -site:youtube.com',
          '"هيئة الهلال الأحمر" تجربة', '"الهلال الأحمر السعودي" شكوى',
          'site:linkedin.com "الهلال الأحمر السعودي" OR "Saudi Red Crescent"']
    res = websearch.search(qs, platform="web", freshness=websearch.DAY)
    skip = ("x.com", "twitter.com", "tiktok.com", "youtube.com", "reddit.com", "srca.gov.sa")
    out = [i for i in res if not any(s in i["url"] for s in skip)]
    for i in out:  # لينكدإن يُرصد عبر بحث الويب (يمنع الجمع المباشر)
        if "linkedin.com" in i["url"]:
            i["platform"], i["id"] = "linkedin", "linkedin:" + i["id"].split(":", 1)[1]
    return out


def web_fallback(cut_dt):
    raise SourceDown("NO_FALLBACK")


# ---------- خرائط قوقل ----------
def maps_primary(cut_dt):
    if not config.PLACES_KEY:
        raise SourceDown("NO_KEY")
    out = []
    for q in config.MAPS_QUERIES:
        from ..util import post
        r = post("https://places.googleapis.com/v1/places:searchText", json={"textQuery": q, "languageCode": "ar"},
                    headers={"X-Goog-Api-Key": config.PLACES_KEY,
                             "X-Goog-FieldMask": "places.id,places.displayName,places.reviews,places.googleMapsUri"}, timeout=25)
        if r.status_code != 200:
            raise SourceDown(f"HTTP{r.status_code}")
        for pl in r.json().get("places", []):
            for rv in pl.get("reviews", []) or []:
                d = parse_dt(rv.get("publishTime"))
                if d and d < cut_dt:
                    continue
                txt = (rv.get("text") or {}).get("text", "")
                out.append(item("maps", h(pl["id"] + rv.get("name", "")), pl.get("googleMapsUri", ""),
                                f"[{rv.get('rating')}★ {pl.get('displayName', {}).get('text', '')}] {txt}", d,
                                (rv.get("authorAttribution") or {}).get("displayName", ""), "", query=q))
    return out


def maps_fallback(cut_dt):
    raise SourceDown("NO_FALLBACK")


REGISTRY = {
    "news": (news_primary, news_fallback),
    "youtube": (youtube_primary, youtube_fallback),
    "telegram": (telegram_primary, telegram_fallback),
    "apps": (apps_primary, apps_fallback),
    "reddit": (reddit_primary, reddit_fallback),
    "web": (web_primary, web_fallback),
    "maps": (maps_primary, maps_fallback),
}
