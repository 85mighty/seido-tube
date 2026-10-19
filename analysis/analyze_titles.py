#!/usr/bin/env python3
"""Benchmark title/topic analysis for @ryonurse (節約看護師りょう).

Input : data/yutura_raw.txt   (title | views | date | src)
Output: analysis/videos.csv, analysis/topic_ranking.csv, analysis/title_patterns.csv, analysis/summary.md

'latest' views are yutura snapshots taken ~1–2 weeks after upload → treated as EARLY VELOCITY.
'popular' views are current all-time totals (2026-10-19).
"""
import csv, re, statistics, sys
from collections import defaultdict, Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "yutura_raw.txt"
OUT = ROOT / "analysis"
OUT.mkdir(exist_ok=True)

def parse_views(s):
    s = s.strip().replace("回", "").replace(",", "")
    if s in ("?", ""):
        return None
    m = re.match(r"(?:(\d+)万)?(\d*)", s)
    man = int(m.group(1)) if m.group(1) else 0
    rest = int(m.group(2)) if m.group(2) else 0
    return man * 10000 + rest

def parse_date(s):
    m = re.search(r"(\d{4})年(\d{1,2})月(?:(\d{1,2})日)?", s)
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3) or 1):02d}"

# ---- topic taxonomy (first match wins; order = specificity) ----
TOPICS = [
    ("給付金・上乗せ申請",      r"給付金|支給|上乗せ|助成金|振替加算|加給年金|調整給付"),
    ("働きながら年金(在職)",    r"在職老齢|在職定時|働きながら|働く人|働くと|再雇用|週10時間|パート"),
    ("受給開始年齢",            r"受給開始|〇歳|○歳|◯歳|何歳|繰り上げ|繰り下げ|65歳が正解|60歳が最強|60歳で年金"),
    ("年金改正・新ルール",      r"改正|新ルール|激変|ルール|改革"),
    ("定年後の健康保険・マイナ", r"健康保険|任意継続|国民健康保険|保険証|マイナ|介護保険料"),
    ("通知書・定期便チェック",   r"通知書|定期便|源泉徴収票"),
    ("税金・手取り・非課税",     r"税金|手取り|住民税|確定申告|106万|壁|高額療養費|医療費"),
    ("定年退職の手続き",        r"定年|退職"),
    ("老後資金・平均額の現実",   r"厚生年金1[67]万|平均|老後資金|貯金|老後貧乏|老後破綻|買ってはいけない|買い物|手遅れ|後悔|崩壊"),
    ("遺族年金",                r"遺族"),
    ("NISA・投資",              r"NISA"),
]

def topic_of(title):
    for name, pat in TOPICS:
        if re.search(pat, title):
            return name
    return "その他"

# ---- title-pattern features ----
PATTERNS = {
    "【知らないと大損/損】":   r"【知らないと(大損|損|危険|0円)",
    "【年号+新ルール/改正】":  r"【20\d\d年",
    "【超重要/緊急/超速報】":  r"【(超重要|緊急|超速報|警告|絶対)",
    "【悲報/衝撃/後悔続出】":  r"【(悲報|衝撃|後悔続出|勘違い続出|申請忘れ続出|老後貧乏|老後の現実)",
    "【神改正】":              r"【神改正",
    "金額を明示 (○万円)":      r"\d+万円|\d+万",
    "年齢を明示 (○歳/○代)":    r"\d+歳|\d+代",
    "数字リスト (○選)":        r"\d選",
    "伏せ字 (〇/○/◯/？)":      r"〇|○|◯|？万|？％|◯％",
    "命令形CTA (確認して/申請して)": r"(確認して|申請して|チェックして|対策して|備えて)",
    "末尾【補足タグ】":        r"】$|】\s*$",
}

rows = []
for line in RAW.read_text(encoding="utf-8").splitlines():
    if not line.strip() or line.startswith("#"):
        continue
    parts = [p.strip() for p in line.split("|")]
    if len(parts) < 4:
        continue
    title, views, date, src = parts[:4]
    rows.append(dict(title=title, views=parse_views(views), date=parse_date(date), src=src))

# merge: same title → keep early(latest) + current(popular)
by_title = {}
for r in rows:
    d = by_title.setdefault(r["title"], dict(title=r["title"], date=r["date"], early=None, current=None))
    if r["src"] == "latest":
        d["early"] = max(d["early"] or 0, r["views"] or 0) or None
    elif r["src"] == "popular":
        d["current"] = r["views"]
    else:
        d["date"] = r["date"]
videos = sorted(by_title.values(), key=lambda v: v["date"], reverse=True)
for v in videos:
    v["topic"] = topic_of(v["title"])
    v["patterns"] = ";".join(k for k, p in PATTERNS.items() if re.search(p, v["title"]))

