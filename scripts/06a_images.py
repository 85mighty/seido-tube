#!/usr/bin/env python3
"""캐릭터/일러스트 생성 + 라이브러리 캐시.  script.json 의 slides[].character 를 보고
   assets/library/characters/<id>_<mood>.png 가 없으면 이미지 API로 생성해 저장.
   (한 번 만든 캐릭터는 영원히 재사용 → 채널 전체 비주얼 통일 + 비용 절감)

usage: python3 scripts/06a_images.py work/<slug>
env:   IMAGE_PROVIDER = openai | fal | none   (none 이면 플레이스홀더 PNG 생성)
       OPENAI_API_KEY  (openai: gpt-image-1)   /  FAL_KEY (fal: flux)
"""
import base64, json, os, sys, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "assets" / "library" / "characters"; LIB.mkdir(parents=True, exist_ok=True)
STYLE = ("flat vector illustration in the style of Japanese free clip-art (irasutoya), simple rounded shapes, soft pastel colors, "
         "thick clean outlines, white background, no text, centered, full upper body, friendly")
BASE = {
    "man60":     "a Japanese man in his 60s with gray hair and glasses, wearing a brown jacket",
    "woman60":   "a Japanese woman in her 60s with short gray hair, wearing a pink cardigan",
    "couple":    "an elderly Japanese couple standing together, both holding a green bank passbook",
    "nurse_host":"a young Japanese woman nurse presenter with a hair bun and black glasses, white uniform, giving an OK sign",
}
MOOD = {"sad": "worried, sweating, blue gloomy aura", "happy": "smiling brightly, sparkles", "neutral": "calm smile", "surprised": "shocked, mouth open"}

def gen_openai(prompt, out):
    req = urllib.request.Request("https://api.openai.com/v1/images/generations",
        data=json.dumps({"model": "gpt-image-1", "prompt": prompt, "size": "1024x1024", "background": "transparent", "n": 1}).encode(),
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        out.write_bytes(base64.b64decode(json.load(r)["data"][0]["b64_json"]))

def gen_fal(prompt, out):
    req = urllib.request.Request("https://fal.run/fal-ai/flux/schnell",
        data=json.dumps({"prompt": prompt, "image_size": "square", "num_images": 1}).encode(),
        headers={"Authorization": f"Key {os.environ['FAL_KEY']}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        url = json.load(r)["images"][0]["url"]
    out.write_bytes(urllib.request.urlopen(url, timeout=120).read())

def gen_placeholder(prompt, out):
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.ellipse((212, 100, 812, 700), fill=(255, 224, 189)); d.rectangle((312, 700, 712, 1000), fill=(120, 150, 220))
    im.save(out)

GEN = {"openai": gen_openai, "fal": gen_fal, "none": gen_placeholder}

def ensure(cid, mood, custom=None):
    out = LIB / f"{cid}_{mood}.png"
    if out.exists():
        return out
    prompt = f"{custom or BASE.get(cid, cid)}, {MOOD.get(mood, mood)}, {STYLE}"
    GEN[os.getenv("IMAGE_PROVIDER", "none")](prompt, out)
    (LIB / f"{cid}_{mood}.txt").write_text(prompt, encoding="utf-8")
    print("generated", out.name); return out

if __name__ == "__main__":
    wd = Path(sys.argv[1]); js = json.loads((wd / "script.json").read_text(encoding="utf-8"))
    need = set()
    for s in js["sections"]:
        for sl in s.get("slides", []):
            c = sl.get("character")
            if c:
                need.add((c["id"], c.get("mood", "neutral"), sl.get("character_prompt")))
            if sl.get("kind") == "compare":
                need.add(("couple", sl["left"].get("mood", "sad"), None)); need.add(("couple", sl["right"].get("mood", "happy"), None))
            if sl.get("kind") == "timeline":
                for r in sl.get("rows", []):
                    need.add((r.get("character", "man60"), r.get("mood", "neutral"), None))
    th = js.get("thumbnail", {})
    if th:
        need.add(("couple", "sad", None)); need.add(("couple", "happy", None))
    for cid, mood, custom in need:
        ensure(cid, mood, custom)
    print(f"library ready: {len(list(LIB.glob('*.png')))} characters")
