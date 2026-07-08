# 第三步：评价分析与问题发现

**脚本**: `analyze_reviews.py` | **输入**: `reviews_clean.json` (490 条) | **输出**: `analysis_result.json`

---

## 分析架构

三层架构，规则提供可复现基线，LLM 提供语义深度，Grounding 防止幻觉。

```
reviews_clean.json (490 条)
    │
    ├── Layer 1: 规则预处理 (sklearn, 纯本地, 零成本)
    │   ├── TF-IDF + 1-3 gram 关键词提取
    │   ├── 按 sentiment=negative + quality≥0.3 筛选 98 条核心差评
    │   ├── 月度评分趋势 + 版本维度统计
    │   └── 关键词聚类 → 规则版问题列表 (baseline)
    │
    ├── Layer 2: LLM 语义聚类 (可选, 1 次 API call)
    │   ├── 喂入 80 条差评全文 (~6K tokens)
    │   ├── LLM 自由语义聚类 → 5-8 个主题
    │   ├── Prompt 约束: 每个问题必须带 review_ids
    │   └── 支持: --llm openai (需 API key) 或 --llm ollama (本地)
    │
    └── Layer 3: Grounding 验证
        ├── review_id → content 索引回查
        ├── 核验 LLM claim 在原文中是否有支撑
        └── 标注 high / medium / low confidence
```

---

## 分析方法

### TF-IDF 关键词提取

- 1-3 gram, min_df=2, max_df=0.8
- 自定义停用词 (app/workout/women 等通用词)
- 差评关键词 top-10: `free`, `subscription`, `pay`, `trial`, `charged`, `money`, `ads`, `workouts`, `cancel`, `refund`
- 好评关键词 top-10: `love`, `great`, `easy`, `best`, `amazing`, `helpful`, `recommend`, `results`, `perfect`, `favorite`

### 规则聚类

基于 6 类关键词模式做 co-occurrence 匹配，将 98 条差评分为 3 大类:

| # | 类别 | 数量 | 严重度 | 来源版本 |
|---|------|------|--------|---------|
| 1 | Subscription / Paywall 付费墙 | 76 | **critical** | 8.4 |
| 2 | UX / UI 界面体验 | 14 | high | 8.4 |
| 3 | Content Quality 内容质量 | 6 | medium | 8.4 |
| _ | Other 其他 | 2 | low | — |

> 76/98 (77.6%) 的差评直接与付费/订阅有关。这是最突出的产品问题。

### LLM 增强 (可选)

```bash
# OpenAI
python analyze_reviews.py --llm openai --api-key sk-xxx

# 本地 Ollama
python analyze_reviews.py --llm ollama --ollama-model llama3.1
```

规则模式无需任何外部依赖即可运行，适合面试官离线评审。

---

## 发现与洞察

### 核心问题: 付费墙过于激进

**证据:** 76 条差评 (占总差评的 77.6%, 总评价的 15.5%)

**代表性评价:**

> "I downloaded this app yesterday and I wanted to try the 1-week free trial, but once I used the Apple Pay feature to subscribe, I was immediately charged the full amount." — Tinazwrld143, 1★

> "It let me start my training on the free app but the second day it was making me have to pay to continue" — Jude/Judith, 1★

> "Cancelled subscription and still got charged for it. No spot in app to manage no place on website either." — Bobillena, 1★

**根因分析:**
- 免费试用承诺与实际收费不一致 (1 天后就收费而非 7 天)
- 免费内容几乎不可用 (app 被描述为仅支持付费)
- 订阅管理缺失 (无法在 app 内取消/管理)

### 次要问题: UI/体验

14 条差评涉及广告弹窗无法关闭、找不到设置/取消按钮等。

### 版本趋势

| 版本 | 评价数 | 差评率 | 均分 |
|------|--------|--------|------|
| 8.3 | 77 | 27% | 3.84 |
| 8.4 | 413 | **29%** | 3.70 |

v8.4 差评率略有上升 (27% → 29%)，均分下降 (3.84 → 3.70)，趋势不乐观。

---

## 下一步

基于这些分析发现，进入 **Step 4: PRD 与版本规划**，将 3 个问题转化为具体的产品需求。

---

*最后更新: 2026-07-07*
