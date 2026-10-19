#!/usr/bin/env python3
"""script.json + audio + 캐릭터 라이브러리 → 슬라이드 PNG(Playwright) → ffmpeg 합성
   → work/<slug>/final.mp4, thumbnail.png, subs.srt
   → assets/<slug>/{NNN_section_kind.png, thumbnail.png, manifest.json}   ← 블로그 재사용용 영구 보관

usage: pip install playwright && playwright install chromium   (VPS 1회)
       python3 scripts/06_render.py work/<slug>
"""
import html, json, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TPL = (ROOT / "templates" / "slide.html").read_text(encoding="utf-8")
LIB = ROOT / "assets" / "library" / "characters"
CHANNEL = "制度ノート"

def esc(s): return html.escape("" if s is None else str(s))
def chara(cid, mood):
    p = LIB / f"{cid}_{mood}.png"
    return f"<img src='file://{p.resolve()}'>" if p.exists() else ""

def svg_timeline(sl):
    periods, rows, vals = sl.get("periods", []), sl.get("rows", []), sl.get("values", [])
    W, H, L = 1300, 820, 60; cw = (W - L) / max(1, len(periods)); rh = (H - 120) / max(1, len(rows))
    out = [f"<svg viewBox='0 0 {W} {H}' xmlns='http://www.w3.org/2000/svg'>"]
    for i, p in enumerate(periods):
        x = L + i * cw
        out.append(f"<line x1='{x}' y1='20' x2='{x}' y2='{H-90}' stroke='#333' stroke-width='4' stroke-dasharray='14,10'/>")
        out.append(f"<text x='{x+cw/2}' y='{H-30}' font-size='40' font-weight='700' text-anchor='middle'>{esc(p)}</text>")
    out.append(f"<line x1='{L}' y1='{H-90}' x2='{W-10}' y2='{H-90}' stroke='#d32f2f' stroke-width='6' marker-end='url(#a)'/>")
    out.append("<defs><marker id='a' markerWidth='10' markerHeight='10' refX='5' refY='5' orient='auto'><path d='M0,0 L10,5 L0,10 z' fill='#333'/></marker></defs>")
    for r, row in enumerate(vals):
        y = 40 + r * rh
        for c, v in enumerate(row):
            if v in (None, ""):
                continue
            x = L + c * cw; col = "#2b5fd9" if c == 0 else "#f06b8a"
            out.append(f"<rect x='{x+6}' y='{y}' width='{cw-12}' height='{rh*0.6}' fill='{col}' rx='4'/>")
            out.append(f"<text x='{x+cw/2}' y='{y+rh*0.3+16}' font-size='48' font-weight='900' fill='#fff' text-anchor='middle'>{esc(v)}</text>")
    out.append("</svg>"); return "".join(out)

def svg_bar(sl):
    labels, vals, hl = sl.get("labels", []), [float(v) for v in sl.get("values", [])], sl.get("highlight")
    W, H, n = 1500, 760, max(1, len(vals)); mx = max(vals) or 1; bw = W / n * 0.6
    out = [f"<svg viewBox='0 0 {W} {H}' xmlns='http://www.w3.org/2000/svg'>"]
    for i, (lab, v) in enumerate(zip(labels, vals)):
        x = W / n * i + (W / n - bw) / 2; h = (H - 160) * v / mx; y = H - 100 - h
        col = "#d32f2f" if i == hl else "#2b5fd9"
        out.append(f"<rect x='{x}' y='{y}' width='{bw}' height='{h}' fill='{col}' rx='10'/>")
        out.append(f"<text x='{x+bw/2}' y='{y-16}' font-size='46' font-weight='900' text-anchor='middle' fill='{col}'>{esc(v)}{esc(sl.get('unit',''))}</text>")
        out.append(f"<text x='{x+bw/2}' y='{H-40}' font-size='40' font-weight='700' text-anchor='middle'>{esc(lab)}</text>")
    out.append("</svg>"); return "".join(out)

