# LaienTech App Review Analysis — 技术设计文档

> 项目路径: `E:\AI_learning_project\laien_homework`
> Python 环境: `laien_homework` (conda)
> 依赖: Flask, scikit-learn, langchain, langchain-openai (LLM 可选)

---

## 1. 数据采集 (Step 1)

### 1.1 数据源

Apple App Store 官方 RSS Feed API，无需 API Key。

```
https://itunes.apple.com/{country}/rss/customerreviews/page={n}/id={app_id}/sortby=mostrecent/json
```

### 1.2 采集方案演变

| 方案 | 结果 | 原因 |
|------|------|------|
| Python `requests` + RSS | ❌ 失败 | SSL 握手不兼容 (SSLEOFError) |
| `app-store-scraper` 库 | ❌ 失效 | Apple 2025 年迁移到 Vite 客户端渲染 |
| 网页爬取 | ❌ 不可行 | 动态渲染, 无法静态解析 |
| **`curl` subprocess + RSS** | ✅ 采用 | 原生 SSL 支持, 返回完整 JSON |

### 1.3 当前状态

2026年7月，Apple 已关闭 RSS Feed 的评论数据输出——API 返回 HTTP 200 但 `entry` 数组为空。项目使用预置缓存数据 `reviews_raw_cached.json` (500条) 作为降级方案。

### 1.4 输出

`reviews_raw.json` — 500条原始评价, 每条含: id, user_name, rating(1-5), title, content, version, updated

---

## 2. 评价清洗 (Step 2)

### 2.1 清洗管线

```
reviews_raw.json (500条)
  → 内容清洗 (智能引号→ASCII, 控制字符移除, 空白归一化)
  → ID 去重 (保留 content 更长的那条)
  → 质量评分 (0-1: 长度0.3 + 实质性0.4 + 投票0.3)
  → 语言检测 (langdetect)
  → 版本归一化 (提取 major.minor)
  → 衍生字段 (word_count, sentiment, year_month)
```

### 2.2 设计原则

清洗阶段不硬删除低质量评价，仅标记 `low_info` 和 `quality_score`。分析阶段据此加权排序。

### 2.3 输出

`reviews_clean.json` — ~487 条, 每条 15 个字段（含 quality_score, sentiment, word_count, major_minor 等）

---

## 3. 分类与分析 (Step 3)

### 3.1 分析架构

```
reviews_clean.json
  → Layer 1: 规则预处理 (TF-IDF 关键词提取 + 规则聚类)
  → 产出: 8 个通用问题分类 (中文): 付费与订阅、UX与广告、内容质量、Bug、性能、功能建议、新手引导、其他
  → 每个 Issue 关联具体 review_ids + representative_quotes
```

### 3.2 关键词提取

- TF-IDF, ngram_range=(1,3), min_df=2, max_df=0.8
- 自定义停用词过滤 (app/workout/women 等 App 特定词)
- 差评 Top 关键词 + 好评 Top 关键词 (对照组)

### 3.3 输出

`analysis_result.json` — issues 列表 + statistics (评分分布/月度趋势/版本对比) + keywords

---

## 4. 分析看板 (Step 3.5)

### 4.1 7 个分析维度

| 维度 | 工具函数 | 展示 |
|------|---------|------|
| 关键词词云 | `wordcloud()` | 2-3gram 短语词云 (TF-IDF 权重) |
| 情绪时间线 | `sentiment_timeline()` | Chart.js 堆积柱状图 |
| 高风险版本 | `high_risk_versions()` | 差评率排序卡片 |
| 差评高峰日 | `peak_negative_day()` | 日期 + 当日差评原文 |
| 版本口碑 | `version_trend()` | Chart.js 双Y轴折线图 |
| 差评证据 | `evidence_table()` | 可滚动表格 |
| 版本趋势 | 按差评率自动标记 🔴/🟡/🟢 |

### 4.2 输出

