"""
合併 HuggingFace 結果與 Claude 提取的 buzz 指標，去重。

Location: .claude/skills/model-scout/scripts/merge.py

Usage:
    python .claude/skills/model-scout/scripts/merge.py \
        --hf results_hf.json \
        --discovered discovered_models.json \
        --output merged.json
"""

import argparse
import json
import sys
from datetime import datetime


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"  Warning: cannot read {path}: {e}", file=sys.stderr)
        return {}


def main():
    parser = argparse.ArgumentParser(description="合併搜尋結果與 buzz 指標")
    parser.add_argument("--hf", required=True, help="HuggingFace 搜尋結果")
    parser.add_argument("--discovered", required=True, help="Claude 產生的 discovered_models.json")
    parser.add_argument("--output", default="merged.json")
    args = parser.parse_args()

    # 讀取 HF 結果
    hf_data = load_json(args.hf)
    hf_results = hf_data.get("results", [])
    print(f"  Loaded {len(hf_results)} models from HF", file=sys.stderr)

    # 讀取 Claude 提取的模型資訊
    disc_data = load_json(args.discovered)
    disc_models = disc_data.get("models", [])
    print(f"  Loaded {len(disc_models)} discovered models", file=sys.stderr)

    # 建立 buzz 指標 lookup（用小寫名稱比對）
    buzz_lookup = {}
    for m in disc_models:
        name = m.get("name", "").lower()
        short = name.split("/")[-1] if "/" in name else name
        buzz_lookup[name] = m
        buzz_lookup[short] = m

    # 去重並附加 buzz 指標
    seen = {}
    for r in hf_results:
        name = r.get("model_name", "").lower().strip()
        if name:
            seen[name] = r

    # 附加 buzz 指標到 HF 模型
    for name_key, model in seen.items():
        short = name_key.split("/")[-1] if "/" in name_key else name_key
        matched = buzz_lookup.get(name_key) or buzz_lookup.get(short)

        if matched:
            model["mention_count"] = matched.get("mention_count", 0)
            model["source_diversity"] = matched.get("source_diversity", 0)
            model["mentioned_sources"] = matched.get("sources", [])
        else:
            model["mention_count"] = 0
            model["source_diversity"] = 0
            model["mentioned_sources"] = []

    # 找出 Claude 發現但 HF 搜不到的模型
    web_only = []
    for m in disc_models:
        name = m.get("name", "").lower()
        short = name.split("/")[-1] if "/" in name else name
        found = any(short == k.split("/")[-1] or name == k for k in seen)
        if not found:
            web_only.append({
                "model_name": m.get("name", ""),
                "url": "",
                "source": "web-search-only",
                "mention_count": m.get("mention_count", 0),
                "source_diversity": m.get("source_diversity", 0),
                "mentioned_sources": m.get("sources", []),
            })

    all_models = list(seen.values()) + web_only

    output = {
        "search_sources": ["huggingface", "web-search"],
        "total_hf": len(hf_results),
        "total_web_only": len(web_only),
        "total_merged": len(all_models),
        "merged_at": datetime.now().isoformat(),
        "results": all_models,
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nMerged: {len(hf_results)} HF + {len(web_only)} web-only = {len(all_models)} total",
          file=sys.stderr)
    print(f"\n{'Model':<40s} {'Source':<16s} {'Downloads':>10} {'Mentions':>8}", file=sys.stderr)
    print("-" * 78, file=sys.stderr)
    for m in all_models:
        print(f"{m.get('model_name','?'):<40s} {m.get('source','?'):<16s} "
              f"{m.get('downloads',0):>10} {m.get('mention_count',0):>8}", file=sys.stderr)

"""
合併 HuggingFace 結果與 Claude 提取的 buzz 指標，去重。

Location: .claude/skills/model-scout/scripts/merge.py

Usage:
    python .claude/skills/model-scout/scripts/merge.py \
        --hf results_hf.json \
        --discovered discovered_models.json \
        --output merged.json
"""

import argparse
import json
import sys
from datetime import datetime


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"  Warning: cannot read {path}: {e}", file=sys.stderr)
        return {}


def main():
    parser = argparse.ArgumentParser(description="合併搜尋結果與 buzz 指標")
    parser.add_argument("--hf", required=True, help="HuggingFace 搜尋結果")
    parser.add_argument("--discovered", required=True, help="Claude 產生的 discovered_models.json")
    parser.add_argument("--output", default="merged.json")
    args = parser.parse_args()

    # 讀取 HF 結果
    hf_data = load_json(args.hf)
    hf_results = hf_data.get("results", [])
    print(f"  Loaded {len(hf_results)} models from HF", file=sys.stderr)

    # 讀取 Claude 提取的模型資訊
    disc_data = load_json(args.discovered)
    disc_models = disc_data.get("models", [])
    print(f"  Loaded {len(disc_models)} discovered models", file=sys.stderr)

    # 建立 buzz 指標 lookup（用小寫名稱比對）
    buzz_lookup = {}
    for m in disc_models:
        name = m.get("name", "").lower()
        short = name.split("/")[-1] if "/" in name else name
        buzz_lookup[name] = m
        buzz_lookup[short] = m

    # 去重並附加 buzz 指標
    seen = {}
    for r in hf_results:
        name = r.get("model_name", "").lower().strip()
        if name:
            seen[name] = r

    # 附加 buzz 指標到 HF 模型
    for name_key, model in seen.items():
        short = name_key.split("/")[-1] if "/" in name_key else name_key
        matched = buzz_lookup.get(name_key) or buzz_lookup.get(short)

        if matched:
            model["mention_count"] = matched.get("mention_count", 0)
            model["source_diversity"] = matched.get("source_diversity", 0)
            model["mentioned_sources"] = matched.get("sources", [])
        else:
            model["mention_count"] = 0
            model["source_diversity"] = 0
            model["mentioned_sources"] = []

    # 找出 Claude 發現但 HF 搜不到的模型
    web_only = []
    for m in disc_models:
        name = m.get("name", "").lower()
        short = name.split("/")[-1] if "/" in name else name
        found = any(short == k.split("/")[-1] or name == k for k in seen)
        if not found:
            web_only.append({
                "model_name": m.get("name", ""),
                "url": "",
                "source": "web-search-only",
                "mention_count": m.get("mention_count", 0),
                "source_diversity": m.get("source_diversity", 0),
                "mentioned_sources": m.get("sources", []),
            })

    all_models = list(seen.values()) + web_only

    output = {
        "search_sources": ["huggingface", "web-search"],
        "total_hf": len(hf_results),
        "total_web_only": len(web_only),
        "total_merged": len(all_models),
        "merged_at": datetime.now().isoformat(),
        "results": all_models,
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nMerged: {len(hf_results)} HF + {len(web_only)} web-only = {len(all_models)} total",
          file=sys.stderr)
    print(f"\n{'Model':<40s} {'Source':<16s} {'Downloads':>10} {'Mentions':>8}", file=sys.stderr)
    print("-" * 78, file=sys.stderr)
    for m in all_models:
        print(f"{m.get('model_name','?'):<40s} {m.get('source','?'):<16s} "
              f"{m.get('downloads',0):>10} {m.get('mention_count',0):>8}", file=sys.stderr)


if __name__ == "__main__":
    main()
if __name__ == "__main__":
    main()