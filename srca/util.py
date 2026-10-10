import hashlib, json, logging, re, sys, time
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

import requests

log = logging.getLogger("srca")
if not log.handlers:
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(h)
    log.setLevel(logging.INFO)

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")
S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept-Language": "ar,en;q=0.8"})

RIYADH = timezone(timedelta(hours=3))


def now():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_dt(s):
    if not s:
        return None
    if isinstance(s, (int, float)):
        return datetime.fromtimestamp(s, timezone.utc)
    try:
        return parsedate_to_datetime(s).astimezone(timezone.utc)
    except Exception:
        pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def riyadh(s):
    d = parse_dt(s) if isinstance(s, str) else s
    return d.astimezone(RIYADH).strftime("%Y-%m-%d %H:%M") if d else ""


def get(url, retries=2, **kw):
    kw.setdefault("timeout", 25)
    last = None
    for i in range(retries + 1):
        try:
            r = S.get(url, **kw)
            if r.status_code in (429, 500, 502, 503) and i < retries:
                time.sleep(3 * (i + 1)); continue
            return r
        except requests.RequestException as e:
            last = e
            time.sleep(2 * (i + 1))
    raise last


def post(url, retries=2, **kw):
    kw.setdefault("timeout", 40)
    last = None
    for i in range(retries + 1):
        try:
            r = S.post(url, **kw)
            if r.status_code in (429, 500, 502, 503) and i < retries:
                time.sleep(4 * (i + 1)); continue
            return r
        except requests.RequestException as e:
            last = e
            time.sleep(3 * (i + 1))
    raise last


_AR_NORM = [(re.compile("[إأآا]"), "ا"), (re.compile("ى"), "ي"), (re.compile("ة"), "ه"),
            (re.compile("[ً-ٟـ]"), "")]


def norm(t):
    t = (t or "").lower()
    t = re.sub(r"https?://\S+|@\w+|#", " ", t)
    for rx, rep in _AR_NORM:
        t = rx.sub(rep, t)
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", t)).strip()


def h(s):
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:16]


def item(platform, native_id, url, text, created=None, author="", author_name="", **extra):
    """الشكل الموحد لأي منشور من أي مصدر."""
    return {
        "id": f"{platform}:{native_id}", "platform": platform, "url": url,
        "author": author or "", "author_name": author_name or "",
        "text": (text or "").strip(), "created": iso(created) if created else iso(now()),
        "quoted": extra.pop("quoted", ""), "location": extra.pop("location", ""),
        "metrics": extra.pop("metrics", {}), "media": extra.pop("media", ""),
        "query": extra.pop("query", ""), "extra": extra,
    }


def dumps(o):
    return json.dumps(o, ensure_ascii=False)
