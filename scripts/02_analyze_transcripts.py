#!/usr/bin/env python3
"""자막(vtt) → 영상 구성 분석. 01 실행 후 VPS에서 실행.

out: analysis/structure.md
  - 각 영상: 길이, 분당 글자수(말속도), 처음 60초 훅 텍스트, 챕터 수/평균 챕터 길이,
    CTA 등장 타이밍(チャンネル登録/概要欄/書籍), 숫자 밀도(万円/歳 등장 횟수)
  - 전체: 중앙값 요약 → 대본 템플릿 파라미터로 사용
"""
import json, re, statistics, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUBS = ROOT / "data" / "subs"; META = ROOT / "data" / "channel_videos.json"
OUT = ROOT / "analysis" / "structure.md"

CTA = {"登録": r"チャンネル登録|登録", "概要欄": r"概要欄", "書籍": r"本|書籍|Amazon", "高評価": r"高評価|いいね", "次回": r"次の動画|関連動画"}

def parse_vtt(p):
    """YouTube 자동자막은 롤링 방식(이전 줄이 다음 큐에 다시 포함)이라 그대로 합치면 2~3배로 부풀어진다.
    각 큐에서 '누적 텍스트의 끝과 겹치는 부분'을 잘라내고 새로 추가된 글자만 이어붙인다."""
    cues, acc = [], ""
    for block in p.read_text(encoding="utf-8").split("\n\n"):
        m = re.search(r"(\d+):(\d+):(\d+)\.(\d+) --> ", block)
        if not m:
            continue
        t = int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3])
        lines = block.split("\n")[1:]
        text = "".join(re.sub(r"<[^>]+>", "", l) for l in lines if "-->" not in l).strip()
        text = re.sub(r"\[(音楽|拍手|笑い)\]", "", text).strip()
        if not text:
            continue
        # 누적 끝과 겹치는 최장 접두사 제거
        tail = acc[-len(text):] if acc else ""
        k = 0
        for n in range(min(len(text), len(tail)), 0, -1):
            if tail.endswith(text[:n]):
                k = n; break
        new = text[k:]
        if new:
            acc += new; cues.append((t, new))
    return cues

def analyze(vid, meta):
    cues = parse_vtt(SUBS / f"{vid}.ja.vtt")
    if not cues:
        return None
    total = meta.get("duration") or cues[-1][0]
    full = "".join(t for _, t in cues)
    hook = "".join(t for s, t in cues if s < 60)
    cta_times = {k: [s for s, t in cues if re.search(p, t)][:3] for k, p in CTA.items()}
    chapters = meta.get("chapters") or []
    chap_len = [(b - a) for (a, _), (b, _) in zip(chapters, chapters[1:])] if len(chapters) > 1 else []
    return dict(id=vid, title=meta.get("title"), views=meta.get("view_count"), minutes=round(total / 60, 1),
                chars_per_min=round(len(full) / (total / 60)), hook=hook[:300],
                n_chapters=len(chapters), chap_median_min=round(statistics.median(chap_len) / 60, 1) if chap_len else None,
                chapter_titles=[c[1] for c in chapters][:12], cta=cta_times,
                num_density=len(re.findall(r"\d+万円|\d+歳|\d+％|\d+%", full)))

if __name__ == "__main__":
    metas = {m["id"]: m for m in json.loads(META.read_text(encoding="utf-8"))}
    res = [r for vid in [p.stem.split(".")[0] for p in SUBS.glob("*.vtt")] if (r := analyze(vid, metas.get(vid, {})))]
    if not res:
        sys.exit("no subtitles in data/subs → skip (bgutil PO token server or config/cookies.txt needed)")
    res.sort(key=lambda r: r["views"] or 0, reverse=True)
    L = ["# 벤치마크 영상 구성 분석\n", f"분석 {len(res)}본\n",
         f"- 길이 중앙값: {statistics.median([r['minutes'] for r in res])}분",
         f"- 말속도 중앙값: {statistics.median([r['chars_per_min'] for r in res])}자/분 (→ 대본 글자수 = 목표분수 × 이 값)",
         f"- 챕터 수 중앙값: {statistics.median([r['n_chapters'] for r in res if r['n_chapters']]) if any(r['n_chapters'] for r in res) else 'n/a'}",
         f"- 숫자 밀도 중앙값: {statistics.median([r['num_density'] for r in res])}회/본\n"]
    for r in res:
        L += [f"## {r['title']}", f"- {r['views']:,} views | {r['minutes']}분 | {r['chars_per_min']}자/분 | 챕터 {r['n_chapters']} (중앙 {r['chap_median_min']}분)",
              f"- CTA 초: {json.dumps(r['cta'], ensure_ascii=False)}", f"- 챕터: {' / '.join(r['chapter_titles'])}",
              f"- 훅(0-60s): {r['hook']}", ""]
    OUT.write_text("\n".join(L), encoding="utf-8"); print("\n".join(L[:8]))
