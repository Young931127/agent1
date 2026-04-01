"""
根據使用者需求搜尋網路，儲存原始結果。不做任何模型名稱提取。

Location: .claude/skills/model-scout/scripts/web_search.py

API key 從 .env 檔案讀取（SERPER_API_KEY=xxx）

Usage:
    python .claude/skills/model-scout/scripts/web_search.py \
        --task "embedding" \
        --output results_web.json

    python .claude/skills/model-scout/scripts/web_search.py \
        --task "chinese embedding model" \
        --output results_web.json
"""

import argparse
import json
import os
import sys
from datetime import datetime

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

SERPER_URL = "https://google.serper.dev/search"


def load_api_key():
    key = os.environ.get("SERPER_API_KEY")
    if key:
        return key
    for path in [".env", "../.env", "../../.env"]:
        if os.path.exists(path):
            with open(path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("SERPER_API_KEY="):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def build_queries(task):
    return [
        {"query": f"best {task} model 2026", "purpose": "recommendation"},
        {"query": f"{task} model comparison benchmark", "purpose": "comparison"},
        {"query": f"{task} leaderboard 2026", "purpose": "leaderboard"},
        {"query": f"{task} model recommendation reddit", "purpose": "community"},
        {"query": f"latest {task} model state of the art", "purpose": "new_models"},
    ]


def search_serper(query, api_key, limit=10):
    headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
    payload = {"q": query, "num": limit}
    resp = requests.post(SERPER_URL, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    results = []
    for item in resp.json().get("organic", []):
        results.append({
            "position": item.get("position"),
            "title": item.get("title", ""),
            "url": item.get("link", ""),
            "snippet": item.get("snippet", ""),
            "displayed_url": item.get("displayedLink", ""),
        })
    return results


def main():
    parser = argparse.ArgumentParser(description="搜尋網路，儲存原始結果")
    parser.add_argument("--task", required=True, help="任務描述")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--output", default="results_web.json")
    args = parser.parse_args()

    if not HAS_REQUESTS:
        print("Error: install requests", file=sys.stderr)
        sys.exit(1)

    api_key = load_api_key()
    if not api_key:
        print("Error: SERPER_API_KEY not found", file=sys.stderr)
        print("  請在 .env 檔案中加入: SERPER_API_KEY=your_key_here", file=sys.stderr)
        sys.exit(1)

    queries = build_queries(args.task)

    print(f"Generated {len(queries)} queries for task: {args.task}", file=sys.stderr)

    all_results = []
    for item in queries:
        q = item["query"]
        purpose = item["purpose"]
        print(f"  Searching [{purpose}]: {q}", file=sys.stderr)
        try:
            results = search_serper(q, api_key, limit=args.limit)
            for r in results:
                r["search_purpose"] = purpose
                r["search_query"] = q
            all_results.extend(results)
            print(f"    Found {len(results)} results", file=sys.stderr)
        except Exception as e:
            print(f"    Failed: {e}", file=sys.stderr)

    # URL 去重
    seen_urls = set()
    deduped = []
    for r in all_results:
        url = r.get("url", "").rstrip("/").lower()
        if url and url not in seen_urls:
            seen_urls.add(url)
            deduped.append(r)

    output = {
        "source": "web-search",
        "query": {"task": args.task, "total_queries": len(queries)},
        "searched_at": datetime.now().isoformat(),
        "count": len(deduped),
        "results": deduped,
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nTotal {len(deduped)} unique results, saved to {args.output}", file=sys.stderr)
    for r in deduped[:10]:
        print(f"  [{r.get('search_purpose','')}] {r['title'][:60]}", file=sys.stderr)
        print(f"    {r['url'][:80]}", file=sys.stderr)


if __name__ == "__main__":
    main()