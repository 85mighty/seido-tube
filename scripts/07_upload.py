#!/usr/bin/env python3
"""final.mp4 → YouTube 업로드(unlisted, 예약공개 금요 19:00 JST) → Telegram 으로 미리보기 링크 + 승인 요청
     --publish : 승인 후 public 전환(예약 시각 유지)

setup (VPS 1회):
  pip install google-api-python-client google-auth-oauthlib
  Google Cloud Console → YouTube Data API v3 활성화 → OAuth 클라이언트(데스크톱) → config/client_secret.json
  최초 1회 `python3 scripts/07_upload.py --auth` 로 브라우저 인증 → config/yt_token.json 저장
env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""
import argparse, datetime as dt, json, os, sys, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CFG = ROOT / "config"; SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube", "https://www.googleapis.com/auth/youtube.force-ssl"]

def creds():
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    tok = CFG / "yt_token.json"
    if tok.exists():
        return Credentials.from_authorized_user_file(str(tok), SCOPES)
    c = InstalledAppFlow.from_client_secrets_file(str(CFG / "client_secret.json"), SCOPES).run_console()
    tok.write_text(c.to_json()); return c

def next_friday_19jst():
    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=9)))
    d = now + dt.timedelta(days=(4 - now.weekday()) % 7 or 7)
    return d.replace(hour=19, minute=0, second=0, microsecond=0).astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")

def telegram(text):
    if not os.getenv("TELEGRAM_BOT_TOKEN"):
        print("[telegram skipped]", text); return
    urllib.request.urlopen(f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage?" +
                           urllib.parse.urlencode({"chat_id": os.environ["TELEGRAM_CHAT_ID"], "text": text}))

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("workdir", nargs="?"); ap.add_argument("--auth", action="store_true")
    ap.add_argument("--publish", action="store_true"); a = ap.parse_args()
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    yt = build("youtube", "v3", credentials=creds())
    if a.auth:
        print("auth ok"); sys.exit()
    wd = Path(a.workdir); js = json.loads((wd / "script.json").read_text(encoding="utf-8")); meta = wd / "youtube.json"
    if a.publish:
        vid = json.loads(meta.read_text())["id"]
        yt.videos().update(part="status", body={"id": vid, "status": {"privacyStatus": "private", "publishAt": next_friday_19jst(), "selfDeclaredMadeForKids": False}}).execute()
        telegram(f"✅ 公開予約: https://youtu.be/{vid} ({next_friday_19jst()})"); sys.exit()
    body = {"snippet": {"title": js["title"][:100], "description": js["description"], "tags": js.get("tags", [])[:30],
                        "categoryId": "27", "defaultLanguage": "ja", "defaultAudioLanguage": "ja"},
            "status": {"privacyStatus": "unlisted", "selfDeclaredMadeForKids": False}}
    r = yt.videos().insert(part="snippet,status", body=body,
                           media_body=MediaFileUpload(str(wd / "final.mp4"), chunksize=8 * 1024 * 1024, resumable=True)).execute()
    vid = r["id"]
    if (wd / "thumbnail.png").exists():
        yt.thumbnails().set(videoId=vid, media_body=str(wd / "thumbnail.png")).execute()
    if (wd / "subs.srt").exists():   # CC 트랙 (시청자가 자막 버튼으로 켜고 끔)
        try:
            yt.captions().insert(part="snippet", body={"snippet": {"videoId": vid, "language": "ja", "name": "日本語", "isDraft": False}},
                                 media_body=MediaFileUpload(str(wd / "subs.srt"), mimetype="application/octet-stream")).execute()
        except Exception as e:
            print("caption upload skipped:", e)
    meta.write_text(json.dumps({"id": vid, "uploaded": dt.datetime.now().isoformat()}))
    telegram(f"🎬 확인 요청\n{js['title']}\nhttps://youtu.be/{vid}\n\n승인: python3 scripts/07_upload.py {wd} --publish")
    print("unlisted:", f"https://youtu.be/{vid}")