`analysis_dashboard.html` — 自包含 HTML, 使用 Chart.js CDN, 可独立打开

---

## 5. PRD 生成 (Step 4)

### 5.1 双模式

| 模式 | 触发 | 实现 |
|------|------|------|
| 规则模式 | 无 API Key | `rule_based_prd()` — 通用模板, 中文输出 |
| Agent 模式 | 有 DeepSeek Key | `run_langchain_agent()` — LangChain Tool-Calling Agent |

### 5.2 Agent 架构

- **Tool**: `read_analysis()` → 读取 analysis_result.json
- **Tool**: `save_prd()` → 保存 prd_version_plan.json
- **Prompt**: 根因分析 + 版本拆分规则 + 商业约束 + 中文输出要求

### 5.3 版本拆分规则

- vNext (P0): 所有 critical 问题 → >30条差评的问题强制拆为 2-3 个子需求
- vNext+1 (P1): 所有 high + 最重要的 medium 问题
- 拆分原则: 不取消付费墙, 优化信任与透明度

### 5.4 输出

`prd_version_plan.json` — {version_plan: [{vNext, vNext+1}, requirements, executive_summary]}

---

## 6. 测试用例 (Step 5)

### 6.1 双模式

| 模式 | 触发 | 实现 |
|------|------|------|
| 规则模式 | 无 API Key | `rule_based_test_cases()` — 每条 REQ 生成 1-2 个 TC |
| Agent 模式 | 有 DeepSeek Key | `run_langchain_agent()` — LangChain Agent with 3 tools |

### 6.2 Agent 架构

- **Tool**: `read_prd()` → 读取 PRD 获取 source_review_ids
- **Tool**: `lookup_reviews(ids)` → 批量查询原始评价内容
- **Tool**: `save_test_cases()` → 保存
- **溯源**: 每个 TC 包含 source_review_ids + source_quotes

### 6.3 输出

`test_cases.json` — test_cases 列表 + coverage_summary (包含溯源矩阵)

---

## 7. Web 应用 (app.py)

### 7.1 架构

```
Flask Web App (app.py)
  │
  ├── 管线调度: 按顺序 import + 调用各脚本的核心函数
  │   collect → clean → analyze → dashboard → prd → testcases
  │
  ├── 实时状态: 全局 state 字典, 前端每秒轮询 /api/status
  │
  ├── 页面路由:
  │   /                  → 主页面 (index.html)
  │   /dashboard         → 分析看板
  │   /prd               → PRD 展示页
  │   /testcases         → 测试用例展示页
  │   /api/status        → 管线状态 JSON
  │   /api/report/{name}  → TXT 报告
  │   /api/result/{step} → JSON 结果
  │
  └── Agent 开关: 用户通过 UI 输入 DeepSeek Key 启用 LLM Agent
```

---

## 8. 通用性设计

所有模块从 JSON 文件读取数据，不包含任何 App 特定硬编码：

- 问题分类: 8 个通用类别 (付费/UX/内容/Bug/性能/建议/引导/其他)
- PRD 模板: 通用版本命名 + 需求模板
- 测试用例: 通用 TC 模板
- 分析看板: 全部从数据自动生成
- 语言: 全部中文输出

换其他 App 只需修改 `collect_reviews.py` 中的 APP_ID 并准备缓存数据，重跑管线即可。

---

## 9. 环境 & 依赖

```bash
conda create -n laien_homework python=3.11
conda activate laien_homework
pip install flask scikit-learn langchain langchain-core langchain-community langchain-openai
```

LLM Agent 需要 DeepSeek API Key (可选, 无 Key 时自动降级为规则模式)。

---

## 10. 防幻觉机制 (Hallucination Prevention)

### 10.1 核心策略: 三层防线

```
Layer 1 ─ 规则基线                   → 零幻觉
Layer 2 ─ LLM 约束 + 溯源验证         → 幻觉可控
Layer 3 ─ 降级机制                   → 永远可用
```

