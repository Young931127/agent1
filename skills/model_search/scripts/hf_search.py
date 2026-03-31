"""
搜尋 HuggingFace Hub，抓取完整指標。
支援按任務搜尋 + 模糊搜尋 Claude 提取的模型名稱。

Location: .claude/skills/model-scout/scripts/hf_search.py

Usage:
    python .claude/skills/model-scout/scripts/hf_search.py \
        --task feature-extraction \
        --from-discovered discovered_models.json \
        --limit 10 \
        --output results_hf.json

    python .claude/skills/model-scout/scripts/hf_search.py \
        --models "bge-m3" "e5-large" \
        --output results_hf.json
"""

import argparse
import json
import sys
from datetime import datetime

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


def search_by_task(task=None, query=None, language=None,
                   library=None, sort="downloads", limit=10):
    params = {"sort": sort, "direction": "-1", "limit": str(limit)}
    if query:
        params["search"] = query
    if task:
        params["pipeline_tag"] = task
    if language:
        params["language"] = language
    if library:
        params["library"] = library
    resp = requests.get("https://huggingface.co/api/models", params=params, timeout=30)
    resp.raise_for_status()
    return [parse_model(m) for m in resp.json()]


def fuzzy_search(name, limit=3):
    params = {"search": name, "sort": "downloads", "direction": "-1", "limit": str(limit)}
    resp = requests.get("https://huggingface.co/api/models", params=params, timeout=15)
    resp.raise_for_status()
    return [parse_model(m) for m in resp.json()]


def get_model_detail(model_id):
    try:
        resp = requests.get(f"https://huggingface.co/api/models/{model_id}", timeout=15)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def parse_model(m):
    info = {
        "model_name": m.get("id", ""),
        "url": f"https://huggingface.co/{m.get('id', '')}",
        "source": "huggingface",
        "task": m.get("pipeline_tag", ""),
        "library": m.get("library_name", ""),
        "downloads": m.get("downloads", 0),
        "downloads_all_time": m.get("downloadsAllTime", 0),
        "likes": m.get("likes", 0),
        "trending_score": m.get("trendingScore", 0),
        "last_updated": m.get("lastModified", ""),
        "created_at": m.get("createdAt", ""),
        "tags": m.get("tags", []),
        "license": "",
        "parameters": None,
        "benchmark_scores": {},
        "gated": m.get("gated", False),
    }

    for tag in m.get("tags", []):
        if tag.startswith("license:"):
            info["license"] = tag.replace("license:", "")
            break

    safetensors = m.get("safetensors")
    if safetensors and isinstance(safetensors, dict):
        params = safetensors.get("total")
        if not params:
            param_count = safetensors.get("parameters", {})
            if isinstance(param_count, dict):
                params = sum(param_count.values())
        if params:
            info["parameters"] = params

    model_index = m.get("model-index") or m.get("modelIndex")
    if model_index and isinstance(model_index, list):
        for entry in model_index:
            for result in entry.get("results", []):
                dataset_info = result.get("dataset", {})
                dataset_name = ""
                if isinstance(dataset_info, dict):
                    dataset_name = dataset_info.get("name", "") or dataset_info.get("type", "")
                for metric in result.get("metrics", []):
                    mt = metric.get("type", "")
                    mv = metric.get("value")
                    if mt and mv is not None:
                        key = f"{dataset_name}/{mt}" if dataset_name else mt
                        info["benchmark_scores"][key] = mv

    return info


def load_discovered_models(path):
    """讀取 Claude 產生的 discovered_models.json。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        models = data.get("models", [])
        return [m.get("name", "") for m in models if m.get("name")]
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"  Warning: cannot read {path}: {e}", file=sys.stderr)
        return []


def main():
    parser = argparse.ArgumentParser(description="搜尋 HuggingFace Hub")
    parser.add_argument("--task")
    parser.add_argument("--query")
    parser.add_argument("--language")
    parser.add_argument("--library")
    parser.add_argument("--sort", default="downloads",
                        choices=["downloads", "likes", "trending", "lastModified"])
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--models", nargs="*", default=[])
    parser.add_argument("--from-discovered", help="Claude 產生的 discovered_models.json")
    parser.add_argument("--limit-per-name", type=int, default=3)
    parser.add_argument("--output", default="results_hf.json")
    args = parser.parse_args()

    if not HAS_REQUESTS:
        print("Error: install requests", file=sys.stderr)
        sys.exit(1)

    discovered = list(args.models)
    if args.from_discovered:
        from_file = load_discovered_models(args.from_discovered)
        print(f"  Loaded {len(from_file)} models from {args.from_discovered}", file=sys.stderr)
        discovered.extend(from_file)

    if not args.task and not args.query and not discovered:
        print("Error: provide at least --task, --query, --models, or --from-discovered", file=sys.stderr)
        sys.exit(1)

    all_results = []
    existing_ids = set()

    # 1. 按任務搜尋
    if args.task or args.query:
        print("Searching by task...", file=sys.stderr)
        try:
            task_results = search_by_task(
                task=args.task, query=args.query, language=args.language,
                library=args.library, sort=args.sort, limit=args.limit
            )
            for r in task_results:
                mid = r["model_name"]
                if mid.lower() not in existing_ids:
                    detail = get_model_detail(mid)
                    if detail:
                        r = parse_model(detail)
                    existing_ids.add(mid.lower())
                    all_results.append(r)
            print(f"  Found {len(all_results)} models by task", file=sys.stderr)
        except Exception as e:
            print(f"  Task search failed: {e}", file=sys.stderr)

    # 2. 模糊搜尋 Claude 發現的模型
    if discovered:
        to_search = [m for m in discovered if m.lower() not in existing_ids]
        if to_search:
            print(f"Fuzzy searching {len(to_search)} discovered model names...", file=sys.stderr)
            for name in to_search:
                print(f"    Searching: {name}", file=sys.stderr)
                try:
                    results = fuzzy_search(name, limit=args.limit_per_name)
                    added = 0
                    for r in results:
                        mid = r["model_name"]
                        if mid.lower() not in existing_ids:
                            detail = get_model_detail(mid)
                            if detail:
                                r = parse_model(detail)
                            r["discovered_from"] = name
                            existing_ids.add(mid.lower())
                            all_results.append(r)
                            added += 1
                    print(f"      Found {added} new models", file=sys.stderr)
                except Exception as e:
                    print(f"      Failed: {e}", file=sys.stderr)

    output = {
        "source": "huggingface",
        "query": {"task": args.task, "search": args.query, "language": args.language,
                  "discovered_models": discovered},
        "searched_at": datetime.now().isoformat(),
        "count": len(all_results),
        "results": all_results,
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nTotal {len(all_results)} models, saved to {args.output}", file=sys.stderr)
    for r in all_results[:15]:
        p = r.get("parameters")
        ps = f"{p/1e6:.0f}M" if p else "?"
        d = f"  (from: {r['discovered_from']})" if r.get("discovered_from") else ""
        print(f"  {r['model_name']:<40s}  dl={r['downloads']:>8}  params={ps:<8s}{d}")


if __name__ == "__main__":
    main()