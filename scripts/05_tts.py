#!/usr/bin/env python3
"""script.json → ElevenLabs 일본어 음성 → work/<slug>/audio/*.mp3 + timing.json

슬라이드별 narration 이 있으면 **슬라이드 단위로** 녹음 (audio/<sec>_<idx>.mp3) → 각 화면 길이 = 실제 음성 길이 (싱크 정확)
섹션 재생용으로 <sec>.mp3 도 이어붙여 생성. 기존 mp3 는 재사용(텍스트가 바뀐 슬라이드만 다시 생성).

usage: python3 scripts/05_tts.py work/<slug>
env:   ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID, ELEVENLABS_MODEL(default eleven_multilingual_v2),
       ELEVENLABS_SPEED(default 0.9), SLIDE_GAP(슬라이드 사이 무음 초, default 0.25)
"""
import hashlib, json, os, subprocess, sys, urllib.request
from pathlib import Path

def synth(text, out):
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{os.environ['ELEVENLABS_VOICE_ID']}?output_format=mp3_44100_128",
        data=json.dumps({"text": text, "model_id": os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2"),
                         "voice_settings": {"stability": 0.6, "similarity_boost": 0.8, "speed": float(os.getenv("ELEVENLABS_SPEED", "0.9"))}}).encode(),
        headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"], "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        out.write_bytes(r.read())

def duration(p):
    return float(subprocess.check_output(["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)]))

def h(text):
    return hashlib.md5(text.encode()).hexdigest()[:8]

if __name__ == "__main__":
    wd = Path(sys.argv[1]); js = json.loads((wd / "script.json").read_text(encoding="utf-8"))
    ad = wd / "audio"; ad.mkdir(exist_ok=True); gap = float(os.getenv("SLIDE_GAP", "0.25"))
    timing, t = [], 0.0
    for s in js["sections"]:
        slides = s.get("slides") or []
        per_slide = bool(slides) and all(x.get("narration") for x in slides)
        if per_slide:
            parts, sec_start = [], t
            for j, sl in enumerate(slides):
                text = sl["narration"].strip()
                mp3 = ad / f"{s['id']}_{j}_{h(text)}.mp3"      # 텍스트 해시 → 바뀐 슬라이드만 재생성
                if not mp3.exists():
                    synth(text, mp3)
                d = duration(mp3) + gap
                parts.append(dict(idx=j, start=round(t, 2), dur=round(d, 2), chars=len(text), file=mp3.name)); t += d
            # 섹션 재생용 결합 (슬라이드 사이 gap 무음 포함)
            lst = ad / f"{s['id']}.list.txt"
            sil = ad / "_gap.mp3"
            if not sil.exists():
                subprocess.run(["ffmpeg", "-y", "-v", "quiet", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", str(gap), "-b:a", "128k", str(sil)], check=True)
            lst.write_text("".join(f"file '{(ad / p['file']).resolve()}'\nfile '{sil.resolve()}'\n" for p in parts))
            subprocess.run(["ffmpeg", "-y", "-v", "quiet", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(ad / f"{s['id']}.mp3")], check=True)
            dsec = t - sec_start
            timing.append(dict(id=s["id"], start=round(sec_start, 2), dur=round(dsec, 2), chars=len(s["narration"]), slides=parts))
            print(f"{s['id']:<10} {dsec:6.1f}s  {len(slides)} slides")
        else:
            mp3 = ad / f"{s['id']}.mp3"
            if not mp3.exists():
                synth(s["narration"], mp3)
            d = duration(mp3)
            timing.append(dict(id=s["id"], start=round(t, 2), dur=round(d, 2), chars=len(s["narration"]))); t += d
            print(f"{s['id']:<10} {d:6.1f}s  {len(s['narration'])}字 (섹션 단위)")
    (wd / "timing.json").write_text(json.dumps(timing, ensure_ascii=False, indent=1), encoding="utf-8")
    chars = sum(x["chars"] for x in timing)
    print(f"total {t/60:.1f}분  (TTS 실측 {chars/(t/60):.0f}字/분)")
