#!/usr/bin/env bash
# 벤치마크 수집 → 자막 구조 분석 → 랭킹 재계산 → GitHub 푸시.  주 1회 cron 권장:
#   (crontab -l; echo "30 4 * * 6 /root/seido-tube/vps/benchmark_sync.sh >> /root/seido-tube/data/sync.log 2>&1") | crontab -
# (토요일 04:30 JST = 금요 19:00 업로드 후 하루 지난 시점의 조회수 반영)
set -euo pipefail
cd "$(dirname "$0")/.."
git pull --ff-only -q || true
set -a; [ -f .env ] && source .env; set +a

CHANNEL="${BENCH_CHANNEL:-https://www.youtube.com/@ryonurse}"
echo "== $(date '+%F %T') collect $CHANNEL"
python3 scripts/01_collect_channel.py --channel "$CHANNEL" --subs-top "${SUBS_TOP:-30}"
python3 scripts/02_analyze_transcripts.py || echo "(transcript analysis skipped)"
python3 -I analysis/analyze_titles.py >/dev/null
python3 scripts/03_topic_queue.py --n 8 || echo "(queue skipped)"

# 말속도(자/분) → .env CHARS_PER_MIN 자동 갱신
CPM=$(grep -oP '말속도 중앙값: \K[0-9]+' analysis/structure.md 2>/dev/null || true)
if [ -n "${CPM:-}" ]; then
  grep -q '^CHARS_PER_MIN=' .env && sed -i "s/^CHARS_PER_MIN=.*/CHARS_PER_MIN=$CPM/" .env || echo "CHARS_PER_MIN=$CPM" >> .env
fi

# 결과 커밋 (자막 원문은 제외, 분석 결과와 메타만)
git add data/channel_videos.csv data/channel_videos.json analysis/*.md analysis/*.csv data/queue.csv 2>/dev/null || true
git -c user.name=vps -c user.email=vps@seido-note.com commit -qm "benchmark sync $(date '+%F')" || { echo "no changes"; exit 0; }
git push -q origin main && echo "pushed"
