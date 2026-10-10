#!/data/data/com.termux/files/usr/bin/bash
# تركيب رصد الهلال على تابلت أندرويد (Termux) — يصير التابلت هو «السيرفر» الأساسي.
# الأمر الوحيد المطلوب داخل Termux:
#   curl -fsSL https://raw.githubusercontent.com/salehx11sa/srca-monitor/main/deploy/tablet.sh | bash
#
# ما يسويه:
#  - بيئة لينكس (Debian) معزولة داخل Termux فيها متصفح خاص بالرصد (لا يلمس كروم التابلت).
#  - الرصد كل 30 دقيقة (:05 و:35)، الملخص اليومي 8:00، الأسبوعي الأحد 8:10، الشهري أول الشهر 8:20 — بتوقيت الرياض.
#  - تشغيل تلقائي بعد إعادة الإقلاع عبر ملف مستقل: ~/.termux/boot/srca-boot.sh
# ما لا يلمسه أبدًا: tyworker.py · tyhelper.dex · .tyworker.json · tyw-*.sh · boot/tyw-boot.sh · crontab · كروم.
set -e
R=https://github.com/salehx11sa/srca-monitor.git
D=debian   # متصفح Debian الرسمي يُنزّل من نفس خوادم البرامج (أثبت من خادم Playwright على شبكة البيت)
say() { printf '\n\033[1;32m== %s ==\033[0m\n' "$1"; }

say "1/5 تجهيز Termux"
dpkg --configure -a >/dev/null 2>&1 || true
pkg update -y >/dev/null 2>&1 || true
pkg install -y proot-distro git curl util-linux procps x11-repo >/dev/null
pkg install -y chromium >/dev/null

say "2/5 بيئة لينكس (أول مرة تاخذ 5-10 دقائق)"
proot-distro login $D -- true >/dev/null 2>&1 || proot-distro install $D
IN() { proot-distro login $D --shared-tmp -- bash -lc "$1"; }

say "3/5 الكود والمتصفح (10-20 دقيقة)"
IN "export DEBIAN_FRONTEND=noninteractive TZ=Asia/Riyadh
apt-get update -y >/dev/null && apt-get install -y -o Acquire::Retries=10 python3 python3-venv python3-pip git tzdata >/dev/null
[ -d /root/srca-monitor/.git ] && git -C /root/srca-monitor pull -q --ff-only || git clone -q $R /root/srca-monitor
cd /root/srca-monitor && python3 -m venv .venv && .venv/bin/pip install -q --upgrade pip && .venv/bin/pip install -q -r requirements.txt
echo 'الكود جاهز'"

say "4/5 المفاتيح"
if ! IN "grep -q '^X_AUTH_TOKEN=' /root/srca-monitor/.env 2>/dev/null"; then
  echo "الصق محتوى ملف «مفاتيح-التابلت.txt» كاملًا، ثم اضغط Enter، ثم CTRL ثم d:"
  proot-distro login $D -- bash -c "cat > /root/srca-monitor/.env; chmod 600 /root/srca-monitor/.env" < /dev/tty
fi
IN "cd /root/srca-monitor && grep -q '^X_AUTH_TOKEN=' .env || { echo '!! المفاتيح ناقصة. أعد التشغيل والصقها كاملة.'; rm -f .env; exit 1; }
grep -q '^SRCA_RUNNER=' .env || echo SRCA_RUNNER=server >> .env
sed -i '/^CHROME_PATH=/d' .env; grep -q '^CHROME_CDP=' .env || echo CHROME_CDP=http://127.0.0.1:9222 >> .env"

say "5/5 الجدولة"
pkill -f srca-loop.sh 2>/dev/null || true
cat > ~/srca-chrome.sh <<'CHR'
#!/data/data/com.termux/files/usr/bin/bash
# متصفح الرصد الخاص (Chromium من Termux، مستقل عن كروم التابلت) — يُشغَّل إذا كان متوقفًا.
curl -s -m 5 http://127.0.0.1:9222/json/version >/dev/null 2>&1 && exit 0
pkill -f "remote-debugging-port=9222" 2>/dev/null; sleep 2
setsid nohup chromium-browser --headless=new --no-sandbox --no-zygote --single-process --disable-gpu \
  --remote-debugging-port=9222 --user-data-dir=$HOME/.srca-chrome about:blank > ~/srca-chrome.log 2>&1 &
for i in $(seq 1 20); do sleep 2; curl -s -m 3 http://127.0.0.1:9222/json/version >/dev/null 2>&1 && exit 0; done
exit 1
CHR
chmod +x ~/srca-chrome.sh
cat > ~/srca-loop.sh <<'LOOP'
#!/data/data/com.termux/files/usr/bin/bash
# مجدول رصد الهلال — نسخة واحدة فقط تعمل (قفل)، ولا يلمس أي مهمة أخرى على التابلت.
exec 9>~/.srca-loop.lock
flock -n 9 || exit 0
export TZ=Asia/Riyadh
run() { # $1 = run|daily|weekly|monthly
  ~/srca-chrome.sh
  proot-distro login debian --shared-tmp -- bash -lc \
    "cd /root/srca-monitor && git pull -q --ff-only 2>/dev/null; TZ=Asia/Riyadh timeout 1500 .venv/bin/python -m srca.main $1" \
    >> ~/srca-$1.log 2>&1
  tail -n 400 ~/srca-$1.log > ~/srca-$1.log.tmp && mv ~/srca-$1.log.tmp ~/srca-$1.log
}
last=""
while true; do
  now=$(date +%H:%M); dow=$(date +%u); dom=$(date +%d)
  if [ "$now" != "$last" ]; then
    last=$now
    case "$now" in
      08:00) run daily ;;
      08:10) [ "$dow" = 7 ] && run weekly ;;
      08:20) [ "$dom" = 01 ] && run monthly ;;
    esac
    case "${now#*:}" in 05|35) run run ;; esac
  fi
  sleep 20
done
LOOP
chmod +x ~/srca-loop.sh
mkdir -p ~/.termux/boot
cat > ~/.termux/boot/srca-boot.sh <<'BOOT'
#!/data/data/com.termux/files/usr/bin/bash
termux-wake-lock 2>/dev/null
sleep 60
setsid nohup ~/srca-loop.sh >/dev/null 2>&1 < /dev/null &
BOOT
chmod +x ~/.termux/boot/srca-boot.sh
termux-wake-lock 2>/dev/null || true
pgrep -f srca-loop.sh >/dev/null || setsid nohup ~/srca-loop.sh >/dev/null 2>&1 < /dev/null &
sleep 2; pgrep -f srca-loop.sh >/dev/null && echo "✔ الجدولة شغّالة" || echo "!! الجدولة ما اشتغلت"

~/srca-chrome.sh && echo "✔ متصفح الرصد شغّال" || echo "!! متصفح الرصد ما اشتغل"
say "تجربة (3-5 دقائق) — يوصلك إشعار هادئ على Pushover"
IN "cd /root/srca-monitor && TZ=Asia/Riyadh .venv/bin/python -m srca.main test" || true
echo
echo "✔ تم. الرصد شغّال كل 30 دقيقة. السجل: tail ~/srca-run.log"
