#!/usr/bin/env bash
# VPS 1회 셋업 + 첫 벤치마크 수집.  VPS(root)에서 그대로 붙여넣기:
#   curl -fsSL https://raw.githubusercontent.com/85mighty/seido-tube/main/vps/bootstrap.sh | bash
set -euo pipefail
cd /root
[ -d seido-tube ] || git clone https://github.com/85mighty/seido-tube.git
cd seido-tube && git pull --ff-only

pip install -q --break-system-packages -U yt-dlp pyyaml anthropic playwright pillow google-api-python-client google-auth-oauthlib 2>/dev/null \
  || pip install -q -U yt-dlp pyyaml anthropic playwright pillow google-api-python-client google-auth-oauthlib
python3 -m playwright install chromium >/dev/null 2>&1 || true
python3 -m playwright install-deps >/dev/null 2>&1 || true
command -v ffmpeg >/dev/null || apt-get install -y -qq ffmpeg
fc-list | grep -qi "noto sans cjk" || apt-get install -y -qq fonts-noto-cjk
[ -f .env ] || cp .env.example .env

# yt-dlp 봇 차단 회피: bgutil PO token 서버(:4416) + yt-dlp 플러그인
pip install -q --break-system-packages bgutil-ytdlp-pot-provider 2>/dev/null || pip install -q bgutil-ytdlp-pot-provider || true
if [ -d /root/bgutil-pot/server ] && ! curl -s --max-time 3 http://127.0.0.1:4416/ping >/dev/null; then
  ( cd /root/bgutil-pot/server && [ -f build/main.js ] || { npm install --silent && npx tsc; } ) || true
  pm2 describe bgutil-pot >/dev/null 2>&1 || pm2 start /root/bgutil-pot/server/build/main.js --name bgutil-pot >/dev/null && pm2 save >/dev/null || true
  sleep 2
fi
curl -s --max-time 3 http://127.0.0.1:4416/ping >/dev/null && echo "bgutil PO token server: up" || echo "bgutil PO token server: not running (자막은 config/cookies.txt 필요)"

bash vps/benchmark_sync.sh
echo "bootstrap done. 다음: nano /root/seido-tube/.env (키 입력) → ./run_pipeline.sh"
