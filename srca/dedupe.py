"""دمج المكرر بين المنصات: نفس القصة في X والأخبار ويوتيوب = مجموعة واحدة وتنبيه واحد."""
import re

from . import store
from .util import norm


def _sh(t, n=3):
    w = norm(t).split()
    return {" ".join(w[i:i + n]) for i in range(max(1, len(w) - n + 1))} if w else set()


def _urls(t):
    return {u.rstrip("/.،") for u in re.findall(r"https?://\S+", t or "") if "t.co/" not in u}


def assign(new_items):
    """يضع cluster لكل عنصر جديد مقابل آخر 72 ساعة."""
    pool = store.rows("created >= ? AND relevance IN ('مؤكد','محتمل')", (store.since(72),))
    idx = [(r["cluster"] or r["id"], _sh(r["text"]), _urls(r["text"]) | {r["url"]}) for r in pool]
    for it in new_items:
        sh, us = _sh(it["text"]), _urls(it["text"]) | {it["url"]}
        best = None
        for cid, osh, ous in idx:
            if us & ous:
                best = cid; break
            if len(sh) >= 4 and len(osh) >= 4:
                j = len(sh & osh) / len(sh | osh)
                if j >= 0.5:
                    best = cid; break
        it["cluster"] = best or it["id"]
        idx.append((it["cluster"], sh, us))
    return new_items