def slide_html(sl, section):
    k = sl.get("kind", "bullets"); hdr = f"<div class='hdr'>{esc(sl.get('title'))}</div>" if sl.get("title") else ""
    if k in ("title", "number"):
        body = f"<div class='big'>{esc(sl.get('big'))}</div><div class='sub'>{esc(sl.get('sub'))}</div>"
    elif k == "table":
        import re
        header, rows = sl.get("header", []), sl.get("rows", []); hl = sl.get("highlight") or [-1, -1]
        ncols = max([len(header)] + [len(x) for x in rows] or [1])
        maxcell = max([len(str(v)) for x in rows + [header] for v in x] or [1])
        has_co = bool(sl.get("callout"))
        # 행 수·열 수·셀 최대 글자수·콜아웃 유무로 표 폰트 단계 결정 (화면 밖으로 안 나가게)
        load = len(rows) + (1 if has_co else 0) + (ncols - 3) * 0.5 + max(0, maxcell - 8) * 0.4
        cls = "" if load <= 4 else "md" if load <= 5.5 else "sm" if load <= 7 else "xs"
        th = "".join(f"<th>{esc(h)}</th>" for h in header)
        tr = "".join("<tr>" + "".join(f"<td class='{'hl' if [r, c] == list(hl) else ''}'>{esc(v)}</td>" for c, v in enumerate(row)) + "</tr>"
                     for r, row in enumerate(rows))
        body = f"{hdr}<table class='{cls}'><tr>{th}</tr>{tr}</table>"
        if has_co:
            raw = sl["callout"]; n = len(re.sub(r"<br>|\s", "", raw))
            ccls = "" if n <= 20 else "md" if n <= 30 else "sm"
            co = esc(raw).replace("&lt;br&gt;", "<br>"); co = re.sub(r"([\d,.]+万?[\d,]*円|[\d,]+歳|[\d,]+％)", r"<b>\1</b>", co)
            body += f"<div class='callout {ccls}'>{co}</div>"
    elif k == "compare":
        l, r = sl.get("left", {}), sl.get("right", {})
        body = (f"{hdr}<div class='compare'><div class='l'><div class='note'>{esc(l.get('note'))}</div><div class='lab'>{esc(l.get('label'))}</div><div class='ver'>{esc(l.get('verdict'))}</div></div>"
                f"<div class='r'><div class='note'>{esc(r.get('note'))}</div><div class='lab'>{esc(r.get('label'))}</div><div class='ver'>{esc(r.get('verdict'))}</div></div></div>")
    elif k == "timeline":
        chars = "".join(f"<div>{chara(r.get('character','man60'), r.get('mood','neutral'))}<span>{esc(r.get('label'))}</span></div>" for r in sl.get("rows", []))
        body = f"{hdr}<div class='timeline'><div class='chars'>{chars}</div>{svg_timeline(sl)}</div>"
    elif k == "bar":
        body = f"{hdr}{svg_bar(sl)}"
    else:
        body = f"{hdr}<ul>" + "".join(f"<li>{esc(i)}</li>" for i in sl.get("items", [])) + "</ul>"
    c = sl.get("character")
    if c and k not in ("compare", "timeline"):
        body += chara(c["id"], c.get("mood", "neutral")).replace("<img", "<img class='character'")
    return TPL.replace("{{BODY}}", body).replace("{{CHANNEL}}", "").replace("{{SECTION}}", "")

THUMB_TPL = (ROOT / "templates" / "thumb.html").read_text(encoding="utf-8")
def thumb_html(th):
    l, r = th.get("left", {}), th.get("right", {})
    def ver(v):   # verdict 5文字超は自動縮小
        v = str(v or ""); return f"<span style='font-size:{96 if len(v) <= 4 else 76 if len(v) <= 6 else 60}px'>{esc(v)}</span>"
    def lab(v):
        v = str(v or ""); return f"<span style='font-size:{70 if len(v) <= 5 else 56 if len(v) <= 7 else 46}px'>{esc(v)}</span>"
    t = str(th.get("title") or ""); tsize = 82 if len(t) <= 7 else 66 if len(t) <= 9 else 54
    return (THUMB_TPL.replace("{{RIBBON}}", esc(th.get("ribbon", "知らなきゃ損！"))).replace("{{TITLE}}", f"<span style='font-size:{tsize}px'>{esc(t)}</span>")
            .replace("{{LNOTE}}", esc(l.get("note", ""))).replace("{{LLAB}}", lab(l.get("label"))).replace("{{LVER}}", ver(l.get("verdict")))
            .replace("{{RNOTE}}", esc(r.get("note", ""))).replace("{{RLAB}}", lab(r.get("label"))).replace("{{RVER}}", ver(r.get("verdict"))))

