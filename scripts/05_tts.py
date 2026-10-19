#!/usr/bin/env python3
"""script.json → 섹션별 ElevenLabs 일본어 음성 → work/<slug>/audio/<section>.mp3 + timing.json

usage: python3 scripts/05_tts.py work/<slug>
env:   ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID, ELEVENLABS_MODEL(default eleven_multilingual_v2),
       ELEVENLABS_SPEED(default 0.9 — 실버층 대상이라 느리게. 1.05=약409字/分, 0.9=약350字/分)
"""
import json, os, subprocess, sys, urllib.request
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

if __name__ == "__main__":
    wd = Path(sys.argv[1]); js = json.loads((wd / "script.json").read_text(encoding="utf-8"))
    ad = wd / "audio"; ad.mkdir(exist_ok=True)
    timing, t = [], 0.0
    for s in js["sections"]:
        mp3 = ad / f"{s['id']}.mp3"
        if not mp3.exists():
            synth(s["narration"], mp3)
        d = duration(mp3)
        timing.append(dict(id=s["id"], start=round(t, 2), dur=round(d, 2), chars=len(s["narration"])))
        t += d
        print(f"{s['id']:<10} {d:6.1f}s  {len(s['narration'])}字")
    (wd / "timing.json").write_text(json.dumps(timing, ensure_ascii=False, indent=1), encoding="utf-8")
    chars = sum(x["chars"] for x in timing)
    print(f"total {t/60:.1f}분  (TTS 실측 {chars/(t/60):.0f}字/분 → .env CHARS_PER_MIN 권장값)")
