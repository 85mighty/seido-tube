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

# yt-dlp 봇 차단 회피: 기존 bgutil-pot 가 있으면 PO token provider 사용
if [ -d /root/bgutil-pot ]; then
  pip install -q --break-system-packages bgutil-ytdlp-pot-provider 2>/dev/null || pip install -q bgutil-ytdlp-pot-provider || true
fi

bash vps/benchmark_sync.sh
echo "bootstrap done. 다음: nano /root/seido-tube/.env (키 입력) → ./run_pipeline.sh"
