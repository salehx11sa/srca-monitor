"""المنسّق: python -m srca.main run|daily|weekly|monthly|test|should-backup|backup-loop
كل تعقيد التشغيل هنا؛ أنت لا ترى إلا التنبيهات والجدول واللوحة."""
import sys, time, traceback
from datetime import timedelta

from . import config, dedupe, notify, reports, sheet, store
from .classify import llm, rules
from .collectors import simple, tiktok, x
from .collectors.websearch import NoBackend
from .util import get, log, now, iso, parse_dt, riyadh, RIYADH

NAMES = {"x": "X", "tiktok": "تيك توك", "news": "الأخبار", "youtube": "يوتيوب", "telegram": "قنوات تيليجرام",
         "apps": "تقييمات التطبيقات", "reddit": "ريديت", "web": "المنتديات والمواقع", "maps": "خرائط قوقل"}
# كل كم دقيقة يُفحص كل مصدر (X كل دورة). ريديت كل 12 ساعة: ما يجيب شي تقريبًا، ووفّرنا بحثه لتيك توك
EVERY = {"x": 0, "tiktok": 0, "news": 0, "youtube": 120, "telegram": 60, "apps": 360, "reddit": 720, "web": 720, "maps": 1440}
SOURCES = {
    "x": (x.collect, x.fallback),
    "tiktok": (tiktok.primary, tiktok.fallback),
    **simple.REGISTRY,
}


def ping(suffix=""):
    if config.HEALTHCHECK_URL:
        try:
            get(config.HEALTHCHECK_URL.rstrip("/") + suffix, retries=1, timeout=10)
        except Exception:
            pass


def _notice(source, mode, detail=""):
    if config.RUNNER == "backup":
        return  # الاحتياطي لا يرسل رسالة لكل مصدر؛ يرسل رسالة واحدة مجمّعة عند الاستلام (_takeover_note)
    n = NAMES.get(source, source)
    msg = {"fallback": f"مصدر «{n}» متعطل، والرصد مستمر عن طريق البديل.",
           "down": f"مصدر «{n}» متوقف هو وبديله. بقية المصادر تعمل، وسأبلغك إذا رجع.",
           "primary": f"مصدر «{n}» رجع يعمل بشكل طبيعي.",
           "nokey": f"مصدر «{n}» غير مفعّل بعد (ينقصه حساب أو مفتاح)."}[mode]
    notify.send("حالة الرصد", msg, notify.QUIET)


def collect_source(name, start):
    prim, fb = SOURCES[name]
    st = store.src_get(name)
    if EVERY.get(name) and st.get("last_ok") and (now() - parse_dt(st["last_ok"])) < timedelta(minutes=EVERY[name] - 5):
        return [], "skip"
    cut = store.cut_for(name, default_hours=6 if config.RUNNER == "server" else 3)
    over = store.kv_get("cut_override")
    if over:
        cut = min(cut, parse_dt(over))
    detail = ""
    try:
        res = prim(cut)
        items, info = res if isinstance(res, tuple) else (res, {})
        detail = info.get("status", "") if isinstance(info, dict) else ""
        if st.get("mode") not in ("primary", None) and st.get("mode") != "nokey":
            _notice(name, "primary")
        store.src_set(name, last_ok=iso(start), last_cut=iso(start), mode="primary", fails=0, last_error="")
        return items, "primary " + detail
    except Exception as e:
        err = f"{type(e).__name__}: {str(e)[:150]}"
        nokey = any(k in str(e) for k in ("NO_ACCOUNT", "NO_KEY", "NO_SEARCH_KEY"))
    try:
        items = fb(cut)
        if items is None:
            raise RuntimeError("no fallback")
        if st.get("mode") != "fallback" and not nokey:
            _notice(name, "fallback")
        store.src_set(name, last_ok=iso(start), last_cut=iso(start), mode="fallback", fails=0, last_error=err)
        return items, "fallback (" + err + ")"
    except Exception as e2:
        mode = "nokey" if nokey and isinstance(e2, (NoBackend, RuntimeError, simple.SourceDown, tiktok.SourceDown)) else "down"
        if st.get("mode") != mode and (mode == "down" or not st.get("last_error")):
            _notice(name, mode)
        store.src_set(name, mode=mode, fails=(st.get("fails") or 0) + 1, last_error=err + " | " + str(e2)[:100])
        return [], f"{mode}: {err}"


