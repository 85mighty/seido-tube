#!/usr/bin/env python3
"""토픽 큐 생성: 벤치마크 랭킹 × 시즌 캘린더 × seido-note 기존 글 매칭 → data/queue.csv

- analysis/topic_ranking.csv (02까지의 분석)과 config/topics.yaml 을 합쳐 이번 달 우선순위 산출
- seido-note WP REST API (SEIDO_WP_URL) 에서 글 목록을 받아 seed_keywords 와 매칭 → 대본 소스 글 URL 연결
- 매칭 안 되면 source=NEW (seido-note 에도 글이 없는 주제 → 영상 먼저 만들고 글은 후속 자동생성)

usage: python3 scripts/03_topic_queue.py --month 11 --n 8
"""
import argparse, csv, datetime as dt, json, os, re, urllib.request
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT / "config" / "topics.yaml").read_text(encoding="utf-8"))

def wp_posts(base):
    posts, page = [], 1
    while base:
        url = f"{base.rstrip('/')}/wp-json/wp/v2/posts?per_page=100&page={page}&_fields=id,link,title,categories,excerpt"
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                batch = json.load(r)
        except Exception as e:
            print("WP fetch stop:", e); break
        if not batch:
            break
        posts += batch; page += 1
    return posts

def match(post, keywords):
    text = re.sub(r"<[^>]+>", "", post["title"]["rendered"] + post.get("excerpt", {}).get("rendered", ""))
    return sum(1 for kw in keywords for tok in kw.split() if tok in text)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", type=int, default=dt.date.today().month)
    ap.add_argument("--n", type=int, default=8)
    a = ap.parse_args()

    posts = wp_posts(os.getenv("SEIDO_WP_URL", "https://seido-note.com"))
    boost = set(CFG.get("calendar", {}).get(a.month, []))
    rows = []
    for t in CFG["topics"]:
        w = t["ranking_weight"] * (1.5 if t["key"] in boost else 1.0)
        best = max(posts, key=lambda p: match(p, t["seed_keywords"]), default=None)
        score = match(best, t["seed_keywords"]) if best else 0
        for kw in t["seed_keywords"]:
            rows.append(dict(priority=round(w, 1), topic_key=t["key"], topic=t["name"], keyword=kw,
                             seasonal="Y" if t["key"] in boost else "",
                             source_url=best["link"] if best and score else "NEW",
                             seido_category=t["seido_note_category"], status="todo"))
    rows.sort(key=lambda r: (-r["priority"], r["topic_key"]))
    out = ROOT / "data" / "queue.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0].keys())); wr.writeheader(); wr.writerows(rows[: a.n * 3])
    print(f"queue → {out}\n")
    for r in rows[: a.n]:
        print(f"{r['priority']:>4} {r['seasonal']:1} {r['topic']:<22} {r['keyword']:<28} {r['source_url']}")
