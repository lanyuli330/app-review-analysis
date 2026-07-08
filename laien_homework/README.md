# LaienTech App Review Analysis

从 App Store 用户评价到产品决策的全流程自动化分析工具。

**核心目标**：将 App Store 评论转化为可追溯的产品研究证据（Product Research Evidence）。

---

## 快速开始

```bash
conda activate laien_homework
cd E:\AI_learning_project\laien_homework
pip install flask scikit-learn langchain langchain-core langchain-community langchain-openai

python app.py
# → 打开 http://localhost:5001
```

## 运行方式

| 按钮 | 数据来源 | 网络要求 |
|------|---------|---------|
| ▶ 开始分析 | RSS Feed 实时爬取 → 失败则提示错误 | 需要 |
| 📦 离线演示 | `reviews_raw_cached.json` (500条预置数据) | 不需要 |

**可选：启用 AI Agent（DeepSeek V4）**

在 API Key 输入框中填入 `sk-xxx`，点击开始。Agent 会调用 DeepSeek 生成更精准的 PRD 和测试用例。无 Key 时自动降级为规则模式。

---

## 6 步分析管线

```
collect → clean → analyze → dashboard → prd → testcases
                                                      ↑
                          DeepSeek Agent (可选, 需 API Key)
```

| 步骤 | 脚本 | 产出 | 说明 |
|------|------|------|------|
| 1. 数据采集 | `collect_reviews.py` | `reviews_raw.json` | Apple RSS Feed → 降级缓存 |
| 2. 评价清洗 | `clean_reviews.py` | `reviews_clean.json` | 去重、质量评分、语言检测、衍生字段 |
| 3. 分类分析 | `analyze_reviews.py` | `analysis_result.json` | TF-IDF + 规则聚类 |
| 3.5 分析看板 | `generate_analysis_report.py` | `analysis_dashboard.html` | 词云、情绪时间线、高风险版本、趋势图 |
| 4. PRD 生成 | `generate_prd.py` | `prd_version_plan.json` | 规则模板 / DeepSeek Agent |
| 5. 测试用例 | `generate_test_cases.py` | `test_cases.json` | 规则模板 / DeepSeek Agent (含溯源) |

## 数据追溯链

```
用户评价 id_1426 (1★ "charged after 1 day")
    → ISSUE-001 付费与订阅问题 (74条差评)
    → REQ-001 修复付费体验 (source_review_ids: [id_1426,...])
    → TC-001 验证7天试用不扣费 (source_quotes: "charged after 1 day")
```

每个环节 `review_id` 透传，PRD 需求和测试用例都可追溯到原始评价。

## Web 页面导航

| Tab | 路由 | 内容 |
|-----|------|------|
| 📊 分析结果 | `/` | 问题发现 + PRD 摘要 + TC 摘要 |
| 📄 原始数据 | `/` | 各步骤 JSON 数据 |
| 📝 可读报告 | `/` | 测试用例 TXT (含源评价引用) |
| 📊 分析看板 | `/dashboard` | Chart.js 交互式图表 (词云/趋势/证据表) |
| 📋 PRD | `/prd` | 完整 PRD HTML |
| ✅ 测试用例 | `/testcases` | 完整 TC HTML (含溯源矩阵) |

## 中间交付物实时展示

管线运行中，每步完成后自动展开卡片，展示该步骤的摘要数据：
- Step 1: 采集评价数、评分分布
- Step 2: 清洗后数量、情感分布
- Step 3: 发现的问题数、Top 关键词
- Step 3.5: 分析看板文件
- Step 4: PRD 版本数、需求数、生成方式 (LLM/Rules)
- Step 5: 测试用例数、生成方式

运行结束后切换到对应 Tab 查看完整交付物。

## 项目结构

```
E:\AI_learning_project\laien_homework\
├── app.py                        # Flask Web 应用 (管线调度 + 路由)
├── templates/index.html          # 前端 UI
├── collect_reviews.py            # Step 1
├── clean_reviews.py              # Step 2
├── analyze_reviews.py            # Step 3
├── generate_analysis_report.py   # Step 3.5
├── generate_prd.py               # Step 4 (LangChain Agent)
├── generate_test_cases.py        # Step 5 (LangChain Agent)
├── reviews_raw_cached.json       # 预置缓存数据
├── docs/                         # 技术文档
└── 产出:
    ├── reviews_raw.json
    ├── reviews_clean.json
    ├── analysis_result.json
    ├── analysis_dashboard.html
    ├── prd_version_plan.json
    └── test_cases.json
```

## 技术栈

| 组件 | 技术 |
|------|------|
| 后端 | Python 3.13, Flask |
| 前端 | 原生 HTML/CSS/JS, Chart.js |
| 分析 | scikit-learn (TF-IDF, 聚类) |
| AI Agent | LangChain + DeepSeek V4 (可选), 规则兜底 |
| 数据采集 | urllib + curl subprocess → 降级缓存 |
| 通用性 | 全部中文 + 通用模板, 换 App 零代码修改 |

## 换 App 使用

1. 在 `collect_reviews.py` 修改 `APP_ID` 和 `APP_NAME`
2. 当前APPLE RSS Feed服务已无法使用
3. 运行 `python app.py` 即可, 所有分析、PRD、测试用例自动适配
