# 第二步：评价清洗与结构化

**脚本**: `clean_reviews.py` | **输入**: `reviews_raw.json` (500 条) | **输出**: `reviews_clean.json` (490 条)

---

## 清洗管线

7 步清洗管线，原始 500 条评价 → 清洗后 490 条高质量结构化评价。**清洗阶段不硬删除数据**（除非 ID 重复），所有评价保留原始 `id` 确保后续 PRD 和测试用例可追溯。

```
reviews_raw.json (500)
    │
    ├─ [1] 内容清洗     ─ 智能引号→ASCII, 控制字符移除, 空白归一化
    ├─ [2] 去重         ─ ID 精确去重(-10) + 内容相似度去重(>85%)
    ├─ [3] 质量评分     ─ 0-1 连续分数(长度0.3 + 实质性0.4 + 投票0.3)
    ├─ [4] 语言检测     ─ langdetect
    ├─ [5] 版本清洗     ─ 归一化 + major_minor 提取
    ├─ [6] 衍生字段     ─ word_count, sentiment, year_month, has_developer_response
    └─ [7] 输出         ─ reviews_clean.json + cleaning_report.json
```

### Step 1: 内容清洗

智能引号转为 ASCII、移除零宽/控制字符、多余空白压缩为单个空格。确保后续 NLP 分词不受干扰。

```python
# 智能引号映射
"\u2018\u2019" → "'",  "\u201c\u201d" → '"',  "\u2013" → "-",  "\u2014" → "--"
# 控制字符
[\x00-\x08\x0b\x0c\x0e-\x1f\x7f] → 移除
# 空白
多个空格/制表符 → 单个空格, trim 首尾
```

### Step 2: 去重

两阶段去重:
1. **ID 精确去重**: 同一个 `id` 出现多次 → 保留 `content` 更长的那条。发现 10 条重复 (500 → 490)。
2. **内容相似度去重**: 同一用户 (`user_name`) 提交了相似度 > 85% 的评价且长度差异 < 5 字 → 视为重复。使用 `difflib.SequenceMatcher`。结果: 无新增重复 (490 → 490)。

### Step 3: 质量评分

每条评价赋予 0-1 的 `quality_score`，用于后续分析时加权排序:

| 维度 | 权重 | 计算方式 |
|------|------|---------|
| 长度 | 0.3 | < 3 字=0, 3-9 字=0.1, 10-29 字=0.2, ≥30 字=0.3 |
| 实质性 | 0.4 | 匹配 50+ 产品相关关键词 (bug/crash/subscription/workout/feature...), 每个匹配 +0.08, 上限 0.4 |
| 投票 | 0.3 | `vote_count / max_vote_count × 0.3` |

结果: avg=0.38, 高质量 (>0.4) 205 条, 低质量 (<0.1) 27 条, low_info 标记 106 条 (< 10 字)。

### Step 4: 语言检测

| 语言 | 数量 |
|------|------|
| en | 469 (95.7%) |
| no | 4 |
| es | 4 |
| 其他 | 12 |
| unknown | 1 |

美区 App Store 评价以英文为绝对主流。

### Step 5: 版本清洗

提取 `major_minor` 字段（如 "8.4.25" → "8.4"），用于按版本聚合问题。2 个 major.minor 分组覆盖 490 条评价。

### Step 6: 衍生字段

新增 4 个分析维度:

| 字段 | 说明 | 示例 |
|------|------|------|
| `word_count` | 评价单词数 | 37 |
| `sentiment` | 基于评分极性 | 1-2★→negative, 3→neutral, 4-5→positive |
| `year_month` | 评价年月 | "2026-07" |
| `has_developer_response` | 开发者是否回复 | false (RSS Feed 不包含) |
| `quality_score` | 0-1 质量分 | 0.38 |
| `low_info` | 是否低信息量 | true (word_count < 10) |

### Step 7: 输出

两条输出:
- `reviews_clean.json` (371 KB) — 清洗后结构化的 490 条评价
- `cleaning_report.json` — 清洗统计报告

---

## 清洗结果总览

| 指标 | 原始 | 清洗后 |
|------|------|--------|
| 评价数 | 500 | **490** |
| 评分均值 | 3.72 | **3.72** |
| 高质量 (>0.4) | — | **205** |
| 低质量 (<0.1) | — | **27** |
| 平均词数 | — | **36.9** |
| App 版本 | 30 | 2 major.minor |

**评分分布:**

| ⭐ | 数量 | 占比 |
|---|------|------|
| 5 | 287 | 58.6% |
| 4 | 35 | 7.1% |
| 3 | 29 | 5.9% |
| 2 | 24 | 4.9% |
| 1 | 115 | 23.5% |

**情感分布:**

| 极性 | 数量 |
|------|------|
| positive (4-5★) | 322 |
| neutral (3★) | 29 |
| **negative (1-2★)** | **139** |

> 139 条负面评价（28.4%）是后续分析与 PRD 的核心信号源。

---

## 数据结构 `reviews_clean.json`

```json
{
  "metadata": {
    "step": 2,
    "stage": "Review Cleaning & Normalization",
    "input_file": "reviews_raw.json",
    "input_count": 500,
    "output_count": 490,
    "pipeline": ["content_cleaning", "deduplication", ...],
    "rating_distribution": {"5": 287, "4": 35, ...},
    "avg_rating": 3.72,
    "quality_score": {"avg": 0.38, "high_quality": 205, "low_quality": 27},
    "language_distribution": {"en": 469, ...},
    "sentiment_distribution": {"positive": 322, "neutral": 29, "negative": 139}
  },
  "reviews": [
    {
      "id": "14264918620",
      "user_name": "Meotdjsscsjdvddng",
      "rating": 1,
      "title": "Idk",
      "content": "It made me pay after the first day and i didn't like it",
      "version": "8.4.25",
      "updated": "2026-07-04T23:49:12-07:00",
      "vote_sum": 0,
      "vote_count": 0,
      "quality_score": 0.1,
      "low_info": true,
      "lang": "en",
      "major_minor": "8.4",
      "word_count": 12,
      "sentiment": "negative",
      "year_month": "2026-07",
      "has_developer_response": false
    }
  ]
}
```

---

## 设计决策

**为什么不按 content 长度删除低质量评价？**
清洗阶段不硬删除低信息量评价，仅标记 `low_info` 和 `quality_score`。分析阶段可据此加权排序（PRD 优先引用 `quality_score > 0.4` 的差评），同时保留简短但有意义的反馈（如 "Too many ads" 可能暴露变现问题）。

**为什么 sentiment 基于评分而非 NLP？**
评分是用户本人对体验的量化表达，比 NLP 模型推断更权威。评分与文本内容的一致性校验留待分析阶段的 cross-check。

**去重的意义**
ID 去重消除 RSS Feed 分页可能导致的边界重复；内容相似度去重防止同一用户使用不同 Apple ID 重复提交。两者共同确保统计数据不被人为放大。

---

## 下一步：评价分类与分析

基于 `reviews_clean.json`，后续将对清洗后的数据执行:
- 按 `quality_score > 0.4` + `sentiment = negative` 提取核心差评
- 对差评内容做关键词聚类，抽象用户问题
- 按 `major_minor` 追踪版本维度的质量趋势
- 输出分析报告作为 PRD 的事实依据
