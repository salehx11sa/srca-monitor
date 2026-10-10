"""الذاكرة: قاعدة SQLite على السيرفر (سريعة، مجانية، بلا حدود)."""
import json, sqlite3
from datetime import timedelta

from . import config
from .util import now, iso, parse_dt

SCHEMA = """
CREATE TABLE IF NOT EXISTS items(
  id TEXT PRIMARY KEY, platform TEXT, url TEXT, author TEXT, author_name TEXT, text TEXT, quoted TEXT,
  created TEXT, collected TEXT, location TEXT, metrics TEXT, media TEXT, query TEXT, extra TEXT,
  cluster TEXT, relevance TEXT, priority TEXT, sentiment TEXT, ctype TEXT, summary TEXT, reason TEXT,
  region TEXT, classifier TEXT, alerted INTEGER DEFAULT 0, alerted_at TEXT, synced INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS i_created ON items(created);
CREATE INDEX IF NOT EXISTS i_cluster ON items(cluster);
CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY AUTOINCREMENT, started TEXT, finished TEXT,
  runner TEXT, kind TEXT, status TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS source_state(source TEXT PRIMARY KEY, last_ok TEXT, last_cut TEXT,
  mode TEXT DEFAULT 'primary', fails INTEGER DEFAULT 0, last_error TEXT);
CREATE TABLE IF NOT EXISTS feedback(item_id TEXT PRIMARY KEY, verdict TEXT, at TEXT, author TEXT, text TEXT);
CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT);
"""

_con = None


def db():
    global _con
    if _con is None:
        _con = sqlite3.connect(config.DB_PATH, timeout=30)
        _con.row_factory = sqlite3.Row
        _con.executescript(SCHEMA)
    return _con


def kv_get(k, d=None):
    r = db().execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
    return json.loads(r["v"]) if r else d


def kv_set(k, v):
    db().execute("INSERT OR REPLACE INTO kv(k,v) VALUES(?,?)", (k, json.dumps(v, ensure_ascii=False)))
    db().commit()


def known_ids(ids):
    if not ids:
        return set()
    out = set()
    ids = list(ids)
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        q = "SELECT id FROM items WHERE id IN (%s)" % ",".join("?" * len(chunk))
        out |= {r["id"] for r in db().execute(q, chunk)}
    return out


def add_items(items):
    """يضيف الجديد فقط ويرجعه."""
    seen = known_ids([i["id"] for i in items])
    extra_seen = set(kv_get("seen_remote", []))  # معرّفات قادمة من الجدول (للتشغيل الاحتياطي)
    new = []
    for it in items:
        if it["id"] in seen or it["id"] in extra_seen:
            continue
        seen.add(it["id"])
        db().execute(
            "INSERT OR IGNORE INTO items(id,platform,url,author,author_name,text,quoted,created,collected,location,"
            "metrics,media,query,extra) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (it["id"], it["platform"], it["url"], it["author"], it["author_name"], it["text"], it["quoted"],
             it["created"], iso(now()), it["location"], json.dumps(it["metrics"], ensure_ascii=False),
             it["media"], it["query"], json.dumps(it["extra"], ensure_ascii=False)))
        new.append(it)
    db().commit()
    return new


def update_item(iid, **f):
    if not f:
        return
    cols = ",".join(f"{k}=?" for k in f)
    db().execute(f"UPDATE items SET {cols} WHERE id=?", (*f.values(), iid))
    db().commit()


def rows(where="1=1", args=(), order="created DESC", limit=None):
    q = f"SELECT * FROM items WHERE {where} ORDER BY {order}" + (f" LIMIT {int(limit)}" if limit else "")
    return [dict(r) for r in db().execute(q, args)]


def since(hours):
    return iso(now() - timedelta(hours=hours))


# --- حالة كل مصدر (للتحويل للبديل والتنبيه مرة واحدة) ---
def src_get(name):
    r = db().execute("SELECT * FROM source_state WHERE source=?", (name,)).fetchone()
    return dict(r) if r else {"source": name, "last_ok": None, "last_cut": None, "mode": "primary", "fails": 0}


def src_set(name, **f):
    cur = src_get(name)
    cur.update(f)
    db().execute("INSERT OR REPLACE INTO source_state(source,last_ok,last_cut,mode,fails,last_error) VALUES(?,?,?,?,?,?)",
                 (name, cur.get("last_ok"), cur.get("last_cut"), cur.get("mode"), cur.get("fails", 0), cur.get("last_error")))
    db().commit()


def run_start(kind):
    c = db().execute("INSERT INTO runs(started,runner,kind,status) VALUES(?,?,?,?)",
                     (iso(now()), config.RUNNER, kind, "running"))
    db().commit()
    return c.lastrowid


def run_end(rid, status, detail):
    db().execute("UPDATE runs SET finished=?, status=?, detail=? WHERE id=?",
                 (iso(now()), status, json.dumps(detail, ensure_ascii=False), rid))
    db().commit()


def last_runs(n=10):
    return [dict(r) for r in db().execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (n,))]


def cut_for(source, default_hours=6, overlap_min=20):
    """نقطة البداية للبحث: آخر فحص ناجح لهذا المصدر ناقص هامش تداخل."""
    st = src_get(source)
    d = parse_dt(st.get("last_cut")) if st.get("last_cut") else None
    if not d:
        return now() - timedelta(hours=default_hours)
    return d - timedelta(minutes=overlap_min)
