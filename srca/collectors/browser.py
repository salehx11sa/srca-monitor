import glob
import os
from contextlib import contextmanager

from ..util import UA

# إعدادات اختيارية من .env (للأجهزة الخاصة مثل التابلت):
#   CHROME_PATH  مسار متصفح بديل
#   CHROME_ARGS  خيارات إضافية مفصولة بمسافة (مثل: --single-process --disable-gpu)
#   CHROME_CDP   رابط متصفح شغّال مسبقًا (مثل: http://127.0.0.1:9222) — يُستخدم بدل تشغيل متصفح جديد


@contextmanager
def chrome(cookies=None):
    """كروم كامل بوضع headless=new (نسخة headless-shell يرفضها X برمز 403)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        cdp = os.environ.get("CHROME_CDP", "").strip()
        if cdp:
            # متصفح شغّال مسبقًا (وضع العملية الواحدة لا يدعم نوافذ خاصة جديدة، فنستخدم نافذته الأساسية)
            b = p.chromium.connect_over_cdp(cdp, timeout=60000)
            ctx = b.contexts[0] if b.contexts else b.new_context()
            before = set(ctx.pages)
            if cookies:
                ctx.add_cookies(cookies)
            try:
                yield ctx
            finally:
                for pg in ctx.pages:
                    if pg not in before:
                        try:
                            pg.close()
                        except Exception:
                            pass
            return
        exe = os.environ.get("CHROME_PATH") or (glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome") or [None])[0]
        kw = {"executable_path": exe} if exe else {}
        extra = os.environ.get("CHROME_ARGS", "").split()
        b = p.chromium.launch(headless=False, args=["--headless=new", "--disable-blink-features=AutomationControlled",
                                                     "--no-sandbox", "--no-zygote", "--disable-dev-shm-usage"] + extra, **kw)
        ctx = b.new_context(user_agent=UA, locale="ar-SA", timezone_id="Asia/Riyadh",
                            viewport={"width": 1280, "height": 900})
        if cookies:
            ctx.add_cookies(cookies)
        try:
            yield ctx
        finally:
            b.close()