with open(OUT / "videos.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["date", "topic", "early", "current", "patterns", "title"])
    w.writeheader()
    for v in videos:
        w.writerow({k: v.get(k) for k in w.fieldnames})

# ---- topic ranking ----
agg = defaultdict(list)
for v in videos:
    if v["early"]:
        agg[v["topic"]].append(v)
recent_cut = "2025-10-01"
trank = []
for t, vs in agg.items():
    early = [v["early"] for v in vs]
    recent = [v["early"] for v in vs if v["date"] >= recent_cut]
    hits = [v for v in vs if v["early"] >= 150000]
    mega = [v for v in by_title.values() if v["topic"] == t and v["current"]]
    trank.append(dict(
        topic=t, n=len(vs), median_early=int(statistics.median(early)),
        mean_early=int(statistics.mean(early)), max_early=max(early),
        n_recent=len(recent), median_recent=int(statistics.median(recent)) if recent else 0,
        hits_15万plus=len(hits), top10_alltime=len(mega),
        score=int(statistics.median(early) * (1 + 0.3 * len(hits)) * (1 + 0.5 * len(mega))),
    ))
trank.sort(key=lambda r: r["score"], reverse=True)
with open(OUT / "topic_ranking.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(trank[0].keys())); w.writeheader(); w.writerows(trank)

# ---- pattern stats ----
pstats = []
all_early = [v["early"] for v in videos if v["early"]]
base = statistics.median(all_early)
for name, pat in PATTERNS.items():
    with_ = [v["early"] for v in videos if v["early"] and re.search(pat, v["title"])]
    without = [v["early"] for v in videos if v["early"] and not re.search(pat, v["title"])]
    pstats.append(dict(pattern=name, n=len(with_),
                       share=f"{len(with_)/len(all_early):.0%}",
                       median_with=int(statistics.median(with_)) if with_ else 0,
                       median_without=int(statistics.median(without)) if without else 0,
                       lift=round(statistics.median(with_)/statistics.median(without), 2) if with_ and without else None))
pstats.sort(key=lambda r: (r["lift"] or 0), reverse=True)
with open(OUT / "title_patterns.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(pstats[0].keys())); w.writeheader(); w.writerows(pstats)

# ---- summary ----
L = []
L.append(f"# 節約看護師りょう ベンチマーク — タイトル/テーマ分析\n")
L.append(f"- 分析対象: {len(videos)}本 (2024-06 〜 2026-10), 早期再生数あり {len(all_early)}本, 全体中央値(早期) {int(base):,}")
L.append(f"- 'early' = 投稿後1〜2週の再生数スナップショット(yutura), 'current' = 2026-10-19 時点累計(上位10本のみ)\n")
L.append("## テーマ別ランキング (score = 早期中央値 × ヒット補正 × 殿堂入り補正)\n")
L.append("| # | テーマ | 本数 | 早期中央値 | 早期最大 | 直近12ヶ月本数/中央値 | 15万+ | 全期間TOP10 | score |")
L.append("|---|---|---|---|---|---|---|---|---|")
for i, r in enumerate(trank, 1):
    L.append(f"| {i} | {r['topic']} | {r['n']} | {r['median_early']:,} | {r['max_early']:,} | {r['n_recent']} / {r['median_recent']:,} | {r['hits_15万plus']} | {r['top10_alltime']} | {r['score']:,} |")
L.append("\n## タイトル型の効き目 (早期中央値 あり/なし)\n")
L.append("| 型 | 使用本数 | 比率 | 中央値(あり) | 中央値(なし) | lift |")
L.append("|---|---|---|---|---|---|")
for r in pstats:
    L.append(f"| {r['pattern']} | {r['n']} | {r['share']} | {r['median_with']:,} | {r['median_without']:,} | {r['lift']} |")
L.append("\n## 早期再生数 TOP15\n")
for v in sorted([v for v in videos if v["early"]], key=lambda v: v["early"], reverse=True)[:15]:
    L.append(f"- {v['early']:>9,} | {v['date']} | {v['topic']} | {v['title']}")
L.append("\n## 全期間 累計TOP10 (2026-10-19)\n")
for v in sorted([v for v in videos if v["current"]], key=lambda v: v["current"], reverse=True):
    L.append(f"- {v['current']:>10,} | {v['date']} | {v['topic']} | {v['title']}")
# cadence
dates = sorted(v["date"] for v in videos if v["date"] >= "2025-01-01")
L.append(f"\n## 投稿頻度\n- 2025-01 以降 {len(dates)}本 → ほぼ毎週金曜 19:00 固定 (週1本)")
(OUT / "summary.md").write_text("\n".join(L), encoding="utf-8")
print("\n".join(L))
