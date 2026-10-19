#!/usr/bin/env bash
# 기본: 큐 → 대본+슬라이드 생성 → 이미지만 렌더 → 패널에서 검수   (음성·영상은 패널의 버튼으로)
#   ./run_pipeline.sh            # 큐의 다음 todo 1건
#   ./run_pipeline.sh --row 3    # 특정 행
#   FULL=1 ./run_pipeline.sh     # 음성+영상(+업로드)까지 한 번에
set -euo pipefail
cd "$(dirname "$0")"
set -a; [ -f .env ] && source .env; set +a

OUT=$(python3 scripts/04_script_gen.py --minutes "${MINUTES:-20}" "$@")
echo "$OUT"
SLUG=$(echo "$OUT" | head -1)
WD="work/$SLUG"

if [ "${FULL:-0}" != "1" ]; then
  python3 scripts/06_render.py "$WD"
  echo "DONE (대본+이미지) → 패널에서 검수: http://$(hostname -I | awk '{print $1}'):${PANEL_PORT:-8085}/w/$SLUG"
  exit 0
fi
python3 scripts/05_tts.py "$WD"
python3 scripts/06_render.py "$WD"
if [ "${SKIP_UPLOAD:-0}" = "1" ] || [ ! -f config/client_secret.json ]; then
  echo "DONE $WD/final.mp4  (업로드 생략: config/client_secret.json 없음 또는 SKIP_UPLOAD=1)"
else
  python3 scripts/07_upload.py "$WD"
  echo "DONE $WD  → Telegram 확인 후 --publish"
fi
