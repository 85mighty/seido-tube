#!/usr/bin/env python3
"""seido-tube 검수 패널 (VPS :8085)
   - 영상 재생 + 섹션/슬라이드별 시작~끝 초, 대본, 음성 한눈에
   - 슬라이드 내용 수정 → 미리보기(PNG 1장만 즉시 렌더), 추가(분할)/삭제/순서/비중(weight)
   - 섹션 대본 수정 → 음성 재생성, 전체 재렌더(백그라운드), 로그

run:  pip install fastapi uvicorn python-multipart
      pm2 start "python3 /root/seido-tube/panel/app.py" --name seido-panel && pm2 save
env:  PANEL_PORT(8085), PANEL_USER/PANEL_PASS(설정하면 Basic 인증)
"""
import base64, importlib.util, json, os, secrets, subprocess, sys, time
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
WORK, ASSETS = ROOT / "work", ROOT / "assets"
sys.path.insert(0, str(ROOT / "scripts"))
_spec = importlib.util.spec_from_file_location("render", ROOT / "scripts" / "06_render.py")
render = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(render)

app = FastAPI()
JOBS = {}   # slug -> Popen

@app.middleware("http")
async def auth(request: Request, call_next):
    u, p = os.getenv("PANEL_USER"), os.getenv("PANEL_PASS")
    if u and p:
        h = request.headers.get("authorization", "")
        ok = h.startswith("Basic ") and secrets.compare_digest(base64.b64decode(h[6:]).decode(), f"{u}:{p}")
        if not ok:
            return Response("auth", 401, headers={"WWW-Authenticate": "Basic"})
    return await call_next(request)

def wd(slug):
    d = WORK / slug
    if not d.is_dir() or "/" in slug:
        raise HTTPException(404)
    return d

def load(slug):
    d = wd(slug)
    js = json.loads((d / "script.json").read_text(encoding="utf-8"))
    timing = {t["id"]: t for t in json.loads((d / "timing.json").read_text())} if (d / "timing.json").exists() else {}
    man = {}
    mp = ASSETS / slug / "manifest.json"
    if mp.exists():
        for m in json.loads(mp.read_text(encoding="utf-8"))["images"]:
            man.setdefault(m["section"], []).append(m)
    return d, js, timing, man

# ---------- pages ----------
@app.get("/", response_class=HTMLResponse)
def index():
    rows = []
    for d in sorted(WORK.iterdir(), reverse=True) if WORK.exists() else []:
        if (d / "script.json").exists():
            js = json.loads((d / "script.json").read_text(encoding="utf-8"))
            st = "✅mp4" if (d / "final.mp4").exists() else ("🔊audio" if (d / "audio").exists() else "📝script")
            rows.append(f"<li><a href='/w/{d.name}'>{d.name}</a> {st} — {js.get('title','')}</li>")
    return f"<html><meta charset=utf-8><body style='font-family:sans-serif;max-width:900px;margin:40px auto'><h2>seido-tube 検収パネル</h2><ul>{''.join(rows) or '<li>work/ 비어있음</li>'}</ul></body></html>"

@app.get("/w/{slug}", response_class=HTMLResponse)
def page(slug):
    wd(slug)
    return (ROOT / "panel" / "index.html").read_text(encoding="utf-8").replace("{{SLUG}}", slug)

# ---------- data ----------
@app.get("/api/{slug}/state")
def state(slug):
    d, js, timing, man = load(slug)
    secs = []
    for s in js["sections"]:
        t = timing.get(s["id"], {}); slides = s.get("slides") or []
        ws = [float(sl.get("weight") or 1) for sl in slides]; cur = t.get("start", 0); out = []
        files = man.get(s["id"], [])
        for j, sl in enumerate(slides):
            per = t.get("dur", 0) * ws[j] / (sum(ws) or 1)
            out.append(dict(idx=j, spec=sl, start=round(cur, 1), end=round(cur + per, 1),
                            img=f"/assets/{slug}/{files[j]['file']}" if j < len(files) else None)); cur += per
        secs.append(dict(id=s["id"], narration=s["narration"], chars=len(s["narration"]), start=t.get("start"), dur=t.get("dur"),
                         audio=f"/files/{slug}/audio/{s['id']}.mp3" if (d / "audio" / f"{s['id']}.mp3").exists() else None, slides=out))
    job = JOBS.get(slug); running = job is not None and job.poll() is None
    return dict(slug=slug, title=js["title"], thumbnail=f"/files/{slug}/thumbnail.png" if (d / "thumbnail.png").exists() else None,
                video=f"/files/{slug}/final.mp4" if (d / "final.mp4").exists() else None,
                video_mtime=(d / "final.mp4").stat().st_mtime if (d / "final.mp4").exists() else 0,
                sections=secs, running=running, log=(d / "render.log").read_text(encoding="utf-8", errors="ignore")[-3000:] if (d / "render.log").exists() else "")

