#!/usr/bin/env bash
# تركيب رصد الهلال على سيرفر Oracle (Ubuntu 22.04/24.04 — ARM أو x86) بأمر واحد:
#   curl -fsSL <رابط هذا الملف الخام> | sudo bash -s -- <رابط المستودع مع رمز الوصول>
# أو بعد نسخ المستودع:  sudo bash deploy/install.sh
set -euo pipefail
REPO_URL="${1:-}"
APP=/opt/srca-monitor
USER_NAME=srca

echo "== تجهيز النظام =="
apt-get update -y
DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-venv python3-pip git sqlite3 curl
timedatectl set-timezone Asia/Riyadh || true
id -u $USER_NAME >/dev/null 2>&1 || useradd -r -m -d /home/$USER_NAME -s /bin/bash $USER_NAME

echo "== الكود =="
if [ -n "$REPO_URL" ]; then
  [ -d $APP/.git ] && git -C $APP pull --ff-only || git clone "$REPO_URL" $APP
elif [ ! -d $APP ]; then
  cp -r "$(cd "$(dirname "$0")/.." && pwd)" $APP
fi
chown -R $USER_NAME:$USER_NAME $APP

echo "== البيئة =="
sudo -u $USER_NAME python3 -m venv $APP/.venv
sudo -u $USER_NAME $APP/.venv/bin/pip install -q --upgrade pip
sudo -u $USER_NAME $APP/.venv/bin/pip install -q -r $APP/requirements.txt
$APP/.venv/bin/python -m playwright install-deps chromium
sudo -u $USER_NAME $APP/.venv/bin/python -m playwright install chromium

if [ ! -f $APP/.env ]; then
  cp $APP/.env.example $APP/.env; chown $USER_NAME:$USER_NAME $APP/.env; chmod 600 $APP/.env
  echo "!! املأ المفاتيح في $APP/.env ثم أعد تشغيل: sudo systemctl start srca-run.service"
fi

echo "== الجدولة =="
mk() { # name, schedule, args
cat > /etc/systemd/system/srca-$1.service <<EOF
[Unit]
Description=SRCA monitor $1
After=network-online.target
[Service]
Type=oneshot
User=$USER_NAME
WorkingDirectory=$APP
ExecStartPre=-/usr/bin/git -C $APP pull --ff-only -q
ExecStart=$APP/.venv/bin/python -m srca.main $3
TimeoutStartSec=1500
Nice=5
EOF
cat > /etc/systemd/system/srca-$1.timer <<EOF
[Unit]
Description=SRCA monitor $1 timer
[Timer]
OnCalendar=$2
Persistent=true
RandomizedDelaySec=60
[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload; systemctl enable --now srca-$1.timer
}
mk run "*:05,35" run                     # كل 30 دقيقة
mk daily "*-*-* 08:00:00" daily          # الملخص اليومي 8 صباحًا (توقيت الرياض)
mk weekly "Sun *-*-* 08:10:00" weekly    # الأحد
mk monthly "*-*-01 08:20:00" monthly     # أول كل شهر

echo "== تم. اختبار سريع: =="
sudo -u $USER_NAME $APP/.venv/bin/python -m srca.main test || true
systemctl list-timers 'srca-*' --no-pager
