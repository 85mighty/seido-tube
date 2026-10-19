#!/usr/bin/env bash
# 한 편 끝까지: 큐 → 대본 → 캐릭터 → 음성 → 렌더 → (unlisted 업로드 + Telegram 승인요청)
# usage: ./run_pipeline.sh            # 큐의 다음 todo 1건
#        ./run_pipeline.sh --row 3    # 특정 행
#        승인 후:  python3 scripts/07_upload.py work/<slug> --publish && python3 scripts/08_blog_post.py work/<slug> --wp --hatena
set -euo pipefail
cd "$(dirname "$0")"
set -a; [ -f .env ] && source .env; set +a

OUT=$(python3 scripts/04_script_gen.py --minutes "${MINUTES:-10}" "$@")
echo "$OUT"
SLUG=$(echo "$OUT" | head -1)
WD="work/$SLUG"

python3 scripts/06a_images.py "$WD"
python3 scripts/05_tts.py "$WD"
python3 scripts/06_render.py "$WD"
python3 scripts/07_upload.py "$WD"
echo "DONE $WD  → Telegram 확인 후 --publish"
