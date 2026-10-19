# seido-tube — 일본 年金・給付金 롱폼 YouTube 자동화

벤치마크: [節約看護師りょう](https://www.youtube.com/@ryonurse) (구독 74.6만 / 161본 / 매주 금 19:00 / 24〜41분)
분석 결과: `analysis/summary.md` · 토픽 설정: `config/topics.yaml`

## 파이프라인

```
01 collect   yt-dlp → 벤치마크 전체 메타 + 자막          (VPS, 주 1회 cron)
02 analyze   자막 → 길이/말속도/훅/CTA 타이밍 → structure.md
03 queue     랭킹 × 시즌캘린더 × seido-note 글 매칭 → data/queue.csv
04 script    Claude → script.json (대본 + 슬라이드 스펙 + 썸네일 + 블로그 메타)
06a images   캐릭터 일러스트 생성/캐시 → assets/library/characters/
05 tts       ElevenLabs 섹션별 mp3 + timing.json
06 render    HTML 슬라이드(표·콜아웃·2분할비교·타임라인·막대) → PNG → ffmpeg → final.mp4
             └ 모든 슬라이드 PNG + manifest.json → assets/<slug>/   ← 블로그 재사용 자산
07 upload    unlisted 업로드 + 썸네일 → Telegram 승인요청 → --publish 로 금 19:00 예약공개
08 blog      Claude → 기사 HTML → WP 미디어 업로드 → seido-note.com + seido-note.hatenablog.com
```

하루 운영: `./run_pipeline.sh` 1회 → Telegram 미리보기 확인 → `--publish` → `08_blog_post.py --wp --hatena`
(수동 입력은 승인 1번 = 목표 10〜15분 이내)

## VPS 셋업 (1회) — 한 줄

```bash
curl -fsSL https://raw.githubusercontent.com/85mighty/seido-tube/main/vps/bootstrap.sh | bash
```
클론 → 의존성 → 벤치마크 161편 수집(현재 조회수·길이·자막 30편) → 구조분석 → 랭킹 재계산 → `.env`의 CHARS_PER_MIN 자동 반영 → 결과를 GitHub에 푸시.
이후 매주 토요일 새벽(JST) 자동 갱신 (VPS는 UTC):
```bash
(crontab -l; echo "30 19 * * 5 /root/seido-tube/vps/benchmark_sync.sh >> /root/seido-tube/data/sync.log 2>&1") | crontab -
```
푸시가 거절되면 VPS의 GitHub 인증 방식에 맞춰 `git remote set-url origin git@github.com:85mighty/seido-tube.git`.
**봇 차단 대응**: 채널 목록(조회수·길이)은 차단 없이 수집됨. 업로드일·좋아요는 `.env`에 `YOUTUBE_API_KEY`(Cloud Console → API 키, YouTube Data API v3)를 넣으면 API로 가져옴(차단 무관). 자막은 bgutil PO token 서버(:4416, bootstrap이 pm2로 띄움) 또는 Chrome에서 내보낸 `config/cookies.txt`(확장 "Get cookies.txt LOCALLY", youtube.com 로그인 상태) 중 하나가 필요.

### 수동 셋업

```bash
cd /root && git clone <repo> seido-tube && cd seido-tube
cp .env.example .env && nano .env
pip install yt-dlp pyyaml anthropic playwright google-api-python-client google-auth-oauthlib pillow
playwright install chromium && playwright install-deps
apt install -y fonts-noto-cjk            # 슬라이드/자막 일본어 폰트
# YouTube OAuth: Cloud Console → YouTube Data API v3 → OAuth 클라이언트(데스크톱) → config/client_secret.json
python3 scripts/07_upload.py --auth
# 벤치마크 수집 + 구조 분석
python3 scripts/01_collect_channel.py --channel https://www.youtube.com/@ryonurse --subs-top 30
python3 scripts/02_analyze_transcripts.py      # → analysis/structure.md, CHARS_PER_MIN 값 .env 에 반영
python3 scripts/03_topic_queue.py --month 11
```

## 슬라이드 타입 (벤치마크 화면 재현)

| kind | 재현 대상 |
|---|---|
| table + callout | 早見表 위에 노란 말풍선 + 빨간 숫자 (「61歳から70歳までに合計16万4,000円増える」형) |
| compare | 2분할: 좌 파랑「65歳 超大損」/ 우 빨강「？歳 最強」+ 캐릭터 표정 |
| timeline | 좌측 캐릭터 행 × 기간 컬럼 × 색 막대 (在職老齢年金 기준액 변천형) |
| bar / number / bullets / title | 금액 강조, 요점, 섹션 타이틀 |

캐릭터는 `assets/library/characters/<id>_<mood>.png` 에 한 번 생성 후 영구 재사용 (채널 통일감 + 비용 0).

## 디렉터리

```
analysis/   벤치마크 분석 (summary.md, videos.csv, topic_ranking.csv, title_patterns.csv)
config/     topics.yaml, client_secret.json(비공개), yt_token.json(비공개)
data/       yutura_raw.txt, channel_videos.*, subs/, queue.csv
templates/  script_prompt.md, slide.html
scripts/    01〜08
work/       <slug>/ script.json, audio/, frames/, final.mp4, thumbnail.png, youtube.json, article.json, blog.json
assets/     library/characters/, <slug>/{NNN_section_kind.png, thumbnail.png, manifest.json}
```

## 주의
- 대본·이미지는 벤치마크를 "구성"만 참고하고 문장/도판은 새로 생성 (프롬프트에 명시). 제도 숫자는 `notes.uncertain` 에 표시되므로 승인 시 확인.
- seido-note.com 은 현재 子育て支援 단일 카테고리 → 年金/給付金 카테고리 신설 후 `03_topic_queue.py` 매칭이 살아남.