def srt_time(t):
    h, r = divmod(t, 3600); m, s = divmod(r, 60)
    return f"{int(h):02}:{int(m):02}:{int(s):02},{int((s % 1) * 1000):03}"

if __name__ == "__main__":
    wd = Path(sys.argv[1]); slug = wd.name
    js = json.loads((wd / "script.json").read_text(encoding="utf-8"))
    timing = {t["id"]: t for t in json.loads((wd / "timing.json").read_text(encoding="utf-8"))}
    from playwright.sync_api import sync_playwright
    frames = wd / "frames"; frames.mkdir(exist_ok=True)
    assets = ROOT / "assets" / slug; assets.mkdir(parents=True, exist_ok=True)
    concat, srt, manifest, n, cue = [], [], [], 0, 1
    with sync_playwright() as p:
        b = p.chromium.launch(); page = b.new_page(viewport={"width": 1920, "height": 1080})
        for s in js["sections"]:
            t = timing[s["id"]]; slides = s.get("slides") or [{"kind": "bullets", "title": s["id"], "items": []}]
            # 슬라이드별 weight(기본 1)에 비례해 섹션 음성 길이를 배분
            ws = [float(sl.get("weight") or 1) for sl in slides]; cur = t["start"]
            for j, sl in enumerate(slides):
                per = t["dur"] * ws[j] / sum(ws)
                page.set_content(slide_html(sl, s["id"])); png = frames / f"{n:03}.png"; page.screenshot(path=str(png))
                name = f"{n:03}_{s['id']}_{sl.get('kind','bullets')}.png"; shutil.copy(png, assets / name)
                manifest.append(dict(file=name, section=s["id"], kind=sl.get("kind"), title=sl.get("title") or sl.get("big"),
                                     alt=sl.get("alt", ""), start=round(cur, 1), end=round(cur + per, 1), spec=sl))
                concat += [f"file '{png.resolve()}'", f"duration {per:.3f}"]; n += 1; cur += per
            sents = [x for x in s["narration"].replace("。", "。\n").split("\n") if x.strip()]; st = t["start"]
            for x in sents:
                d = t["dur"] * len(x) / max(1, t["chars"])
                srt += [str(cue), f"{srt_time(st)} --> {srt_time(st + d)}", x.strip(), ""]; st += d; cue += 1
        concat.append(f"file '{(frames / f'{n-1:03}.png').resolve()}'")
        page.set_viewport_size({"width": 1280, "height": 720})
        page.set_content(thumb_html(js.get("thumbnail", {}))); page.screenshot(path=str(wd / "thumbnail.png")); b.close()
    shutil.copy(wd / "thumbnail.png", assets / "thumbnail.png")
    (assets / "manifest.json").write_text(json.dumps(dict(slug=slug, title=js["title"], blog=js.get("blog", {}), notes=js.get("notes", {}),
                                                            images=manifest), ensure_ascii=False, indent=1), encoding="utf-8")
    (wd / "concat.txt").write_text("\n".join(concat), encoding="utf-8"); (wd / "subs.srt").write_text("\n".join(srt), encoding="utf-8")
    audio = wd / "audio" / "all.mp3"
    (wd / "audio" / "list.txt").write_text("\n".join(f"file '{(wd/'audio'/(s['id']+'.mp3')).resolve()}'" for s in js["sections"]))
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(wd / "audio" / "list.txt"), "-c", "copy", str(audio)], check=True)
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(wd / "concat.txt"), "-i", str(audio),
                    "-vf", f"subtitles={wd/'subs.srt'}:force_style='FontName=Noto Sans CJK JP,FontSize=22,Outline=2,MarginV=40',format=yuv420p,fps=30",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", "-shortest", str(wd / "final.mp4")], check=True)
    print("→", wd / "final.mp4", "|", assets, f"({len(manifest)} images)")
