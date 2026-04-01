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


def repo_part(name):
    """從 'org/model-name' 取出 'model-name'，否則原樣回傳。"""
    return name.split("/")[-1] if "/" in name else name


def names_match(disc_short, hf_short):
    """
    模糊比對 discovered 的簡稱與 HF 的正式 repo 名稱。
    例如 'gemma' 可比中 'gemma-2-9b'；'llama-3' 可比中 'llama-3-8b-instruct'。
    """
    if disc_short == hf_short:
        return True
    # 其中一個是另一個的前綴/子字串
    if hf_short.startswith(disc_short) or disc_short.startswith(hf_short):
        return True
    return False


def find_buzz(hf_key, buzz_lookup, disc_models_short):
    """
    先做 exact lookup，再 fallback 到 fuzzy 比對。
    disc_models_short: list of (short_name, entry)
    """
    hf_short = repo_part(hf_key)
    # exact
    matched = buzz_lookup.get(hf_key) or buzz_lookup.get(hf_short)
    if matched:
        return matched
    # fuzzy
    for disc_short, entry in disc_models_short:
        if names_match(disc_short, hf_short):
            return entry
    return None


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

    # 建立 buzz 指標 lookup（exact match 用）
    buzz_lookup = {}
    for m in disc_models:
        name = m.get("name", "").lower()
        short = repo_part(name)
        buzz_lookup[name] = m
        buzz_lookup[short] = m

    # 預先建立 (short_name, entry) list 供 fuzzy 比對用
    disc_shorts = [(repo_part(m.get("name", "").lower()), m) for m in disc_models]

    # 去重並附加 buzz 指標
    seen = {}
    for r in hf_results:
        name = r.get("model_name", "").lower().strip()
        if name:
            seen[name] = r

    # 附加 buzz 指標到 HF 模型
    for name_key, model in seen.items():
        matched = find_buzz(name_key, buzz_lookup, disc_shorts)
        if matched:
            model["mention_count"] = matched.get("mention_count", 0)
            model["source_diversity"] = matched.get("source_diversity", 0)
            model["mentioned_sources"] = matched.get("sources", [])
        else:
            model["mention_count"] = 0
            model["source_diversity"] = 0
            model["mentioned_sources"] = []

    # 找出 Claude 發現但 HF 搜不到的模型（fuzzy 比對）
    web_only = []
    for m in disc_models:
        disc_short = repo_part(m.get("name", "").lower())
        found = any(
            names_match(disc_short, repo_part(hf_key))
            for hf_key in seen
        )
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
