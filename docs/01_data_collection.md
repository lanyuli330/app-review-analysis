# LaienTech iOS App 评价分析 — 技术文档

> 项目路径: `E:\AI_learning_project\laien_homework`
> Python 环境: `E:\Anaconda\envs\laien_homework` (Python 3.11)
> 依赖: 仅系统自带 `curl` + Python 标准库 (`subprocess`, `json`, `hashlib`)

---

## 第一步：数据采集

### 1.1 概述

本阶段完成目标应用的美区 App Store 用户评价采集。评价数据是后续清洗、分类、分析、PRD 生成及测试用例设计的唯一数据源。

### 1.2 目标应用

| 字段 | 值 |
|------|------|
| 应用名称 | Workout for Women: Home Gym |
| 开发者 | Fast Builder Limited |
| App ID | `839285684` |
| App Store 区域 | **美区 (US)** |
| App Store 显示评价数 | ~530K+ |

### 1.3 调研过程：方案选择与淘汰

#### 1.3.1 所有候选方案

| 方案 | 原理 | 上限 | 实测结果 |
|------|------|------|---------|
| 网页爬取 | requests + BS4 解析 | 首屏可见 | ❌ Vite 动态渲染，HTML 为壳 |
| iTunes Search API | Apple 官方 | 不支持评价 | ❌ 仅元数据 |
| `app-store-scraper` | 私有 amp-api | 理论上全部 | ❌ **2025 年已失效** |
| Python `requests` + RSS Feed | 直接 HTTP | 500/维度 | ❌ Python SSL 握手失败 |
| **`curl` + RSS Feed (本方案)** | curl 子进程 | 500/排序 | ✅ **采用** |
| amp-api 私有接口 | `amp-api-edge` | 理论上全部 | ❌ 需 `MEDIA_API_TOKEN` (服务端) |
| 付费代理 | ScraperAPI 等 | 不限 | ⚠️ $49/月起 |

#### 1.3.2 `app-store-scraper` 失效根因

Apple 2025 年将 App Store 前端从服务端渲染重构为 **Vite 客户端渲染**:

| | 旧 (2024) | 新 (2025+) |
|---|---|---|
| Token 位置 | HTML `<meta>` 标签 | JS bundle `MEDIA_API_TOKEN` (服务端编译注入) |
| 可提取性 | 任何人可提取 | 客户端不可见 |
| API 端点 | `amp-api.apps.apple.com` | `amp-api-edge.apps.apple.com` |
| 匿名访问 | 不支持 | `userTokenHash` 为空 `""` |

#### 1.3.3 Python `requests` SSL 问题

`requests` 库在访问 `itunes.apple.com` 时出现:
```
SSLEOFError: [SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol
```

经测试，系统 `curl` 命令可正常访问同一 URL（返回 HTTP 200 + 完整 JSON）。根因是 Python OpenSSL 与 Apple CDN 节点的 SSL 实现存在兼容性问题。

**解决方案**: 使用 `subprocess.run(["curl", ...])` 做 HTTP 客户端，Python 仅负责 JSON 解析和数据处理。

#### 1.3.4 最终方案：curl + 双排序 RSS Feed

```
采集策略:
  🇺🇸 US 美区 only
  📊 mostrecent (最新)   — 时间倒序，最新反馈
  📊 mosthelpful (最有用) — 社区投票排序，高质量评价

去重: MD5(review_id + user_name)
HTTP: curl via subprocess
```

### 1.4 实现细节

#### 核心代码

```python
import subprocess, json

url = f"https://itunes.apple.com/us/rss/customerreviews/page={page}/id={app_id}/sortby={sort}/json"
result = subprocess.run(
    ["curl", "-s", "-L", "--connect-timeout", "15", url],
    capture_output=True, text=True, timeout=20
)
data = json.loads(result.stdout)

# 过滤: 仅保留含 im:rating 的评价条目
for entry in data["feed"]["entry"]:
    if "im:rating" in entry:
        review = {
            "id":           entry["id"]["label"],
            "user_name":    entry["author"]["name"]["label"],
            "rating":       int(entry["im:rating"]["label"]),
            "title":        entry["title"]["label"],
            "content":      entry["content"]["label"],
            "version":      entry["im:version"]["label"],
            "updated":      entry["updated"]["label"],
            "vote_sum":     int(entry.get("im:voteSum", {}).get("label", 0)),
            "vote_count":   int(entry.get("im:voteCount", {}).get("label", 0)),
        }
```

#### 请求策略

| 参数 | 值 |
|------|------|
| 单页条数 | 50 (RSS 固定) |
| 每排序最大页数 | 10 |
| 每排序理论最大 | 500 条 |
| 排序方式 | `mostrecent` + `mosthelpful` |
| 理论最大 | 1000 条 (去重后 ~600-900) |
| 页间间隔 | 1 秒 |
| curl 超时 | 15 秒 |

### 1.5 输出数据

#### `reviews_raw.json` 结构

```json
{
  "metadata": {
    "app_id": 839285684,
    "app_name": "Workout for Women: Home Gym",
    "total_reviews": 800,
    "method": "Apple RSS Feed (curl-based, US dual-sort)",
    "source": "Apple App Store (US RSS Feed)"
  },
  "reviews": [
    {
      "id": "14264918620",
      "user_name": "Meotdjsscsjdvddng",
      "user_uri": "https://itunes.apple.com/us/reviews/id...",
      "rating": 1,
      "title": "Idk",
      "content": "It made me pay after the first day...",
      "version": "8.4.25",
      "updated": "2026-07-04T23:49:12-07:00",
      "vote_sum": 0,
      "vote_count": 0,
      "_source_sort": "mostrecent"
    }
  ]
}
```

#### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 评价唯一 ID |
| `user_name` | string | 用户昵称 |
| `user_uri` | string | 用户主页链接 |
| `rating` | int (1-5) | 星级评分 |
| `title` | string | 标题 |
| `content` | string | 正文 |
| `version` | string | 评价时的 App 版本 |
| `updated` | string | 评价时间 (ISO 8601) |
| `vote_sum` | int | 有用投票净数 |
| `vote_count` | int | 有用投票总数 |
| `_source_sort` | string | 来源排序 (内部字段) |

### 1.6 数据局限

| 局限 | 说明 | 影响 |
|------|------|------|
| **500 条/维度** | RSS Feed 硬上限 | 通过双排序扩展到 ~600-900 |
| **非全部 530K** | 私有 API 需要服务端 token | 如实注明；样本仍可反映核心问题 |
| **双排序有重叠** | 同一评价可同时出现在两种排序中 | MD5 去重处理 |
| **仅最新 10 页** | 无法获取更早的历史评价 | 覆盖近期用户反馈，时效性可接受 |

### 1.7 运行

```bash
conda activate laien_homework
cd E:\AI_learning_project\laien_homework
python collect_reviews_v2.py
```

### 1.8 项目文件

```
E:\AI_learning_project\laien_homework\
├── collect_reviews.py         # v1: Python requests (保留)
├── collect_reviews_v2.py      # v2: curl subprocess (当前)
├── reviews_raw.json            # 评价数据库
├── collection_stats.json       # 采集统计
├── requirements.txt            # 依赖说明
└── docs/
    └── 01_data_collection.md   # 本文档
```

### 1.9 下一步

→ **第二步: 评价清洗与结构化** (去无效、语言识别、关键词提取、情感分析)

---

*最后更新: 2026-07-07*
