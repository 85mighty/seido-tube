#!/usr/bin/env python3
"""VPS에서 실행: 벤치마크 채널 전체 메타데이터 + 상위 N개 자막(ja) 수집.
   (클라우드 작업공간에서는 YouTube가 차단되어 있어 VPS에서만 동작)

usage:
  pip install yt-dlp
  python3 scripts/01_collect_channel.py --channel https://www.youtube.com/@ryonurse --subs-top 30
out:
  data/channel_videos.json  (id,title,view_count,duration,upload_date,like_count,chapters)
  data/channel_videos.csv
  data/subs/<id>.ja.vtt     (상위 N개 + 샘플 영상)
"""
import argparse, csv, json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"; SUBS = DATA / "subs"; SUBS.mkdir(parents=True, exist_ok=True)

SAMPLES = ["LBVUpvoz7zU", "9pPYufZza6Q"]   # 사용자가 지정한 샘플 영상

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-2000:], file=sys.stderr)
    return r.stdout

def flat_list(channel):
    out = run(["yt-dlp", "--flat-playlist", "-J", f"{channel.rstrip('/')}/videos"])
    d = json.loads(out)
    return [e["id"] for e in d.get("entries", []) if e.get("id")]

def video_meta(vid):
    out = run(["yt-dlp", "-J", "--skip-download", f"https://www.youtube.com/watch?v={vid}"])
    if not out.strip():
        return None
    d = json.loads(out)
    return dict(id=vid, title=d.get("title"), view_count=d.get("view_count"), like_count=d.get("like_count"),
                comment_count=d.get("comment_count"), duration=d.get("duration"), upload_date=d.get("upload_date"),
                chapters=[(c.get("start_time"), c.get("title")) for c in (d.get("chapters") or [])],
                description=(d.get("description") or "")[:1500])

def fetch_subs(vid):
    run(["yt-dlp", "--skip-download", "--write-auto-sub", "--write-sub", "--sub-lang", "ja",
         "--sub-format", "vtt", "-o", str(SUBS / "%(id)s"), f"https://www.youtube.com/watch?v={vid}"])

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", required=True)
    ap.add_argument("--subs-top", type=int, default=30)
    a = ap.parse_args()

    ids = flat_list(a.channel)
    print(f"{len(ids)} videos found")
    rows = []
    for i, vid in enumerate(ids, 1):
        m = video_meta(vid)
        if m:
            rows.append(m)
        print(f"[{i}/{len(ids)}] {vid} {m['title'][:40] if m else 'ERR'}")
    rows.sort(key=lambda r: r["view_count"] or 0, reverse=True)
    (DATA / "channel_videos.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(DATA / "channel_videos.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["id", "upload_date", "duration", "view_count", "like_count", "comment_count", "title"])
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in w.fieldnames})

    targets = [r["id"] for r in rows[: a.subs_top]] + [s for s in SAMPLES if s not in [r["id"] for r in rows[: a.subs_top]]]
    for vid in targets:
        fetch_subs(vid)
    print(f"subs saved: {len(list(SUBS.glob('*.vtt')))} files → {SUBS}")
