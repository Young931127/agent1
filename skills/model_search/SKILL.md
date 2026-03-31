---
name: model-scout
description: >
  搜尋並篩選符合使用者需求的 AI/ML 模型，產出候選模型排名清單。使用此 skill 當
  使用者要求尋找、搜尋、推薦、比較 AI/ML 模型時。觸發詞包括：「幫我找模型」、
  「推薦一個模型」、「什麼模型適合」、「最新的 embedding 模型」、「找一個文字分類
  模型」、「比較可用的模型」。本 skill 不需要使用者的資料集，排名完全基於公開指標。
---

# Model Scout

搜尋 AI/ML 模型並根據公開指標篩選排名，產出候選清單。

## 運作方式

- **腳本自動化**：網路搜尋、HuggingFace API 查詢、合併去重、分層過濾排名
- **Claude 判斷**：理解需求、從搜尋結果中提取模型名稱和 buzz 指標、解讀摘要、呈現報告

## 與其他 skill 的關係

- 產出 `candidates.json`，供 **model-bench** 讀取進行測試
- 不涉及使用者的資料集

## 流程

### Step 1：理解需求（Claude 負責）

從使用者的描述中提取以下資訊，不清楚就主動詢問：

**硬條件（過濾用）**：
- 任務類型（對應 HuggingFace pipeline_tag）
- 模型大小上限
- 語言支援
- 框架偏好

**軟偏好（排名用）**：
- 優先考量：accuracy / speed / small / popularity / balanced

**判斷流程範圍**：
- 使用者指定了具體模型名稱 → 跳過 Step 2-3，直接到 Step 4 查 HF 詳細資料
- 需求明確且範圍窄 → 可跳過 Step 2-3
- 需要廣泛比較 → 執行完整流程

### Step 2：網路探索（自動化）

```bash
pip install requests 2>/dev/null || true

python .claude/skills/model-scout/scripts/web_search.py \
    --task "{task_description}" \
    --output results_web.json
```

腳本使用 Serper API（API key 從 `.env` 讀取：`SERPER_API_KEY=xxx`）。
腳本只負責搜尋和去重，不做任何模型名稱提取。

### Step 3：提取模型名稱與 buzz 指標（Claude 負責）

閱讀 `results_web.json` 中每筆搜尋結果的 `title`、`snippet`、`url`，完成以下工作：

1. **提取模型名稱**：識別所有提到的 AI/ML 模型名稱（完整名稱如 `BAAI/bge-m3` 或簡稱如 `bge-m3`）
2. **計算 mention_count**：每個模型在所有搜尋結果中被提及的次數
3. **計算 source_diversity**：每個模型被幾個不同網站（domain）提到
4. **記錄來源**：列出提到該模型的網站清單

將結果儲存為 `discovered_models.json`，格式如下：

```json
{
  "extracted_by": "claude",
  "source_file": "results_web.json",
  "models": [
    {
      "name": "bge-m3",
      "mention_count": 8,
      "source_diversity": 5,
      "sources": ["huggingface.co", "reddit.com", "arxiv.org", "medium.com", "github.com"]
    },
    {
      "name": "GTE-Qwen2",
      "mention_count": 4,
      "source_diversity": 3,
      "sources": ["huggingface.co", "arxiv.org", "paperswithcode.com"]
    }
  ]
}
```

### Step 4：HuggingFace 精確搜尋（自動化）

```bash
python .claude/skills/model-scout/scripts/hf_search.py \
    --task "{pipeline_tag}" \
    --language "{language}" \
    --from-discovered discovered_models.json \
    --limit 10 \
    --output results_hf.json
```

腳本會：
1. 按任務搜尋 HuggingFace 上的模型
2. 讀取 `discovered_models.json`，用 search API 模糊搜尋每個模型名稱
3. 對每個模型查詳細資料，抓取完整指標：
   - `downloads`、`likes`、`trendingScore`
   - `lastModified`
   - `safetensors.parameters`（精確參數量）
   - `model-index`（模型自報的 benchmark 分數）
   - `tags`（含 license、language）

