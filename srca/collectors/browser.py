import glob
from contextlib import contextmanager

from ..util import UA


@contextmanager
def chrome(cookies=None):
    """كروم كامل بوضع headless=new (نسخة headless-shell يرفضها X برمز 403)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        exe = (glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome") or [None])[0]
        kw = {"executable_path": exe} if exe else {}
        b = p.chromium.launch(headless=False, args=["--headless=new", "--disable-blink-features=AutomationControlled",
                                                     "--no-sandbox", "--disable-dev-shm-usage"], **kw)
        ctx = b.new_context(user_agent=UA, locale="ar-SA", timezone_id="Asia/Riyadh",
                            viewport={"width": 1280, "height": 900})
        if cookies:
            ctx.add_cookies(cookies)
        try:
            yield ctx
        finally:
            b.close()