def _feedback():
    """تقييماتك من اللوحة: تُستخدم أمثلةً للذكاء، ومن استبعدته مرتين يُستبعد تلقائيًا."""
    if not sheet.enabled():
        return [], set()
    try:
        for f in sheet.feedback():
            store.db().execute("INSERT OR REPLACE INTO feedback(item_id,verdict,at,author,text) VALUES(?,?,?,?,?)",
                               (f["id"], f["verdict"], f.get("at", ""), f.get("author", ""), f.get("text", "")))
        store.db().commit()
    except Exception as e:
        log.warning("تعذر جلب التقييمات: %s", e)
    fb = [dict(r) for r in store.db().execute("SELECT * FROM feedback ORDER BY at DESC LIMIT 60")]
    cnt = {}
    for f in fb:
        if f["verdict"] == "مستبعد" and f["author"]:
            cnt[f["author"].lower()] = cnt.get(f["author"].lower(), 0) + 1
    return fb, {a for a, n in cnt.items() if n >= 2}


def alerts():
    """يبني التنبيهات من غير المُنبَّه عنه: العاجل منفرد بصفارة، والمهم منفرد بأولوية عالية، والباقي رسالة مجمّعة واحدة."""
    rows = store.rows("alerted=0 AND relevance IN ('مؤكد','محتمل') AND created >= ?", (store.since(48),), order="created")
    done_clusters = {r["cluster"] for r in store.rows("alerted=1 AND created >= ?", (store.since(72),)) if r["cluster"]}
    urgent, important, normal, mark = [], [], [], []
    for r in rows:
        mark.append(r["id"])
        if r["cluster"] in done_clusters:
            continue
        done_clusters.add(r["cluster"])
        if r["priority"] == "عاجل":
            urgent.append(r)
        elif r["priority"] == "مهم":
            important.append(r)
        elif r["relevance"] == "مؤكد":
            normal.append(r)
    dash = sheet.dashboard_url() or None
    # منشورات نفس النقاش (أصل + ردود، أو عدة ردود) في هذا الفحص ← تنبيه واحد بدل عدة تنبيهات
    convs = {}
    for r in urgent + important + normal:
        k = notify.conv_key(r)
        if k:
            convs.setdefault(k, []).append(r)
    convs = {k: g for k, g in convs.items() if len(g) >= 2}
    grouped = {r["id"] for g in convs.values() for r in g}
    urgent = [r for r in urgent if r["id"] not in grouped]
    important = [r for r in important if r["id"] not in grouped]
    normal = [r for r in normal if r["id"] not in grouped]
    n_conv_hi = 0
    for k, g in convs.items():
        pris = {r["priority"] for r in g}
        lvl, tag = (notify.URGENT, "🔴 عاجل") if "عاجل" in pris else (notify.IMPORTANT, "🟠 مهم") if "مهم" in pris \
            else (notify.NORMAL, "رصد الهلال")
        n_conv_hi += lvl != notify.NORMAL
        cs = [c for r in g for c in notify.context(r)]
        ctx = [c for c in cs if c["root"]] or cs
        who = next((r["author"] for r in g if r["id"] == "x:" + k), None) or (ctx[0]["who"] if ctx else g[0].get("author", ""))
        url = f"https://x.com/{who or 'i'}/status/{k}"
        notify.send(f"{tag} — نقاش @{who}: {len(g)} منشورات", notify.group_body(g, k), lvl, url, "افتح أصل النقاش")
    for r in urgent:
        notify.send("🔴 عاجل — رصد الهلال", notify.line(r), notify.URGENT, r["url"], "افتح المنشور")
    for r in important[:8]:
        notify.send("🟠 مهم — رصد الهلال", notify.line(r), notify.IMPORTANT, r["url"], "افتح المنشور")
    if len(important) > 8:  # حماية من سيل إشعارات: الزائد يُجمع في رسالة مهمة واحدة
        body = "\n\n".join(notify.line(r) for r in important[8:14])
        if len(important) > 14:
            body += f"\n\nو{len(important) - 14} غيرها في اللوحة."
        notify.send(f"🟠 مهم — {len(important) - 8} أخرى", body, notify.IMPORTANT, dash, "افتح اللوحة")
    if normal:
        body = "\n\n".join(notify.line(r) for r in normal[:6])
        if len(normal) > 6:
            body += f"\n\nو{len(normal) - 6} غيرها في اللوحة."
        notify.send(f"رصد الهلال — {len(normal)} اعتيادي", body, notify.NORMAL, dash, "افتح اللوحة")
    for i in mark:
        store.update_item(i, alerted=1, alerted_at=iso(now()))
    return len(urgent) + len(important) + n_conv_hi, len(normal) + len(convs) - n_conv_hi


