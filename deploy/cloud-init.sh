#!/bin/bash
# سكربت التهيئة التلقائية لسيرفر Oracle — يُلصق كاملًا في:
# Create instance > Show advanced options > Management > Initialization script > Paste cloud-init script
# يركّب كل شيء بدون أي أوامر منك. استبدل القيم بين <> قبل اللصق (أو أرسلها لي وأجهزه لك).
set -e
REPO="https://<GITHUB_TOKEN>@github.com/salehx11sa/srca-monitor.git"
mkdir -p /opt && git clone "$REPO" /opt/srca-monitor 2>/dev/null || (apt-get update -y && apt-get install -y git && git clone "$REPO" /opt/srca-monitor)
cat > /opt/srca-monitor/.env <<'ENV'
<الصق هنا محتوى ملف .env كاملًا>
ENV
chmod 600 /opt/srca-monitor/.env
bash /opt/srca-monitor/deploy/install.sh > /var/log/srca-install.log 2>&1