### Step 5：合併去重（自動化）

```bash
python .claude/skills/model-scout/scripts/merge.py \
    --hf results_hf.json \
    --discovered discovered_models.json \
    --output merged.json
```

腳本會：
1. 將 HF 結果與 Claude 提取的 buzz 指標合併
2. 用模型名稱比對，附加 `mention_count`、`source_diversity`、`sources`
3. 識別只在 web search 出現但 HF 搜不到的模型，標記為 `web-search-only`
4. 輸出 `merged.json`

### Step 6：分層過濾與排名（自動化）

```bash
python .claude/skills/model-scout/scripts/rank.py \
    --input merged.json \
    --language zh \
    --priority accuracy \
    --top 5 \
    --output candidates.json
```

腳本會：
1. 過濾不符合條件的模型：
   - 語言不符（`--language`，使用者指定時才過濾）
   - 模型太大（`--max-size-mb`，使用者指定時才過濾）
   - 超過 10 個月沒更新（預設過濾，可用 `--max-stale-months` 調整）
2. 分為三個梯隊：
   - **Tier 1（強力推薦）**：HF 有資料 + 社群有討論
   - **Tier 2（值得關注）**：社群有討論但 HF 搜不到
   - **Tier 3（僅供參考）**：HF 有資料但社群沒討論
3. 各梯隊內部獨立排名

**Tier 1 排名公式**（五個維度）：
```
score = w_benchmark  * benchmark      ← HF model-index 自報分數
      + w_adoption   * adoption       ← downloads + likes + trendingScore
      + w_recency    * recency        ← lastModified 時間衰減
      + w_efficiency * efficiency     ← benchmark / log2(params)
      + w_buzz       * buzz           ← mention_count + source_diversity
```

**Tier 2**：只用 buzz 排名
**Tier 3**：只用 HF 指標排名（benchmark + adoption + recency + efficiency）

### Step 7：呈現結果（Claude 負責）

分層展示：

```
## Tier 1 — 強力推薦
| 模型 | 參數量 | Benchmark | 下載量 | 社群提及 | 分數 |

## Tier 2 — 值得關注（缺 HF 資料）
| 模型 | 社群提及 | 來源數 | 來源網站 |

## Tier 3 — 僅供參考（社群無討論）
| 模型 | 參數量 | Benchmark | 下載量 | 分數 |
```

Claude 負責：
- 解讀 `results_web.json` 中的摘要，補充社群評價和已知問題
- 說明各梯隊模型的取捨
- 詢問使用者：「要用你的資料集實際測試嗎？」

## Fallback

1. **web_search.py 失敗**：跳過 Step 2-3，直接用 hf_search.py 搜尋，所有模型歸 Tier 3
2. **hf_search.py 失敗**：只用 Claude 從 web search 提取的結果，所有模型歸 Tier 2
3. **全部失敗**：回報錯誤，建議使用者手動提供模型名稱
4. **使用者直接指定模型**：跳過 Step 2-3，用 hf_search.py 查指定模型

## 輸出格式

`candidates.json`：

```json
{
  "query": {
    "hard_constraints": { "language": "zh" },
    "soft_preferences": { "priority": "accuracy" },
    "ranked_at": "ISO-8601"
  },
  "summary": {
    "total_before_filter": 25,
    "total_after_filter": 18,
    "tier1_count": 5,
    "tier2_count": 2,
    "tier3_count": 3
  },
  "tier1": [
    {
      "model_name": "BAAI/bge-m3",
      "tier": 1,
      "downloads": 50000,
      "likes": 120,
      "trending_score": 3.2,
      "parameters": 110000000,
      "benchmark_scores": { "MTEB/ndcg_at_10": 0.68 },
      "license": "mit",
      "mention_count": 8,
      "source_diversity": 5,
      "_scores": { "composite": 0.87 }
    }
  ],
  "tier2": [],
  "tier3": []
}
```