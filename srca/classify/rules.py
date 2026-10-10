"""القواعد: فرز أولي مجاني (منقول من أداة الجمع) + تصنيف احتياطي كامل إذا تعطل الذكاء الاصطناعي."""
import re

REL = re.compile(r"هلال|اسعاف|إسعاف|أسعف|اسعف|مسعف|المستجيب|سفير الحياة|سفيرة الحياة|الروابط العائلية|الثمان الأولى|متأهب|"
                 r"mutaaheb|mediasrca|spokesman_srca|red crescent|ambulance|paramedic", re.I)
FOREIGN = re.compile(r"فلسطين|غزة|غزه|الاحتلال|خان ?يونس|الضفة|اليمن|اليمني|صنعاء|السودان|لبنان|سوريا|السوري|العراق|ايران|إيران|"
                     r"مصر|المصري|الأردن|الاردن|ليبيا|تركيا|القطري|الإماراتي|الاماراتي|الإمارات|الامارات|أبوظبي|ابوظبي|دبي|زايد|"
                     r"الكويتي|البحريني|العماني|المغرب|الجزائر|تونس|الحوثي|القدس|جنين|نابلس|رفح|الإسرائيلي|الاسرائيلي|بيروت|الخرطوم|عدن|"
                     r"Gaza|Israel|Iran|Lebanon|Sudan|Yemen|Syria|Egypt|Emirates|UAE|Qatar", re.I)
SAUDI = re.compile(r"السعودي|السعودية|المملكة|الرياض|جدة|جده|مكة|مكه|المدينة|الدمام|الخبر|القصيم|بريدة|أبها|ابها|خميس مشيط|تبوك|"
                   r"حائل|جازان|جيزان|نجران|الطائف|الأحساء|الاحساء|الجوف|عرعر|الباحة|ينبع|القطيف|الجبيل|حفر الباطن|سكاكا|القريات|"
                   r"997|هيئة الهلال|mediasrca|spokesman_srca|Saudi|KSA|Riyadh|Jeddah|Makkah|Mecca|Dammam", re.I)
PERSIAN = re.compile(r"[پچژگ]|ی")

EXPLICIT = re.compile(r"الهلال ال[أا]حمر السعودي|هي[ئی]ة الهلال ال[أا]حمر السعودي|Saudi Red ?Crescent|#الهلال_ال[أا]حمر_السعودي|"
                      r"@?mediasrca|@?spokesman_srca|@?MutaahebSA|srca\.gov\.sa", re.I)
HAYAH = re.compile(r"هي[ئی]ة الهلال|الهلال ال[أا]حمر|فرق الهلال|فرقة الهلال|مسعفي الهلال|متطوعي الهلال", re.I)
PROGRAMS = re.compile(r"المستجيب الأول|برنامج المستجيب|سفير(?:ة)? الحياة|سفراء الحياة|إعادة الروابط العائلية|اعادة الروابط العائلية|"
                      r"الثمان الأولى|المسعف الصغير|منصة متأهب|الإسعاف الجوي|الاسعاف الجوي", re.I)
EXPERIENCE = re.compile(r"تجربتي|قصتي|صار لي|صار لنا|حصل لي|جونا|نقلوني|نقلوا|أسعفوا|اسعفوا|انقذوا|أنقذوا|اتصلت|اتصلنا|طلبت|طلبنا|"
                        r"أمي|امي|أبوي|ابوي|الوالد|الوالدة|جدتي|جدي|ولدي|بنتي|زوجتي|اخوي|أخوي", re.I)
AMBUL = re.compile(r"الاسعاف|الإسعاف|اسعاف|إسعاف|المسعف|مسعف|997", re.I)
EXCLUDE = re.compile(r"اسعاف مسعوف|اسعفني بفكرة|نادي الهلال|#الهلال\b(?!_الأحمر)|GTA|RP\b|سيرفر|نهر الحياة|هيئة_الهلال_الأحمر_الإماراتي", re.I)
NEG = re.compile(r"تأخر|تأخروا|ما جوا|ماجو|محد رد|ما ردوا|انتظرنا|انتظرت|رفضوا|سوء تعامل|شكوى|إهمال|اهمال|توفي|توفى|مات|وفاة|"
                 r"للأسف|للاسف|فاتور|تدفع|ما فيه فايدة|سيء|سيئ|زفت|فاشل|حسبي الله|\b1★", re.I)