### 10.2 Layer 1: 规则基线 (Step 1-3, 零 LLM)

Step 1-3 完全不使用 LLM，所有分析基于纯规则算法：

| 步骤 | 方法 | 为什么没有幻觉 |
|------|------|---------------|
| 数据采集 | curl subprocess 抓取 RSS Feed | 原始数据直读，不做生成 |
| 评价清洗 | 正则 + 去重 + 公式计算 | 确定性算法，同输入必同输出 |
| 分类分析 | TF-IDF 关键词 + 关键词共现聚类 | 基于词频统计，不产生新内容 |
| 分析看板 | 数据聚合 + Chart.js 渲染 | 图表数据来自原始 JSON |

这些步骤的输出是可复现的：任何人用同样的输入数据运行，得到完全一致的结果。

### 10.3 Layer 2: LLM 约束 + 溯源验证 (Step 4-5)

当启用 DeepSeek Agent 时，以下机制确保 LLM 输出不会偏离事实：

#### Prompt 层约束

```
1. 每个 REQ 的 source_review_ids 必须是分析数据中的真实 ID — 严禁编造
2. 每个 REQ 的 source_quotes 必须从分析数据中原文摘录 — 严禁改写
3. 版本拆分规则硬编码在 Prompt 中 (critical → P0, high → P1)
4. 商业约束硬编码 (不强拆付费墙，优化信任与透明度)
```

#### 数据溯源

```
用户评价 (review_id + content)
    → Step 3 分析: Issue 关联 review_ids[] + representative_quotes[]
    → Step 4 PRD:   REQ 继承 source_review_ids[] + source_quotes[]
    → Step 5 测试用例: TC 继承 source_review_ids[] + source_quotes[]
```

**关键点**: LLM 只在 Step 4 和 Step 5 被调用，且被要求只能从已有数据中引用 review_ids 和 quotes，不允许创造新的事实。

#### 验证机制

| 机制 | 说明 |
|------|------|
| review_id 回查 | TC 生成时 `lookup_reviews(ids)` 工具函数直接从 `reviews_clean.json` 查询，不依赖 LLM 记忆 |
| quotes 原文引用 | 要求 LLM 输出 `source_quotes` 字段直接拷贝分析数据中的 `representative_quotes` |
| JSON schema 约束 | 输出格式严格限定，违反格式会导致解析失败 → 自动降级规则模式 |

### 10.4 Layer 3: 降级机制

```
LLM 调用失败 (API 不可用 / Key 无效 / JSON 解析失败)
    → 自动降级为 rule_based_prd() / rule_based_test_cases()
    → 规则模板保证永远有可用输出
    → 页面标注 "📋 由规则生成" vs "🧠 由 LLM 生成"
```

这使得分析结果**始终可访问**，不会因为 LLM 异常而中断整个流程。

### 10.5 评审视角的可信度

从评审角度看，每条 PRD 需求和测试用例都可以：

1. **点击展开查看源评价原文** — 证据就在页面上
2. **查阅 `analysis_result.json`** — 确认 review_ids 真实存在
3. **对照 `reviews_clean.json`** — 验证原文内容未被修改
4. **页面底部标注生成方式** — 明确区分 LLM 产出 vs 规则产出

### 10.6 不做的事情 (避免过度依赖 LLM)

| 不做 | 原因 |
|------|------|
| 不让 LLM 做评分/情感分析 | 评分是用户提供的客观数据，无需 LLM 推断 |
| 不让 LLM 做关键词提取 | TF-IDF 是确定性算法，结果可复现 |
| 不让 LLM 直接生成最终报告 | 报告由规则模板生成，LLM 仅辅助聚类和总结 |
| 不让 LLM 编造新的用户需求 | 所有需求必须来自实际评价数据 |

---

*最后更新: 2026-07-08*
