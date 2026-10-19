#!/usr/bin/env python3
"""VPS에서 실행: 벤치마크 채널 전체 메타데이터 + 상위 N개 자막(ja) 수집.
   YouTube 봇 차단("Sign in to confirm you're not a bot")을 피하기 위해 3단계로 수집:

   1) flat-playlist  (채널 목록 1회 요청) → id/제목/조회수/길이  ← 봇 차단 안 걸림. 이것만으로 랭킹 가능
   2) YouTube Data API v3 (env YOUTUBE_API_KEY 있으면) → 업로드일/좋아요/댓글/정확한 길이  ← 봇 차단 무관, 161편 = 4회 호출
      (없으면 yt-dlp 개별 요청으로 시도, 실패해도 계속 진행)
   3) 자막: yt-dlp + (bgutil PO token 서버 :4416 자동감지) + (config/cookies.txt 있으면 사용)  ← 실패하면 건너뜀

usage:
  python3 scripts/01_collect_channel.py --channel https://www.youtube.com/@ryonurse --subs-top 30
out:
  data/channel_videos.json / .csv,  data/subs/<id>.ja.vtt
"""
import argparse, csv, json, os, subprocess, sys, time, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"; SUBS = DATA / "subs"; SUBS.mkdir(parents=True, exist_ok=True)
COOKIES = ROOT / "config" / "cookies.txt"
SAMPLES = ["LBVUpvoz7zU", "9pPYufZza6Q"]

YTDLP_BASE = ["yt-dlp", "--no-warnings", "--extractor-args", "youtube:lang=ja", "--sleep-requests", "1.5"]
if COOKIES.exists():
    YTDLP_BASE += ["--cookies", str(COOKIES)]

def run(cmd, quiet=False):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 and not quiet:
        print("  !", r.stderr.strip().splitlines()[-1][:160] if r.stderr.strip() else "error", file=sys.stderr)
    return r.stdout if r.returncode == 0 else ""

# ---------- 1) flat list ----------
def flat_list(channel):
    out = run(YTDLP_BASE + ["--flat-playlist", "-J", f"{channel.rstrip('/')}/videos"])
    if not out:
        sys.exit("flat-playlist failed")
    rows = []
    for e in json.loads(out).get("entries", []):
        if e.get("id"):
            rows.append(dict(id=e["id"], title=e.get("title"), view_count=e.get("view_count"), duration=e.get("duration"),
                             upload_date=None, like_count=None, comment_count=None, chapters=[], description=""))
    return rows

# ---------- 2) metadata ----------
def api_meta(rows, key):
    by = {r["id"]: r for r in rows}
    ids = list(by)
    for i in range(0, len(ids), 50):
        q = urllib.parse.urlencode({"part": "snippet,statistics,contentDetails", "id": ",".join(ids[i:i+50]), "key": key, "hl": "ja"})
        with urllib.request.urlopen(f"https://www.googleapis.com/youtube/v3/videos?{q}", timeout=60) as r:
            for it in json.load(r).get("items", []):
                v = by[it["id"]]; sn, st, cd = it["snippet"], it.get("statistics", {}), it.get("contentDetails", {})
                v.update(title=sn.get("title") or v["title"], upload_date=sn["publishedAt"][:10].replace("-", ""),
                         view_count=int(st.get("viewCount", v["view_count"] or 0)), like_count=int(st["likeCount"]) if "likeCount" in st else None,
                         comment_count=int(st["commentCount"]) if "commentCount" in st else None, description=(sn.get("description") or "")[:1500],
                         duration=iso_dur(cd.get("duration")) or v["duration"])
        print(f"  api {min(i+50, len(ids))}/{len(ids)}")

def iso_dur(s):
    if not s: return None
    import re
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s)
    return int(m[1] or 0) * 3600 + int(m[2] or 0) * 60 + int(m[3] or 0)

def ytdlp_meta(v):
    out = run(YTDLP_BASE + ["-J", "--skip-download", f"https://www.youtube.com/watch?v={v['id']}"], quiet=True)
    if not out:
        return False
    d = json.loads(out)
    v.update(title=d.get("title") or v["title"], view_count=d.get("view_count") or v["view_count"], like_count=d.get("like_count"),
             comment_count=d.get("comment_count"), duration=d.get("duration") or v["duration"], upload_date=d.get("upload_date"),
             chapters=[(c.get("start_time"), c.get("title")) for c in (d.get("chapters") or [])], description=(d.get("description") or "")[:1500])
    return True

# ---------- 3) subs ----------
def fetch_subs(vid):
    if (SUBS / f"{vid}.ja.vtt").exists():
        return True
    out = subprocess.run(YTDLP_BASE + ["--skip-download", "--write-auto-sub", "--write-sub", "--sub-lang", "ja", "--sub-format", "vtt",
                                       "-o", str(SUBS / "%(id)s"), f"https://www.youtube.com/watch?v={vid}"], capture_output=True, text=True)
    return (SUBS / f"{vid}.ja.vtt").exists()

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", required=True); ap.add_argument("--subs-top", type=int, default=30)
    a = ap.parse_args()

    rows = flat_list(a.channel); print(f"{len(rows)} videos (flat)")
    key = os.getenv("YOUTUBE_API_KEY")
    if key:
        try:
            api_meta(rows, key); print("metadata via Data API")
        except Exception as e:
            print("Data API failed:", e)
    if not key or not any(r["upload_date"] for r in rows):
        ok = 0
        for i, v in enumerate(rows, 1):
            if ytdlp_meta(v):
                ok += 1
            elif i <= 3 and ok == 0:
                print("  yt-dlp per-video blocked (bot check). set YOUTUBE_API_KEY or config/cookies.txt for dates/likes/chapters"); break
        print(f"yt-dlp metadata ok: {ok}/{len(rows)}")

    rows.sort(key=lambda r: r["view_count"] or 0, reverse=True)
    (DATA / "channel_videos.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(DATA / "channel_videos.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["id", "upload_date", "duration", "view_count", "like_count", "comment_count", "title"])
        w.writeheader(); [w.writerow({k: r.get(k) for k in w.fieldnames}) for r in rows]
    print(f"saved {DATA/'channel_videos.csv'}")

    targets = [r["id"] for r in rows[: a.subs_top]] + [s for s in SAMPLES if s not in [r["id"] for r in rows[: a.subs_top]]]
    got = 0
    for i, vid in enumerate(targets, 1):
        if fetch_subs(vid):
            got += 1
        elif i == 3 and got == 0:
            print("subs blocked (bot check) → bgutil PO token 서버(:4416) 또는 config/cookies.txt 필요. 메타데이터는 저장됨."); break
        time.sleep(1)
    print(f"subs: {got}/{len(targets)} → {SUBS}")
