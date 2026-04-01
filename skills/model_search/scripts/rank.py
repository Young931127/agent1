"""
分層過濾與排名。

Tier 1：HF 有資料 + 社群有討論（完整公式）
Tier 2：只在社群出現，HF 搜不到（只用 buzz 排名）
Tier 3：只在 HF 有資料，社群沒討論（只用 HF 指標排名）

Location: .claude/skills/model-scout/scripts/rank.py

Usage:
    python .claude/skills/model-scout/scripts/rank.py \
        --input merged.json \
        --language zh \
        --max-stale-months 10 \
        --priority accuracy \
        --top 5 \
        --output candidates.json
"""

import argparse
import json
import math
import sys
from datetime import datetime

def classify_tier(model):
    has_hf = model.get("source") == "huggingface" and model.get("downloads", 0) > 0
    has_buzz = model.get("mention_count", 0) > 0
    if has_hf and has_buzz:
        return 1
    elif has_buzz and not has_hf:
        return 2
    else:
        return 3


def filter_candidates(candidates, args):
    filtered = []
    now = datetime.now()

    for c in candidates:
        # 語言過濾
        if args.language:
            tags = [t.lower() for t in c.get("tags", [])]
            lang_tag = f"language:{args.language.lower()}"
            has_lang = any(t.startswith("language:") for t in tags)
            if has_lang and lang_tag not in tags:
                continue

        # 大小過濾
        if args.max_size_mb and c.get("parameters"):
            est_mb = c["parameters"] * 2 / 1e6
            if est_mb > args.max_size_mb:
                continue

        # 更新時間過濾：超過 N 個月沒更新的移除
        if args.max_stale_months:
            last_updated = c.get("last_updated", "")
            if last_updated:
                try:
                    dt = datetime.fromisoformat(last_updated.replace("Z", "+00:00").replace("+00:00", ""))
                    months_ago = (now - dt).days / 30
                    if months_ago > args.max_stale_months:
                        continue
                except (ValueError, TypeError):
                    pass
            # 沒有更新時間的模型保留（可能是 web-search-only）

        filtered.append(c)
    return filtered


def _safe_max(candidates, key, default=1):
    return max((c.get(key, 0) for c in candidates), default=default) or default


def _recency(last_updated):
    if not last_updated:
        return 0.5
    try:
        dt = datetime.fromisoformat(last_updated.replace("Z", "+00:00").replace("+00:00", ""))
        months = (datetime.now() - dt).days / 30
        return max(0.0, 1.0 - months * 0.05)
    except (ValueError, TypeError):
        return 0.5


def _benchmark(scores_dict):
    if not isinstance(scores_dict, dict):
        return 0.0
    vals = [v for v in scores_dict.values() if isinstance(v, (int, float))]
    if not vals:
        return 0.0
    b = max(vals)
    return b / 100 if b > 1 else b


def _efficiency(benchmark, params):
    if not params or not isinstance(params, (int, float)) or params <= 0 or benchmark <= 0:
        return 0.5
    return min(benchmark / math.log2(params + 1) * 10, 1.0)


def compute_tier1(candidates, priority):
    if not candidates:
        return candidates
    max_dl = _safe_max(candidates, "downloads")
    max_likes = _safe_max(candidates, "likes")
    max_trend = _safe_max(candidates, "trending_score")
    max_mentions = _safe_max(candidates, "mention_count")
    max_diversity = _safe_max(candidates, "source_diversity")

    weights = {
        "accuracy":   {"benchmark": 0.35, "adoption": 0.15, "recency": 0.15, "efficiency": 0.15, "buzz": 0.20},
        "speed":      {"benchmark": 0.20, "adoption": 0.10, "recency": 0.15, "efficiency": 0.35, "buzz": 0.20},
        "small":      {"benchmark": 0.20, "adoption": 0.10, "recency": 0.15, "efficiency": 0.35, "buzz": 0.20},
        "popularity": {"benchmark": 0.15, "adoption": 0.30, "recency": 0.15, "efficiency": 0.10, "buzz": 0.30},
        "balanced":   {"benchmark": 0.25, "adoption": 0.20, "recency": 0.15, "efficiency": 0.15, "buzz": 0.25},
    }
    w = weights.get(priority, weights["balanced"])

    for c in candidates:
        adoption = (0.4 * c.get("downloads", 0) / max_dl
                    + 0.3 * c.get("likes", 0) / max_likes
                    + 0.3 * c.get("trending_score", 0) / max_trend)
        recency = _recency(c.get("last_updated", ""))
        benchmark = _benchmark(c.get("benchmark_scores", {}))
        efficiency = _efficiency(benchmark, c.get("parameters"))
        buzz = (0.6 * c.get("mention_count", 0) / max_mentions
                + 0.4 * c.get("source_diversity", 0) / max_diversity)

        score = (w["benchmark"] * benchmark + w["adoption"] * adoption
                 + w["recency"] * recency + w["efficiency"] * efficiency
                 + w["buzz"] * buzz)

        c["_scores"] = {
            "benchmark": round(benchmark, 3), "adoption": round(adoption, 3),
            "recency": round(recency, 3), "efficiency": round(efficiency, 3),
            "buzz": round(buzz, 3), "composite": round(score, 3),
        }
    candidates.sort(key=lambda c: c["_scores"]["composite"], reverse=True)
    return candidates