@app.get("/files/{slug}/{path:path}")
def files(slug, path):
    p = (wd(slug) / path).resolve()
    if not str(p).startswith(str(wd(slug).resolve())) or not p.exists():
        raise HTTPException(404)
    return FileResponse(p)

# ---------- edits ----------
@app.post("/api/{slug}/slide")
def save_slide(slug, body: dict):
    """body: {section, idx, spec} 저장 / {section, idx, op: 'add'|'del'|'up'|'down'}"""
    d, js, _, _ = load(slug)
    s = next(x for x in js["sections"] if x["id"] == body["section"]); sl = s.setdefault("slides", []); i = int(body.get("idx", 0))
    op = body.get("op")
    if op == "add":
        base = sl[i] if sl else {"kind": "bullets"}
        sl.insert(i + 1, {"kind": "bullets", "title": base.get("title", ""), "items": ["", ""], "alt": "", "weight": 1})
    elif op == "del" and len(sl) > 1:
        sl.pop(i)
    elif op == "up" and i > 0:
        sl[i - 1], sl[i] = sl[i], sl[i - 1]
    elif op == "down" and i < len(sl) - 1:
        sl[i + 1], sl[i] = sl[i], sl[i + 1]
    elif "spec" in body:
        sl[i] = body["spec"]
    (d / "script.json").write_text(json.dumps(js, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"ok": True}

@app.post("/api/{slug}/narration")
def save_narration(slug, body: dict):
    d, js, _, _ = load(slug)
    s = next(x for x in js["sections"] if x["id"] == body["section"]); s["narration"] = body["narration"]
    (d / "script.json").write_text(json.dumps(js, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"ok": True, "chars": len(s["narration"])}

@app.post("/api/{slug}/meta")
def save_meta(slug, body: dict):
    d, js, _, _ = load(slug)
    for k in ("title", "description", "thumbnail", "tags"):
        if k in body:
            js[k] = body[k]
    (d / "script.json").write_text(json.dumps(js, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"ok": True}

@app.post("/api/{slug}/preview")
def preview(slug, body: dict):
    """슬라이드 1장만 즉시 PNG 렌더 (저장하지 않음). body: {spec, section} / {thumbnail: {...}}"""
    d = wd(slug); out = d / "preview.png"
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        if "thumbnail" in body:
            pg = b.new_page(viewport={"width": 1280, "height": 720}); pg.set_content(render.thumb_html(body["thumbnail"]))
        else:
            pg = b.new_page(viewport={"width": 1920, "height": 1080}); pg.set_content(render.slide_html(body["spec"], body.get("section", "")))
        pg.screenshot(path=str(out)); b.close()
    return FileResponse(out, headers={"Cache-Control": "no-store"})

# ---------- jobs ----------
def start_job(slug, cmd):
    d = wd(slug)
    if slug in JOBS and JOBS[slug].poll() is None:
        raise HTTPException(409, "already running")
    env = dict(os.environ)
    for line in (ROOT / ".env").read_text().splitlines() if (ROOT / ".env").exists() else []:
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1); env.setdefault(k.strip(), v.split("#")[0].strip())
    JOBS[slug] = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=open(d / "render.log", "w"), stderr=subprocess.STDOUT)
    return {"ok": True}

@app.post("/api/{slug}/tts")
def tts(slug, body: dict):
    """섹션 음성 재생성: 해당 mp3 삭제 후 05 실행(기존 mp3 는 재사용되므로 그 섹션만 새로 만듦)"""
    d = wd(slug)
    for sid in body.get("sections", []):
        (d / "audio" / f"{sid}.mp3").unlink(missing_ok=True)
    return start_job(slug, ["python3", "scripts/05_tts.py", f"work/{slug}"])

@app.post("/api/{slug}/render")
def do_render(slug):
    return start_job(slug, ["bash", "-c", f"python3 scripts/05_tts.py work/{slug} && python3 scripts/06_render.py work/{slug}"])

@app.post("/api/{slug}/upload")
def do_upload(slug, body: dict):
    args = ["python3", "scripts/07_upload.py", f"work/{slug}"] + (["--publish"] if body.get("publish") else [])
    return start_job(slug, args)

@app.post("/api/{slug}/blog")
def do_blog(slug, body: dict):
    args = ["python3", "scripts/08_blog_post.py", f"work/{slug}"] + (["--wp"] if body.get("wp") else []) + (["--hatena"] if body.get("hatena") else []) + (["--draft"] if body.get("draft") else [])
    return start_job(slug, args)

app.mount("/assets", StaticFiles(directory=str(ASSETS)), name="assets") if ASSETS.exists() else None

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PANEL_PORT", "8085")))
