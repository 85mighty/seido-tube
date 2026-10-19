#!/usr/bin/env python3
"""영상 1편 → 블로그 글 자동 생성 → seido-note.com(WordPress) + seido-note.hatenablog.com(Hatena) 동시 포스팅
   이미지는 assets/<slug>/ 의 슬라이드 PNG 를 그대로 사용 (WP 미디어에 업로드 → 그 URL 을 Hatena 에도 임베드)

usage: python3 scripts/08_blog_post.py work/<slug> [--wp] [--hatena] [--draft]
env:
  SEIDO_WP_URL, SEIDO_WP_USER, SEIDO_WP_APP_PASS   (WP → 사용자 → 애플리케이션 비밀번호)
  HATENA_ID, HATENA_BLOG(=seido-note.hatenablog.com), HATENA_API_KEY (はてな → 設定 → 詳細設定 → AtomPub API キー)
  ANTHROPIC_API_KEY (없으면 claude -p 폴백)
"""
import argparse, base64, datetime as dt, json, mimetypes, os, re, subprocess, sys, urllib.request, html
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ARTICLE_PROMPT = """以下のYouTube台本と画像リストから、検索流入向けのブログ記事(HTML)を書いてください。
- 対象読者: 50〜60代。見出しはh2/h3、1段落3文以内、表は<table>で再構成（画像の表に頼らず本文にも数字を書く）
- 画像は <!--IMG:ファイル名--> という目印を本文の適切な位置に入れる（最大6枚、表・比較・タイムラインを優先）
- 冒頭に導入(lead)、末尾に「よくある質問」(faq)と、動画への誘導 <!--YOUTUBE--> を入れる
- 制度の数字が不確実なら「目安」と書き、出典の省庁名を本文に。台本の文章をそのまま貼らず、記事として書き直す
- 出力はJSONのみ: {"title":"...","excerpt":"120字","html":"...","tags":["..",".."]}

台本: {{script}}
画像: {{images}}
"""

def ask_claude(prompt):
    if os.getenv("ANTHROPIC_API_KEY"):
        import anthropic
        m = anthropic.Anthropic().messages.create(model=os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5"), max_tokens=8000,
                                                  messages=[{"role": "user", "content": prompt}])
        return m.content[0].text
    return subprocess.run(["claude", "-p", prompt, "--output-format", "text"], capture_output=True, text=True).stdout

# ---------- WordPress ----------
def wp_req(path, data=None, headers=None, method=None):
    auth = base64.b64encode(f"{os.environ['SEIDO_WP_USER']}:{os.environ['SEIDO_WP_APP_PASS']}".encode()).decode()
    h = {"Authorization": f"Basic {auth}"}; h.update(headers or {})
    req = urllib.request.Request(f"{os.environ['SEIDO_WP_URL'].rstrip('/')}/wp-json/wp/v2/{path}", data=data, headers=h, method=method)
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)

def wp_upload(p, alt):
    r = wp_req("media", data=p.read_bytes(), headers={"Content-Type": mimetypes.guess_type(p.name)[0] or "image/png",
                                                     "Content-Disposition": f'attachment; filename="{p.name}"'})
    wp_req(f"media/{r['id']}", data=json.dumps({"alt_text": alt}).encode(), headers={"Content-Type": "application/json"})
    return r["id"], r["source_url"]

def wp_post(title, content, excerpt, tags, thumb_id, draft):
    body = {"title": title, "content": content, "excerpt": excerpt, "status": "draft" if draft else "publish", "featured_media": thumb_id}
    return wp_req("posts", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})["link"]

# ---------- Hatena (AtomPub) ----------
def hatena_post(title, content, tags, draft):
    cats = "".join(f'<category term="{html.escape(t)}" />' for t in tags[:5])
    entry = f"""<?xml version="1.0" encoding="utf-8"?>
<entry xmlns="http://www.w3.org/2005/Atom" xmlns:app="http://www.w3.org/2007/app">
  <title>{html.escape(title)}</title><author><name>{os.environ['HATENA_ID']}</name></author>
  <content type="text/html">{html.escape(content)}</content>{cats}
  <app:control><app:draft>{'yes' if draft else 'no'}</app:draft></app:control></entry>"""
    auth = base64.b64encode(f"{os.environ['HATENA_ID']}:{os.environ['HATENA_API_KEY']}".encode()).decode()
    req = urllib.request.Request(f"https://blog.hatena.ne.jp/{os.environ['HATENA_ID']}/{os.environ['HATENA_BLOG']}/atom/entry",
                                 data=entry.encode("utf-8"), headers={"Authorization": f"Basic {auth}", "Content-Type": "application/xml"}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        xml = r.read().decode()
    m = re.search(r'<link rel="alternate" type="text/html" href="([^"]+)"', xml)
    return m[1] if m else "(posted)"

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("workdir"); ap.add_argument("--wp", action="store_true")
    ap.add_argument("--hatena", action="store_true"); ap.add_argument("--draft", action="store_true"); a = ap.parse_args()
    wd = Path(a.workdir); slug = wd.name; assets = ROOT / "assets" / slug
    js = json.loads((wd / "script.json").read_text(encoding="utf-8"))
    man = json.loads((assets / "manifest.json").read_text(encoding="utf-8"))
    yt = json.loads((wd / "youtube.json").read_text()).get("id") if (wd / "youtube.json").exists() else None
    imgs = [dict(file=m["file"], kind=m["kind"], alt=m["alt"], title=m["title"]) for m in man["images"] if m["kind"] in ("table", "compare", "timeline", "bar", "number", "title")]
    prompt = ARTICLE_PROMPT.replace("{{script}}", json.dumps({k: js[k] for k in ("title", "blog", "notes", "sections")}, ensure_ascii=False)[:30000]) \
                           .replace("{{images}}", json.dumps(imgs, ensure_ascii=False))
    raw = ask_claude(prompt); art = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
    (wd / "article.json").write_text(json.dumps(art, ensure_ascii=False, indent=1), encoding="utf-8")

    # 이미지 업로드 (WP 미디어) → URL 치환
    url_of, thumb_id = {}, 0
    if a.wp or a.hatena:
        thumb_id, turl = wp_upload(assets / "thumbnail.png", js["title"]); url_of["thumbnail.png"] = turl
        for m in man["images"]:
            if f"<!--IMG:{m['file']}-->" in art["html"]:
                _, url_of[m["file"]] = wp_upload(assets / m["file"], m["alt"])
    content = art["html"]
    for f, u in url_of.items():
        alt = next((m["alt"] for m in man["images"] if m["file"] == f), "")
        content = content.replace(f"<!--IMG:{f}-->", f'<figure><img src="{u}" alt="{html.escape(alt)}" loading="lazy"><figcaption>{html.escape(alt)}</figcaption></figure>')
    content = re.sub(r"<!--IMG:[^>]+-->", "", content)
    embed = (f'<div style="position:relative;padding-top:56.25%"><iframe src="https://www.youtube.com/embed/{yt}" style="position:absolute;inset:0;width:100%;height:100%" allowfullscreen></iframe></div>'
             if yt else "")
    content = content.replace("<!--YOUTUBE-->", embed)
    out = {}
    if a.wp:
        out["wp"] = wp_post(art["title"], content, art.get("excerpt", ""), art.get("tags", []), thumb_id, a.draft)
    if a.hatena:
        out["hatena"] = hatena_post(art["title"], content, art.get("tags", []), a.draft)
    (wd / "blog.json").write_text(json.dumps(out, ensure_ascii=False, indent=1)); print(json.dumps(out, ensure_ascii=False, indent=1) or art["title"])