def compute_tier2(candidates):
    if not candidates:
        return candidates
    max_m = _safe_max(candidates, "mention_count")
    max_d = _safe_max(candidates, "source_diversity")
    for c in candidates:
        buzz = 0.6 * c.get("mention_count", 0) / max_m + 0.4 * c.get("source_diversity", 0) / max_d
        c["_scores"] = {"buzz": round(buzz, 3), "composite": round(buzz, 3)}
    candidates.sort(key=lambda c: c["_scores"]["composite"], reverse=True)
    return candidates


def compute_tier3(candidates, priority):
    if not candidates:
        return candidates
    max_dl = _safe_max(candidates, "downloads")
    max_likes = _safe_max(candidates, "likes")
    max_trend = _safe_max(candidates, "trending_score")

    weights = {
        "accuracy":   {"benchmark": 0.40, "adoption": 0.20, "recency": 0.20, "efficiency": 0.20},
        "speed":      {"benchmark": 0.25, "adoption": 0.15, "recency": 0.20, "efficiency": 0.40},
        "small":      {"benchmark": 0.25, "adoption": 0.15, "recency": 0.20, "efficiency": 0.40},
        "popularity": {"benchmark": 0.15, "adoption": 0.50, "recency": 0.20, "efficiency": 0.15},
        "balanced":   {"benchmark": 0.30, "adoption": 0.30, "recency": 0.20, "efficiency": 0.20},
    }
    w = weights.get(priority, weights["balanced"])

    for c in candidates:
        adoption = (0.4 * c.get("downloads", 0) / max_dl
                    + 0.3 * c.get("likes", 0) / max_likes
                    + 0.3 * c.get("trending_score", 0) / max_trend)
        recency = _recency(c.get("last_updated", ""))
        benchmark = _benchmark(c.get("benchmark_scores", {}))
        efficiency = _efficiency(benchmark, c.get("parameters"))

        score = (w["benchmark"] * benchmark + w["adoption"] * adoption
                 + w["recency"] * recency + w["efficiency"] * efficiency)

        c["_scores"] = {
            "benchmark": round(benchmark, 3), "adoption": round(adoption, 3),
            "recency": round(recency, 3), "efficiency": round(efficiency, 3),
            "composite": round(score, 3),
        }
    candidates.sort(key=lambda c: c["_scores"]["composite"], reverse=True)
    return candidates


def main():
    parser = argparse.ArgumentParser(description="分層過濾與排名")
    parser.add_argument("--input", required=True)
    parser.add_argument("--max-size-mb", type=int)
    parser.add_argument("--language")
    parser.add_argument("--max-stale-months", type=int, default=10,
                        help="超過幾個月沒更新的模型移除（預設 10）")
    parser.add_argument("--priority", default="balanced",
                        choices=["accuracy", "speed", "small", "popularity", "balanced"])
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--output", default="candidates.json")
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)
    candidates = data.get("results", [])
    print(f"Loaded {len(candidates)} candidates", file=sys.stderr)

    filtered = filter_candidates(candidates, args)
    print(f"After filter: {len(filtered)}", file=sys.stderr)

    tier1, tier2, tier3 = [], [], []
    for c in filtered:
        t = classify_tier(c)
        c["tier"] = t
        [None, tier1, tier2, tier3][t].append(c)

    print(f"Tier 1: {len(tier1)}  Tier 2: {len(tier2)}  Tier 3: {len(tier3)}", file=sys.stderr)

    tier1 = compute_tier1(tier1, args.priority)[:args.top]
    tier2 = compute_tier2(tier2)[:args.top]
    tier3 = compute_tier3(tier3, args.priority)[:args.top]

    output = {
        "query": {
            "hard_constraints": {"max_size_mb": args.max_size_mb, "language": args.language, "max_stale_months": args.max_stale_months},
            "soft_preferences": {"priority": args.priority},
            "ranked_at": datetime.now().isoformat(),
        },
        "summary": {
            "total_before_filter": len(candidates), "total_after_filter": len(filtered),
            "tier1_count": len(tier1), "tier2_count": len(tier2), "tier3_count": len(tier3),
        },
        "tier1": tier1, "tier2": tier2, "tier3": tier3,
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    def pt(name, models):
        if not models:
            print(f"\n{name}: (empty)", file=sys.stderr)
            return
        print(f"\n{name}:", file=sys.stderr)
        print(f"  {'Model':<40s} {'Score':>6} {'Downloads':>10} {'Mentions':>8}", file=sys.stderr)
        print(f"  {'-'*68}", file=sys.stderr)
        for m in models:
            print(f"  {m.get('model_name','?'):<40s} {m.get('_scores',{}).get('composite',0):>6.3f} "
                  f"{m.get('downloads',0):>10} {m.get('mention_count',0):>8}", file=sys.stderr)

    pt("Tier 1 — 強力推薦", tier1)
    pt("Tier 2 — 值得關注", tier2)
    pt("Tier 3 — 僅供參考", tier3)


if __name__ == "__main__":
    main()