def run():
    start = now()
    rid = store.run_start("run")
    ping("/start")
    detail = {"runner": config.RUNNER, "sources": {}}
    try:
        if config.RUNNER == "backup" and sheet.enabled():
            if not _backup_should_run():
                store.run_end(rid, "skipped", {"reason": "server alive"})
                return "skipped"
        fb, blocked = _feedback()
        collected = []
        for name in config.SOURCES:
            if name not in SOURCES:
                continue
            items, how = collect_source(name, start)
            detail["sources"][name] = {"n": len(items), "how": how}
            collected += items
        new = store.add_items(collected)
        keep = []
        for it in new:
            ok, why = rules.prefilter(it, blocked)
            if ok:
                keep.append(it)
            else:
                store.update_item(it["id"], relevance="مستبعد", reason=why, classifier="prefilter")
        examples = [f for f in fb if f.get("text")]
        res, used = llm.classify(keep, examples) if keep else ([], set())
        ai_mode = "rules" if used == {"rules"} else "ai"
        if keep and store.kv_get("ai_mode", "ai") != ai_mode:
            store.kv_set("ai_mode", ai_mode)
            notify.send("حالة الرصد", "التصنيف الذكي غير متاح الآن، والرصد مستمر بالقواعد (دقة أقل)." if ai_mode == "rules"
                        else "التصنيف الذكي رجع يعمل.", notify.QUIET)
        for it, c in zip(keep, res):
            it.update(c)
        relevant = [it for it in keep if it.get("relevance") in ("مؤكد", "محتمل")]
        dedupe.assign(relevant)
        for it in keep:
            store.update_item(it["id"], **{k: it.get(k, "") for k in
                                            ("relevance", "priority", "sentiment", "ctype", "summary", "reason", "region",
                                             "classifier")}, cluster=it.get("cluster", ""))
        if config.RUNNER == "server" and not store.kv_get("baseline_done"):
            # أول تشغيل: خط أساس بلا تنبيهات (حتى لا تصلك منشورات قديمة دفعة واحدة)
            store.db().execute("UPDATE items SET alerted=1, alerted_at=? WHERE alerted=0", (iso(now()),))
            store.db().commit()
            store.kv_set("baseline_done", True)
            notify.send("رصد الهلال بدأ", f"المنصة الجديدة تعمل الآن كل {config.INTERVAL_MIN} دقيقة بدون Claude. "
                        f"أول فحص سجّل {len(relevant)} منشورًا كخط أساس بدون تنبيهات.", notify.QUIET,
                        sheet.dashboard_url() or None, "افتح اللوحة")
        u, n = alerts()
        synced = _sync()
        detail.update(collected=len(collected), new=len(new), candidates=len(keep), relevant=len(relevant),
                      urgent=u, grouped=n, synced=synced, classifier=sorted(used))
        down = [k for k, v in detail["sources"].items() if v["how"].startswith("down")]
        status = "ok" if len(down) < max(1, len(detail["sources"]) // 2) else "degraded"
        store.run_end(rid, status, detail)
        if _status(start) and config.RUNNER == "backup":
            _takeover_note(detail)
        ping("" if status == "ok" else "/fail")
        log.info("انتهى الفحص: %s", detail)
    except Exception:
        tb = traceback.format_exc()
        log.error(tb)
        store.run_end(rid, "error", {"error": tb[-1500:]})
        ping("/fail")
        fails = store.kv_get("run_fails", 0) + 1
        store.kv_set("run_fails", fails)
        if fails == 3:  # رسالة واحدة فقط بعد 3 إخفاقات متتالية
            notify.send("حالة الرصد", "الفحص تعطل 3 مرات متتالية. أحاول تلقائيًا كل دورة، وراجع دليل التشغيل إن استمر.", notify.QUIET)
        return "error"
    store.kv_set("run_fails", 0)
    return "ok"


def _sync():
    if not sheet.enabled():
        return 0
    rows = store.rows("synced=0 AND relevance IN ('مؤكد','محتمل')", order="created")
    try:
        for i in range(0, len(rows), 100):
            sheet.append(rows[i:i + 100])
            for r in rows[i:i + 100]:
                store.update_item(r["id"], synced=1)
        return len(rows)
    except Exception as e:
        log.warning("تعذر تحديث الجدول: %s", e)
        return 0


def _status(start):
    """يكتب حالة الرصد في الجدول. يرجع True إذا كُتبت."""
    if not sheet.enabled():
        return False
    try:
        if config.RUNNER == "backup":
            cur = sheet.get_status()
            if cur.get("runner") != "backup" and cur.get("last_run") and parse_dt(cur["last_run"]) > start:
                return False  # التابلت رجع أثناء هذه الدورة: لا نكتب فوق حالته
            server_last = (store.kv_get("takeover") or {}).get("since", "")
        else:
            server_last = iso(start)
        sheet.status(last_run=iso(start), runner=config.RUNNER, server_last=server_last,
                     sources={r["source"]: r["mode"] for r in store.db().execute("SELECT * FROM source_state")})
        return True
    except Exception as e:
        log.warning("تعذر تحديث الحالة: %s", e)
        return False


def _backup_should_run():
    """التشغيل الاحتياطي (GitHub): يعمل فقط إذا غاب التابلت أكثر من 75 دقيقة."""
    st = sheet.get_status()
    last = parse_dt(st.get("last_run")) if st.get("last_run") else None
    if last and now() - last < timedelta(minutes=75) and st.get("runner") != "backup":
        return False
    if st.get("runner") != "backup":
        # استلام جديد: كل المصادر تبدأ من آخر فحص للتابلت، والرسالة تُرسل مرة واحدة بعد أول دورة (_takeover_note)
        store.db().execute("UPDATE source_state SET last_ok=NULL, last_cut=NULL")
        store.db().commit()
        store.kv_set("takeover", {"since": st.get("last_run") or "", "sent": False})
    elif not store.kv_get("takeover"):  # الاحتياطي شغّال من قبل لكن ذاكرته ضاعت: لا نكرر رسالة الاستلام
        store.kv_set("takeover", {"since": st.get("server_last") or "", "sent": True})
    store.kv_set("seen_remote", sheet.seen_ids(7))
    if last:
        store.kv_set("cut_override", iso(last - timedelta(minutes=20)))
    return True


def _hhmm(s):
    d = parse_dt(s) if s else None
    if not d:
        return ""
    d = d.astimezone(RIYADH)
    return f"الساعة {d:%H:%M}" if d.date() == now().astimezone(RIYADH).date() else f"يوم {d:%d/%m} الساعة {d:%H:%M}"


def _takeover_note(detail):
    """رسالة واحدة واضحة عند استلام الاحتياطي، بدل رسالة لكل مصدر."""
    t = store.kv_get("takeover") or {}
    if not t or t.get("sent"):
        return
    on, off = [], []
    for k, v in detail.get("sources", {}).items():
        n, how = NAMES.get(k, k), v.get("how", "")
        if how.startswith(("primary", "skip")):
            on.append(n)
        elif how.startswith("fallback"):
            on.append(n + " (بحث مختصر)")
        elif k != "maps":  # الخرائط غير مفعّلة أصلًا حتى في التابلت
            off.append(n)
    when = _hhmm(t.get("since"))
    msg = f"التابلت ما أرسل أي فحص{' من ' + when if when else ''}، فاستلم الرصد الاحتياطي.\n" \
          f"يعمل الآن: {'، '.join(on) or '—'}."
    if off:
        msg += f"\nلا يعمل في الاحتياطي: {'، '.join(off)}."
    msg += "\nتأكد أن التابلت شغّال ومتصل بالإنترنت، ولما يرجع يوصلك تنبيه."
    notify.send("حالة الرصد", msg, notify.QUIET)
    t["sent"] = True
    store.kv_set("takeover", t)


def backup_loop():
    """الاحتياطي على GitHub. GitHub لا يشغّل الجدول كل ساعة فعليًا (نحو 5 مرات يوميًا)، فإذا استلم الاحتياطي
    يبقى شغّالًا ويفحص عند :20 و:50 (بعيدًا عن دورات التابلت :05 و:35) حتى ~5.5 ساعات، ويخرج فور رجوع التابلت."""
    end = now() + timedelta(minutes=int(config.E("SRCA_BACKUP_MINUTES", "330")))
    while True:
        if run() == "skipped":
            log.info("التابلت يعمل — الاحتياطي يتوقف")
            return
        t = now().astimezone(RIYADH).replace(second=0, microsecond=0)
        nxt = t.replace(minute=20) if t.minute < 20 else t.replace(minute=50) if t.minute < 50 \
            else (t + timedelta(hours=1)).replace(minute=20)
        if nxt > end:
            log.info("انتهت مدة هذا التشغيل الاحتياطي؛ يكمل التشغيل المجدول التالي")
            return
        log.info("الدورة الاحتياطية التالية: %s", nxt.strftime("%H:%M"))
        time.sleep(max(0.0, (nxt - now()).total_seconds()))


def server_returned_check():
    """يُستدعى أول دورة للتابلت: إذا كان الاحتياطي يعمل، يُبلغ برجوع التابلت."""
    if config.RUNNER == "server" and sheet.enabled():
        try:
            st = sheet.get_status()
            if st.get("runner") == "backup" and store.kv_get("returned_for") != st.get("last_run"):
                store.kv_set("returned_for", st.get("last_run"))
                store.kv_set("seen_remote", sheet.seen_ids(3))  # لا نعيد التنبيه عن ما نبّه عنه الاحتياطي
                notify.send("حالة الرصد", "التابلت رجع يشتغل، والرصد الاحتياطي توقف.", notify.QUIET)
        except Exception:
            pass


def test():
    """فحص سريع لكل جزء ويرسل إشعار تجربة واحد."""
    out = []
    for name in config.SOURCES:
        try:
            prim, _ = SOURCES[name]
            r = prim(now() - timedelta(hours=24))
            items = r[0] if isinstance(r, tuple) else r
            out.append(f"✔ {NAMES[name]}: {len(items)}")
        except Exception as e:
            out.append(f"✖ {NAMES[name]}: {str(e)[:60]}")
    try:
        res, used = llm.classify([{"platform": "x", "author": "test", "text": "شكرا للهلال الأحمر السعودي على سرعة الاستجابة في الرياض", "quoted": ""}])
        out.append(f"✔ التصنيف ({', '.join(used)}): {res[0]['relevance']}")
    except Exception as e:
        out.append(f"✖ التصنيف: {e}")
    out.append(("✔" if sheet.enabled() else "—") + " الجدول")
    msg = "\n".join(out)
    print(msg)
    notify.send("اختبار رصد الهلال", msg, notify.QUIET)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    if cmd == "run":
        server_returned_check()
        run()
    elif cmd in ("daily", "weekly", "monthly"):
        print(reports.report(cmd))
    elif cmd == "test":
        test()
    elif cmd == "should-backup":  # للتشغيل الاحتياطي: خروج 0 = السيرفر غائب
        st = sheet.get_status() if sheet.enabled() else {}
        last = parse_dt(st.get("last_run")) if st.get("last_run") else None
        sys.exit(0 if (not last or now() - last >= timedelta(minutes=75) or st.get("runner") == "backup") else 1)
    elif cmd == "backup-loop":
        backup_loop()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
