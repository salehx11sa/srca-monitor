"""الإعدادات: كل ما يتغير مكانه هنا أو في ملف .env — لا مفاتيح داخل الكود."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_env():
    p = Path(os.environ.get("SRCA_ENV", ROOT / ".env"))
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()
E = lambda k, d="": os.environ.get(k, d).strip()

DATA_DIR = Path(E("SRCA_DATA", str(ROOT / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "srca.db"
TZ = "Asia/Riyadh"
RUNNER = E("SRCA_RUNNER", "server")  # server | backup

# --- المفاتيح (كلها اختيارية؛ ما لا يوجد يُتجاوز ببديله) ---
X_AUTH_TOKEN = E("X_AUTH_TOKEN")
X_CT0 = E("X_CT0")
X_AUTH_TOKEN_2 = E("X_AUTH_TOKEN_2")          # حساب X الاحتياطي (لاحقًا)
TIKTOK_COOKIES = E("TIKTOK_COOKIES")          # لم يعد مستخدمًا (تيك توك صار عبر Apify)
APIFY_TOKEN = E("APIFY_TOKEN")                # تيك توك عبر Apify (الخطة المجانية 5$ شهريًا)
GEMINI_KEY = E("GEMINI_API_KEY")
GEMINI_MODELS = [m for m in E("GEMINI_MODELS", "gemini-flash-latest,gemini-3.8-flash,gemini-3.5-flash,gemini-flash-lite-latest").split(",") if m]
GROQ_KEY = E("GROQ_API_KEY")
GROQ_MODELS = [m for m in E("GROQ_MODELS", "llama-3.3-70b-versatile,openai/gpt-oss-120b").split(",") if m]
PUSHOVER_TOKEN = E("PUSHOVER_TOKEN")
PUSHOVER_USER = E("PUSHOVER_USER")
TELEGRAM_BOT = E("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT = E("TELEGRAM_CHAT_ID")
SHEET_URL = E("SHEET_WEBAPP_URL")             # رابط Apps Script (الجدول + البريد + اللوحة)
SHEET_SECRET = E("SHEET_SECRET")
HEALTHCHECK_URL = E("HEALTHCHECK_URL")        # https://hc-ping.com/<uuid>
YOUTUBE_KEY = E("YOUTUBE_API_KEY")            # اختياري؛ بدونه نقرأ صفحة البحث
PLACES_KEY = E("GOOGLE_PLACES_KEY")           # اختياري؛ خرائط قوقل

INTERVAL_MIN = int(E("SRCA_INTERVAL_MIN", "30"))
X_PAGES_CAP = int(E("X_PAGES_CAP", "2"))

# --- المصادر المفعّلة في هذه المرحلة ---
SOURCES = [s for s in E("SRCA_SOURCES", "x,tiktok,news,youtube,telegram,apps,reddit,web,maps").split(",") if s]

# --- كلمات البحث العامة للمصادر غير X ---
CORE_TERMS = ['"الهلال الأحمر السعودي"', '"هيئة الهلال الأحمر"', '"Saudi Red Crescent"']
EXPERIENCE_TERMS = ['الإسعاف السعودية تجربتي', 'شكرا الهلال الأحمر', 'الهلال الأحمر تأخر الإسعاف']
# تيك توك: بالشكل اللي يكتبه الناس (بدون همزة)؛ كل الكلمات كل دورة، والرقم = عدد أحدث الفيديوهات لكل كلمة
TIKTOK_COUNTS = {"الهلال الاحمر السعودي": 2, "الهلال الاحمر": 3, "اسعاف الهلال الاحمر": 2, "مسعف الهلال الاحمر": 2}
TIKTOK_TERMS = list(TIKTOK_COUNTS)

# قنوات تيليجرام عامة (إخبارية) تُفحص بحثًا عن ذكر الهيئة — أضف ما تشاء
TELEGRAM_CHANNELS = [c for c in E("TELEGRAM_CHANNELS", "SaudiNews50,SPA_News,News_Ejazah,mediasrca,awamir_11,wadhefadotcom").split(",") if c]

# تطبيقات الهيئة في المتاجر
PLAY_APPS = [a for a in E("PLAY_APPS", "sahab.srca.firstresponder,com.srca.myservices").split(",") if a]

# مراكز للخرائط (تُستخدم فقط إذا وُجد مفتاح Places)
MAPS_QUERIES = ["الهلال الأحمر السعودي مركز إسعاف الرياض", "الهلال الأحمر السعودي جدة", "الهلال الأحمر السعودي الدمام"]

OFFICIAL_ACCOUNTS = ["mediasrca", "spokesman_srca", "MutaahebSA"]
