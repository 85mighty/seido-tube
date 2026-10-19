#!/usr/bin/env python3
"""queue.csv 의 다음 todo 1건 → Claude 로 대본 JSON 생성 → work/<slug>/script.json

usage: python3 scripts/04_script_gen.py [--minutes 10] [--row 0]
env:   ANTHROPIC_API_KEY (없으면 `claude -p` CLI 로 폴백)
"""
import argparse, csv, datetime as dt, json, os, re, subprocess, sys, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROMPT = (ROOT / "templates" / "script_prompt.md").read_text(encoding="utf-8")
CHARS_PER_MIN = int(os.getenv("CHARS_PER_MIN", "320"))   # 02_analyze_transcripts 결과로 교체

def source_text(url):
    if not url or url == "NEW":
        return "（参考記事なし。一般的な公的情報に基づき執筆。数字は目安と明記）"
    try:
        m = re.search(r"/([^/]+)/?$", url)
        api = url.split("/wp-content")[0].rstrip("/")
        api = re.sub(r"/[^/]+/?$", "", api) if not api.endswith(".com") else api
        with urllib.request.urlopen(f"{api}/wp-json/wp/v2/posts?slug={m[1]}&_fields=content", timeout=20) as r:
            html = json.load(r)[0]["content"]["rendered"]
        return re.sub(r"<[^>]+>", "", html)[:6000]
    except Exception as e:
        return f"（記事取得失敗: {e}）"

def ask_claude(prompt):
    key = os.getenv("ANTHROPIC_API_KEY")
    if key:
        import anthropic
        client = anthropic.Anthropic()
        msg = client.messages.create(model=os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5"), max_tokens=8000,
                                     messages=[{"role": "user", "content": prompt}])
        return msg.content[0].text
    return subprocess.run(["claude", "-p", prompt, "--output-format", "text"], capture_output=True, text=True).stdout

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--minutes", type=int, default=10); ap.add_argument("--row", type=int)
    a = ap.parse_args()
    q = ROOT / "data" / "queue.csv"
    rows = list(csv.DictReader(open(q, encoding="utf-8")))
    idx = a.row if a.row is not None else next(i for i, r in enumerate(rows) if r["status"] == "todo")
    r = rows[idx]
    prompt = (PROMPT.replace("{{topic}}", r["topic"]).replace("{{keyword}}", r["keyword"])
              .replace("{{source_text}}", source_text(r["source_url"])).replace("{{minutes}}", str(a.minutes))
              .replace("{{chars}}", str(a.minutes * CHARS_PER_MIN)).replace("{{today}}", dt.date.today().isoformat())
              .replace("{{related}}", r["source_url"] if r["source_url"] != "NEW" else "https://seido-note.com"))
    raw = ask_claude(prompt)
    js = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
    slug = f"{dt.date.today():%Y%m%d}_{r['topic_key']}_{idx}"
    wd = ROOT / "work" / slug; wd.mkdir(parents=True, exist_ok=True)
    (wd / "script.json").write_text(json.dumps(js, ensure_ascii=False, indent=1), encoding="utf-8")
    total = sum(len(s["narration"]) for s in js["sections"])
    rows[idx]["status"] = f"scripted:{slug}"
    with open(q, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
    print(f"{slug}\n{js['title']}\n{total}字 ≈ {total / CHARS_PER_MIN:.1f}분, {len(js['sections'])} sections")
