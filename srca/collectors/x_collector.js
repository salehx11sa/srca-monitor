// رصد الهلال الأحمر السعودي على X — أداة الجمع v3 (مستقلة، بلا Claude)
// مبنية على أداة-الجمع.js (v2، 2026-10-10). تُحقن في صفحة x.com مسجّلة الدخول. قراءة فقط: لا نشر ولا تفاعل.
// تلتقط رد SearchTimeline من XHR بعد التنقل الداخلي لصفحة «الأحدث»، وتتصفح للخلف بـ until_time.
(function () {
  if (window.SRCA && window.SRCA.v === 3) return;
  const S = window.SRCA = { v: 3, DB: {}, log: [], waiters: [], lastRL: null };
  if (!window.__srcaHook) {
    const oo = XMLHttpRequest.prototype.open, se = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function (m, u) { this.__u = u; return oo.apply(this, arguments); };
    XMLHttpRequest.prototype.send = function () {
      if (/SearchTimeline/.test(this.__u || '')) {
        this.addEventListener('loadend', () => {
          let j = null; try { j = JSON.parse(this.responseText); } catch (e) {}
          const rec = { j, status: this.status, rem: this.getResponseHeader('x-rate-limit-remaining'), reset: this.getResponseHeader('x-rate-limit-reset') };
          window.SRCA.lastRL = rec.rem + '/' + rec.reset;
          let v = {}; try { v = JSON.parse(new URL(this.__u, location.origin).searchParams.get('variables')); } catch (e) {}
          window.SRCA.waiters = window.SRCA.waiters.filter(w => { if (w.raw === v.rawQuery && !v.cursor) { w.res(rec); return false; } return true; });
        });
      }
      return se.apply(this, arguments);
    };
    window.__srcaHook = true;
  }
  S.parse = function (j) {
    const out = [];
    const walk = o => {
      if (!o || typeof o !== 'object') return; if (Array.isArray(o)) { o.forEach(walk); return; }
      if (o.itemType === 'TimelineTweet' && o.tweet_results) { let t = o.tweet_results.result; if (t && t.__typename === 'TweetWithVisibilityResults') t = t.tweet; if (t && t.legacy) out.push(t); return; }
      for (const k in o) walk(o[k]);
    };
    walk(j);
    return out.map(t => {
      const L = t.legacy, u = t.core?.user_results?.result;
      let q = t.quoted_status_result?.result; if (q && q.tweet) q = q.tweet;
      return {
        id: t.rest_id, sn: u?.core?.screen_name || u?.legacy?.screen_name, nm: u?.core?.name || u?.legacy?.name,
        vt: u?.legacy?.verified_type || '', loc: u?.location?.location || u?.legacy?.location || '', fo: u?.legacy?.followers_count,
        t: new Date(L.created_at).toISOString(), tx: (t.note_tweet?.note_tweet_results?.result?.text || L.full_text || ''),
        rp: L.in_reply_to_screen_name || '', rpId: L.in_reply_to_status_id_str || '', rt: !!L.retweeted_status_result,
        qt: q ? ('@' + (q.core?.user_results?.result?.core?.screen_name || q.core?.user_results?.result?.legacy?.screen_name) + ': ' + (q.note_tweet?.note_tweet_results?.result?.text || q.legacy?.full_text || '')) : '',
        md: (L.extended_entities?.media || []).map(m => m.type).join(','),
        m: { rep: L.reply_count, rt: L.retweet_count, like: L.favorite_count, q: L.quote_count, views: t.views?.count }
      };
    });
  };
  S.nav = function (raw) {
    const cur = new URLSearchParams(location.search).get('q'); if (cur === raw) raw = raw + ' -zzqxq';
    return new Promise(res => {
      S.waiters.push({ raw, res });
      history.pushState({}, '', '/search?q=' + encodeURIComponent(raw) + '&src=typed_query&f=live');
      dispatchEvent(new PopStateEvent('popstate', { state: {} }));
      setTimeout(() => res({ timeout: true }), 20000);
    });
  };
  const NEG = ' -صنعاء -غزة -الحوثي -الحوثيين -الاحتلال -قلقيلية -الإماراتي -اليمن';
  S.QS = {
    A: '"الهلال الأحمر السعودي" OR "الهلال الاحمر السعودي"',
    B: '"هيئة الهلال الأحمر" OR "هيئة الهلال الاحمر" OR "هيئة الهلال"',
    C: '#الهلال_الأحمر_السعودي OR #الهلال_الاحمر_السعودي OR #هيئة_الهلال_الأحمر',
    D: '"Saudi Red Crescent" OR "Saudi Redcrescent"',
    E: '@mediasrca OR to:mediasrca OR @spokesman_srca OR to:spokesman_srca',
    G: '(الاسعاف OR الإسعاف OR اسعاف OR إسعاف) (تجربتي OR قصتي OR "صار لي" OR "صار لنا" OR "حصل لي" OR جونا OR نقلوني OR نقلوا OR أسعفوا OR اسعفوا OR انقذوا OR أنقذوا OR أسعفني OR اسعفني)' + NEG,
    H: '(الاسعاف OR الإسعاف OR المسعفين OR المسعفون OR المسعف OR مسعفين) ("ما قصروا" OR "ماقصروا" OR "بيض الله" OR "يعطيهم العافية" OR "الله يجزاهم" OR "سرعة الاستجابة" OR "حسن التعامل" OR طمنونا)',
    I: '(الاسعاف OR الإسعاف) (تأخر OR تأخروا OR "ما جوا" OR ماجو OR "محد رد" OR "ما ردوا" OR انتظرنا OR انتظرت OR رفضوا OR "سوء تعامل" OR شكوى OR إهمال OR اهمال)' + NEG,
    J: '"اتصلت بالإسعاف" OR "اتصلت بالاسعاف" OR "اتصلنا بالاسعاف" OR "اتصلنا على الاسعاف" OR "اتصلت على الاسعاف" OR "دقيت على الاسعاف" OR "كلمت الاسعاف" OR "طلبت اسعاف" OR "طلبنا اسعاف" OR "طلبنا الاسعاف"',
    K: '997 (اسعاف OR إسعاف OR الهلال OR بلاغ OR اتصلت OR اتصلنا OR ردوا)',
    L: '"الإسعاف الجوي" OR "الاسعاف الجوي" OR "الإسعاف الطائر"',
    M: '"سفراء الحياة" OR "متطوعي الهلال" OR "متطوعين الهلال" OR "تطوع الهلال"',
    N: '(المسعفين OR المسعفون OR مسعف OR مسعفة OR مسعفين) (الهلال OR السعودية OR الرياض OR جدة OR مكة)' + NEG,
    P: '"سيارة الإسعاف" OR "سيارة الاسعاف" OR "سيارة اسعاف" OR "سيارات الإسعاف" OR "سيارات الاسعاف"' + NEG,
    Q: '"فرق الهلال" OR "فرقة الهلال" OR "فرق الإسعاف" OR "فرقة الإسعاف" OR "الفرق الإسعافية"' + NEG,
    R: '(أشكر OR شكرا OR شكراً OR "كل الشكر" OR "شكر خاص") (المسعفين OR المسعف OR "الهلال الأحمر" OR "الهلال الاحمر" OR الاسعاف OR الإسعاف)' + NEG,
    S: '(الاسعاف OR الإسعاف) (الرياض OR جدة OR مكة OR المدينة OR الدمام OR الخبر OR القصيم OR بريدة OR أبها OR خميس OR تبوك OR حائل OR جازان OR نجران OR الطائف OR الأحساء OR الجوف OR عرعر OR الباحة OR ينبع)' + NEG,
    T: '(الاسعاف OR الإسعاف OR اسعاف OR إسعاف OR المسعفين) (أمي OR امي OR أبوي OR ابوي OR الوالد OR الوالدة OR جدتي OR جدي OR ولدي OR بنتي OR زوجتي OR اخوي OR أخوي)' + NEG,
    U: '(ambulance OR paramedics OR "red crescent") (Saudi OR KSA OR Riyadh OR Jeddah OR Dammam OR Makkah) -Houthi -Houthis',
    V: '(أسعفني OR اسعفني) (تطبيق OR التطبيق OR الهلال OR بلاغ OR طلبت OR سجلت OR صحتي OR توكلنا)',
    W: '"المستجيب الأول" OR "برنامج المستجيب" OR "سفير الحياة" OR "سفيرة الحياة" OR "إعادة الروابط العائلية" OR "اعادة الروابط العائلية" OR "الثمان الأولى" OR @MutaahebSA OR to:MutaahebSA OR متأهب'
  };
  S.run = async function (CUT, opt = {}) {
    const cap = opt.pagesCap || 2, keys = opt.keys || Object.keys(S.QS);
    if (!S.queue || opt.reset) S.queue = keys.map(k => ({ k, until: null, pages: 0, got: 0, tries: 0 }));
    while (S.queue.length) {
      const it = S.queue[0];
      const raw = S.QS[it.k] + ' since_time:' + CUT + (it.until ? ' until_time:' + it.until : '');
      const r = await S.nav(raw);
      if (r.timeout) { if (++it.tries >= 3) { S.log.push({ k: it.k, status: 'TIMEOUT', pages: it.pages }); S.queue.shift(); } continue; }
      if (r.status === 429) return { stopped: '429', reset: r.reset, left: S.queue.map(i => i.k) };
      if (r.status !== 200 || !r.j) { if (++it.tries < 3) continue; S.log.push({ k: it.k, status: 'HTTP' + r.status, pages: it.pages }); S.queue.shift(); continue; }
      it.pages++;
      const tw = S.parse(r.j);
      for (const t of tw) {
        if (Date.parse(t.t) / 1000 < CUT) continue;
        if (!S.DB[t.id]) { t.qs = [it.k]; S.DB[t.id] = t; it.got++; } else if (!S.DB[t.id].qs.includes(it.k)) S.DB[t.id].qs.push(it.k);
      }
      const oldest = tw.length ? Math.floor(Math.min(...tw.map(t => Date.parse(t.t) / 1000))) : 0;
      const done = tw.length === 0 || oldest <= CUT || it.pages >= cap || (it.until && oldest >= it.until);
      if (done) { S.log.push({ k: it.k, pages: it.pages, got: it.got, status: tw.length === 0 ? 'end' : oldest <= CUT ? 'cut' : 'CAP' }); S.queue.shift(); }
      else it.until = oldest;
    }
    S.queue = null;
    return { stopped: 'DONE', total: Object.keys(S.DB).length, log: S.log };
  };
  S.all = () => Object.values(S.DB);
})();
