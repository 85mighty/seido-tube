#!/usr/bin/env python3
"""기존 script.json 의 슬라이드를 AI로 더 잘게 다시 구성 (대본 글자는 그대로 → 음성 재사용, TTS 비용 0)

usage: python3 scripts/09_reslice.py work/<slug> [--section hook] [--sec 18]
  --sec : 1슬라이드 목표 초수 (기본 18 → 약 100字). 작을수록 더 잘게
out  : script.json 갱신 (이전 버전은 script.before_reslice.json 으로 백업)
"""
import argparse, datetime as dt, json, os, re, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CPM = int(os.getenv("CHARS_PER_MIN", "350"))

PROMPT = """あなたは日本の年金・給付金解説動画のスライド設計者です。以下の「セクションのナレーション」を、より細かいスライドに分け直してください。

# 絶対条件
- ナレーションの文章は1文字も変えない。各スライドの "narration" は元の文章を先頭から順に切り分けたもので、全部つなぐと元の文章と完全に一致すること（文の途中では切らず、「。」「！」「？」の後で切る）
- 1スライド = 約{chars}字（±40%）。いま読まれている数字・制度名・結論が必ず画面に出ていること。話題が変わったら必ず新しいスライド
- 視聴者は50〜60代。文字は大きく、1画面の情報は少なく。「〇選」は使わない
- 既存スライドの表・数字は正しいので再利用してよい（必要なら行を減らして分割）

# 画面の種類 (kind)
"title":{{"big":"年6万5千円","sub":"申請しないと0円"}} / "number": 同形式 / "bullets":{{"title":"..","items":["..",".."]}}(3項目まで)
"table":{{"title":"..","header":[..],"rows":[[..]..],"highlight":[row,col]|null,"callout":"25文字以内"|null}}(4行×4列以内、1セル8文字以内)
"compare":{{"title":"..","left":{{"note":"..","label":"..","verdict":".."}},"right":{{...}}}}
各スライドに "alt"（ブログ用の1文説明）

# 入力
セクションID: {sid}
ナレーション（変更禁止）:
{narration}

既存スライド（参考）:
{slides}

# 出力（JSONのみ）
{{"slides":[{{"kind":"...","narration":"元の文章の一部","alt":"...", ...}}, ...]}}
"""

def ask_claude(prompt):
    if os.getenv("ANTHROPIC_API_KEY"):
        import anthropic
        m = anthropic.Anthropic().messages.create(model=os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5"), max_tokens=8000,
                                                  messages=[{"role": "user", "content": prompt}])
        return m.content[0].text
    return subprocess.run(["claude", "-p", prompt, "--output-format", "text"], capture_output=True, text=True).stdout

NORM = lambda s: re.sub(r"\s+", "", s)

def realign(original, chunks):
    """모델이 돌려준 조각들이 원문과 정확히 안 맞을 때: 조각 길이 비율로 원문을 문장 경계에서 다시 자름"""
    sents = [x for x in re.split(r"(?<=[。！？!?])", original) if x.strip()]
    tot = sum(len(c) for c in chunks) or 1
    targets = [len(original) * len(c) / tot for c in chunks]
    out, i, acc = [""] * len(chunks), 0, 0
    for s in sents:
        if i < len(chunks) - 1 and acc + len(s) / 2 > sum(targets[: i + 1]):
            i += 1
        out[i] += s; acc += len(s)
    return out

def reslice_section(sec, sec_target):
    chars = int(sec_target / 60 * CPM)
    prompt = PROMPT.format(chars=chars, sid=sec["id"], narration=sec["narration"],
                           slides=json.dumps([{k: v for k, v in s.items() if k not in ("narration", "overlays", "_orig", "weight")} for s in sec.get("slides", [])], ensure_ascii=False))
    raw = ask_claude(prompt)
    js = json.loads(raw[raw.find("{"): raw.rfind("}") + 1]); new = [s for s in js["slides"] if s.get("narration")]
    if not new:
        return None, "no slides"
    chunks = [s["narration"] for s in new]
    note = "exact"
    if NORM("".join(chunks)) != NORM(sec["narration"]):
        chunks = realign(sec["narration"], chunks); note = "realigned"
        if NORM("".join(chunks)) != NORM(sec["narration"]):
            return None, "narration mismatch"
    for s, c in zip(new, chunks):
        s["narration"] = c; s["weight"] = max(1, len(c)); s.setdefault("alt", "")
    return [s for s in new if s["narration"].strip()], note

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("workdir"); ap.add_argument("--section"); ap.add_argument("--sec", type=float, default=18)
    a = ap.parse_args(); wd = Path(a.workdir)
    js = json.loads((wd / "script.json").read_text(encoding="utf-8"))
    bak = wd / "script.before_reslice.json"
    if not bak.exists():
        shutil.copy(wd / "script.json", bak)
    for sec in js["sections"]:
        if a.section and sec["id"] != a.section:
            continue
        before = len(sec.get("slides", []))
        new, note = reslice_section(sec, a.sec)
        if new:
            sec["slides"] = new; print(f"{sec['id']:<10} {before} → {len(new)} slides ({note})")
        else:
            print(f"{sec['id']:<10} skipped ({note})")
        (wd / "script.json").write_text(json.dumps(js, ensure_ascii=False, indent=1), encoding="utf-8")
    print("total slides:", sum(len(s.get("slides", [])) for s in js["sections"]))
