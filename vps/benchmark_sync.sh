#!/usr/bin/env bash
# 벤치마크 수집 → 자막 구조 분석 → 랭킹 재계산 → GitHub 푸시.  주 1회 cron 권장:
#   (crontab -l; echo "30 19 * * 5 /root/seido-tube/vps/benchmark_sync.sh >> /root/seido-tube/data/sync.log 2>&1") | crontab -
# (VPS는 UTC: 금 19:30 UTC = 토 04:30 JST, 금요 19:00 JST 업로드 후 하루 지난 조회수 반영)
set -euo pipefail
cd "$(dirname "$0")/.."
git pull --ff-only -q || true
set -a; [ -f .env ] && source .env; set +a

CHANNEL="${BENCH_CHANNEL:-https://www.youtube.com/@ryonurse}"
echo "== $(date '+%F %T') collect $CHANNEL"
python3 scripts/01_collect_channel.py --channel "$CHANNEL" --subs-top "${SUBS_TOP:-30}" || echo "(collect partial)"
python3 scripts/02_analyze_transcripts.py || echo "(transcript analysis skipped)"
python3 -I analysis/analyze_titles.py >/dev/null
python3 scripts/03_topic_queue.py --n 8 || echo "(queue skipped)"

# (CHARS_PER_MIN 은 TTS 실측 pace 기준이라 여기서 덮어쓰지 않음. 벤치마크 진행자 속도는 analysis/structure.md 참고)

# 결과 커밋 (자막 원문은 제외, 분석 결과와 메타만)
git add data/channel_videos.csv data/channel_videos.json analysis/*.md analysis/*.csv data/queue.csv 2>/dev/null || true
git -c user.name=vps -c user.email=vps@seido-note.com commit -qm "benchmark sync $(date '+%F')" || { echo "no changes"; exit 0; }
git push -q origin main && echo "pushed"