SEVERE = re.compile(r"توفي|توفى|مات|وفاة|إهمال|اهمال|رفضوا|ما جوا|ماجو|سوء تعامل|حسبي الله", re.I)
POS = re.compile(r"ما قصروا|ماقصروا|بيض الله|يعطيهم العافية|الله يجزاهم|شكرا|شكراً|أشكر|اشكر|كل الشكر|سرعة الاستجابة|حسن التعامل|"
                 r"طمنونا|أبطال|ابطال|فخر|ممتاز|رائع|\b5★", re.I)
NEWSY = re.compile(r"يباشر|باشر|بلاغ|بلاغات|يدشن|دشن|توقيع|مذكرة|اتفاقية|ورشة|دورة|تدريب|تكريم|يستقبل|استقبل|وكالة الأنباء|واس", re.I)


def blob(it):
    return f"{it.get('text', '')} {it.get('quoted', '')} {it.get('author', '')}"


def prefilter(it, blocked_authors=()):
    """يستبعد الواضح فقط. يرجع (يبقى؟، السبب)."""
    s = blob(it)
    if it.get("author", "").lower() in blocked_authors:
        return False, "حساب استبعدته أنت سابقًا"
    if re.search(r"mediasrca|spokesman_srca|MutaahebSA", s, re.I):
        return True, ""  # الإشارة للحساب الرسمي تُراجع دائمًا (درس من أداة الجمع)
    if it.get("platform") == "app":
        return True, ""  # تقييمات تطبيقات الهيئة متعلقة بطبيعتها
    if not REL.search(s):
        return False, "لا ذكر للهلال أو الإسعاف"
    if PERSIAN.search(s) and "ة" not in s:
        return False, "نص فارسي"
    if FOREIGN.search(s) and not SAUDI.search(s):
        return False, "سياق خارج السعودية"
    if EXCLUDE.search(s) and not EXPLICIT.search(s):
        return False, "تعبير عامي أو جهة أخرى"
    return True, ""


def classify(it):
    """تصنيف احتياطي بالقواعد (أقل دقة من الذكاء الاصطناعي، لكنه لا يتوقف)."""
    s = blob(it)
    saudi = bool(SAUDI.search(s))
    foreign = bool(FOREIGN.search(s))
    if it.get("platform") == "app" or EXPLICIT.search(s) or (HAYAH.search(s) and saudi and not foreign) or \
            (PROGRAMS.search(s) and saudi):
        rel = "مؤكد"
    elif HAYAH.search(s) and not foreign:
        rel = "محتمل"
    elif saudi and AMBUL.search(s) and EXPERIENCE.search(s) and not foreign:
        rel = "محتمل"
    else:
        rel = "مستبعد"
    neg, pos = bool(NEG.search(s)), bool(POS.search(s))
    sent = "مختلط" if neg and pos else "سلبي" if neg else "إيجابي" if pos else "محايد"
    if it.get("platform") == "news" or (NEWSY.search(s) and not EXPERIENCE.search(s)):
        ctype = "خبر"
    elif re.search(r"أمي|امي|أبوي|ابوي|الوالد|الوالدة|جدتي|جدي|ولدي|بنتي|زوجتي|اخوي|أخوي", s):
        ctype = "تجربة منقولة عن قريب"
    elif EXPERIENCE.search(s):
        ctype = "تجربة شخصية"
    elif "؟" in s or "?" in s:
        ctype = "استفسار/مقترح"
    else:
        ctype = "رأي عام"
    if rel == "مؤكد" and SEVERE.search(s):
        pri = "عاجل"
    elif rel == "مؤكد" and (neg or (pos and ctype != "خبر")):
        pri = "مهم"
    elif rel == "محتمل" and (neg or pos) and EXPERIENCE.search(s):
        pri = "مهم"
    else:
        pri = "اعتيادي"
    txt = re.sub(r"https?://\S+", "", it.get("text", "")).strip().replace("\n", " ")
    return {"relevance": rel, "priority": pri if rel != "مستبعد" else "", "sentiment": sent if rel != "مستبعد" else "",
            "ctype": ctype if rel != "مستبعد" else "", "summary": txt[:140],
            "reason": "تصنيف آلي بالقواعد (الذكاء الاصطناعي غير متاح)", "region": "", "classifier": "rules"}
