"""
Step 3.5: Analysis Dashboard Agent
=====================================
LangChain Agent with specialized tools for multi-dimensional analysis visualization.
Generates a self-contained HTML dashboard with interactive charts.

Tools:
  get_data()        → Load cleaned reviews + analysis results
  wordcloud()       → Generate keyword word cloud
  sentiment_timeline() → Positive/neutral/negative sentiment over time
  high_risk_versions() → Identify versions with most negative reviews + core issues
  peak_negative_day()  → Find the day with most negative reviews
  version_trend()      → Version reputation trend line chart
  evidence_table()     → Generate evidence table from negative reviews
  save_dashboard()     → Save the complete HTML report

Usage:
  python generate_analysis_report.py                        # rules mode
  python generate_analysis_report.py --llm deepseek --api-key sk-xxx  # LLM enhanced
"""

import json
import os
import sys
from datetime import datetime
from collections import Counter, defaultdict

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
REVIEWS_FILE = os.path.join(PROJECT_DIR, "reviews_clean.json")
ANALYSIS_FILE = os.path.join(PROJECT_DIR, "analysis_result.json")
OUTPUT_FILE = os.path.join(PROJECT_DIR, "analysis_dashboard.html")


# ============================================================
# Tool Functions
# ============================================================

def tool_get_data() -> dict:
    """[Tool] Load cleaned reviews and analysis results"""
    with open(REVIEWS_FILE, "r", encoding="utf-8") as f:
        reviews = json.load(f)["reviews"]
    analysis = None
    if os.path.exists(ANALYSIS_FILE):
        with open(ANALYSIS_FILE, "r", encoding="utf-8") as f:
            analysis = json.load(f)
    return {"reviews": reviews, "analysis": analysis}


def tool_wordcloud(neg_reviews: list, width: int = 700, height: int = 400) -> str:
    """[Tool] Generate meaningful phrase word cloud from negative reviews. 
    Prioritizes bigrams & trigrams over single words for readability in English."""
    from sklearn.feature_extraction.text import TfidfVectorizer, ENGLISH_STOP_WORDS
    import numpy as np

    texts = [r["content"] for r in neg_reviews if r["quality_score"] >= 0.2]
    if not texts:
        texts = [r["content"] for r in neg_reviews]

    # Aggressive stop words for English review context
    stops = set(ENGLISH_STOP_WORDS) | {
        "app", "workout", "women", "gym", "home", "im", "ive", "don", "didn", "doesn",
        "can", "get", "just", "like", "really", "use", "used", "time", "one", "day",
        "now", "still", "also", "even", "much", "way", "well", "make", "made", "thing",
        "need", "want", "would", "could", "going", "see", "know", "think", "try",
        "had", "has", "have", "been", "did", "does", "lot", "back", "say", "said",
    }

    # Combine 2-gram and 3-gram vectors with higher weight for phrases
    vec2 = TfidfVectorizer(stop_words=list(stops), ngram_range=(2, 2), max_features=40, min_df=2)
    vec3 = TfidfVectorizer(stop_words=list(stops), ngram_range=(3, 3), max_features=20, min_df=2)

    tfidf2 = vec2.fit_transform(texts)
    tfidf3 = vec3.fit_transform(texts)

    names2 = vec2.get_feature_names_out()
    names3 = vec3.get_feature_names_out()
    scores2 = np.asarray(tfidf2.sum(axis=0)).flatten()
    scores3 = np.asarray(tfidf3.sum(axis=0)).flatten()

    # 3-grams get a boost (they're more meaningful)
    words = [(n, s * 1.5, "trigram") for n, s in zip(names3, scores3)] + \
            [(n, s, "bigram") for n, s in zip(names2, scores2)]

    # Normalize
    max_score = max(s for _, s, _ in words) if words else 1
    if max_score > 0:
        words = [(n, s / max_score, t) for n, s, t in words]

    # Sort by score, take top 35
    words = sorted(words, key=lambda x: -x[1])[:10]

    # Dynamic colors based on sentiment association
    neg_colors = ["#e0556a", "#e06c75", "#d47983", "#e8b44b", "#d19a66", "#c678dd"]
    neu_colors = ["#6c8cff", "#56b6c2", "#4caf93", "#98c379"]

    max_size, min_size = 52, 12
    items = ""
    for i, (word, score, wtype) in enumerate(words):
        # Trigram gets slightly bigger
        boost = 1.2 if wtype == "trigram" else 1.0
        size = int((min_size + score * (max_size - min_size)) * boost)
        opacity = 0.55 + score * 0.45
        # Color based on position (top=N darker)
        pal = neg_colors if score > 0.6 else neu_colors
        color = pal[i % len(pal)]
        items += f'<span style="font-size:{size}px;color:{color};opacity:{opacity};margin:3px 10px;display:inline-block;cursor:default" title="{word} (score: {score:.2f})">{word}</span>'

    return f'<div style="text-align:center;padding:20px;max-width:{width}px;margin:0 auto;line-height:2.2">{items}</div>'


def tool_sentiment_timeline(reviews: list) -> str:
    """[Tool] Generate sentiment timeline chart (positive/neutral/negative by month). Returns Chart.js HTML snippet."""
    monthly = defaultdict(lambda: {"pos": 0, "neu": 0, "neg": 0, "total": 0, "ratings": []})
    for r in reviews:
        ym = r.get("year_month", r.get("updated", "")[:7])
        if not ym or ym == "unknown":
            continue
        s = r.get("sentiment", "neutral")
        # Normalize to English keys
        if s in ("positive", "pos"): monthly[ym]["pos"] += 1
        elif s in ("negative", "neg"): monthly[ym]["neg"] += 1
        else: monthly[ym]["neu"] += 1
        monthly[ym]["total"] += 1
        monthly[ym]["ratings"].append(r["rating"])

    months = sorted(monthly.keys())[-12:]  # last 12 months
    pos_data = [monthly[m]["pos"] for m in months]
    neu_data = [monthly[m]["neu"] for m in months]
    neg_data = [monthly[m]["neg"] for m in months]
    avg_data = [round(sum(monthly[m]["ratings"]) / max(len(monthly[m]["ratings"]), 1), 2) for m in months]

    chart_id = "sentimentTimeline"

    return f"""
    <div style="margin:20px 0">
        <canvas id="{chart_id}" style="max-height:350px"></canvas>
    </div>
    <script>
    (function() {{
        var ctx = document.getElementById('{chart_id}');
        if (!ctx) return;
        new Chart(ctx, {{
            type: 'bar',
            data: {{
                labels: {json.dumps(months)},
                datasets: [
                    {{ label: 'Positive', data: {json.dumps(pos_data)}, backgroundColor: '#4caf93', borderRadius: 4 }},
                    {{ label: 'Neutral',  data: {json.dumps(neu_data)}, backgroundColor: '#e8b44b', borderRadius: 4 }},
                    {{ label: 'Negative', data: {json.dumps(neg_data)}, backgroundColor: '#e0556a', borderRadius: 4 }},
                ]
            }},
            options: {{
                responsive: true,
                scales: {{
                    x: {{ stacked: true, ticks: {{ color: '#8b8fa3' }}, grid: {{ display: false }} }},
                    y: {{ stacked: true, title: {{ display: true, text: 'Reviews', color: '#8b8fa3' }}, ticks: {{ color: '#8b8fa3' }}, grid: {{ color: '#2a2d3a' }} }}
                }},
                plugins: {{ legend: {{ labels: {{ color: '#e1e4ed' }} }} }}
            }}
        }});
    }})();
    </script>
    """


def tool_high_risk_versions(reviews: list) -> str:
    """[Tool] Identify high-risk versions (most negative reviews). Returns HTML card."""
    ver_stats = defaultdict(lambda: {"total": 0, "neg": 0, "ratings": [], "neg_texts": []})
    for r in reviews:
        v = r.get("major_minor", r.get("version", "?"))
        ver_stats[v]["total"] += 1
        ver_stats[v]["ratings"].append(r["rating"])
        if r.get("sentiment") == "negative":
            ver_stats[v]["neg"] += 1
            ver_stats[v]["neg_texts"].append(r["content"])

    # Sort by negative ratio
    ranked = sorted(ver_stats.items(), key=lambda x: x[1]["neg"] / max(x[1]["total"], 1), reverse=True)

    html = '<div style="display:grid;gap:16px">'
    for v, s in ranked[:3]:
        neg_ratio = s["neg"] / max(s["total"], 1)
        risk = "🔴 High" if neg_ratio > 0.25 else ("🟡 Medium" if neg_ratio > 0.15 else "🟢 Low")
        avg_r = round(sum(s["ratings"]) / max(len(s["ratings"]), 1), 2)

        # Core issue from negative reviews
        from sklearn.feature_extraction.text import TfidfVectorizer, ENGLISH_STOP_WORDS
        stops = set(ENGLISH_STOP_WORDS) | {"app", "workout", "women", "gym", "home", "im", "ve", "don", "didn", "can", "get", "just", "like", "really"}
        vec = TfidfVectorizer(stop_words=list(stops), ngram_range=(1, 2), max_features=5)
        try:
            vec.fit(s["neg_texts"][:20])
            top_words = ", ".join(vec.get_feature_names_out()[:5])
        except:
            top_words = "insufficient data"

        html += f"""
        <div style="background:var(--card-bg,#1a1d27);border:1px solid var(--border,#2a2d3a);border-radius:10px;padding:20px">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
                <h3 style="margin:0;color:var(--accent,#6c8cff)">Version {v}</h3>
                <span style="font-size:13px;padding:4px 12px;border-radius:20px;background:{'rgba(224,85,106,.2)' if risk.startswith('🔴') else 'rgba(76,175,147,.2)'};color:{'#e0556a' if risk.startswith('🔴') else '#4caf93'}">{risk}</span>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:12px">
                <div><small style="color:var(--muted,#8b8fa3)">总评价</small><br><strong>{s['total']}</strong></div>
                <div><small style="color:var(--muted,#8b8fa3)">差评</small><br><strong style="color:#e0556a">{s['neg']} ({neg_ratio:.0%})</strong></div>
                <div><small style="color:var(--muted,#8b8fa3)">均分</small><br><strong>{avg_r}</strong></div>
            </div>
            <div><small style="color:var(--muted,#8b8fa3)">核心问题关键词</small><br><span style="font-size:14px">{top_words}</span></div>
        </div>
        """
    html += '</div>'
    return html


def tool_peak_negative_day(reviews: list) -> str:
    """[Tool] Find the day with the most negative reviews. Returns HTML card."""
    daily = defaultdict(lambda: {"total": 0, "neg": 0, "neg_items": []})
    for r in reviews:
        day = r.get("updated", "")[:10]
        if not day:
            continue
        daily[day]["total"] += 1
        if r.get("sentiment") == "negative":
            daily[day]["neg"] += 1
            daily[day]["neg_items"].append(r)

    if not daily:
        return "<p>No data available</p>"

    # Find peak by negative count
    peak_day = max(daily.items(), key=lambda x: x[1]["neg"])
    day_str, day_data = peak_day

    html = f"""
    <div style="background:var(--card-bg,#1a1d27);border:1px solid var(--border,#2a2d3a);border-radius:10px;padding:20px">
        <h3 style="color:#e0556a;margin-bottom:8px">📉 差评高峰日</h3>
        <div style="font-size:24px;font-weight:bold;margin-bottom:4px">{day_str}</div>
        <div style="color:var(--muted,#8b8fa3);margin-bottom:12px">
            {day_data['neg']} 条差评 / {day_data['total']} 条总评价 ({day_data['neg']/max(day_data['total'],1)*100:.0f}%)
        </div>
        <div style="max-height:200px;overflow-y:auto">
            <small style="color:var(--muted,#8b8fa3)">当天差评示例:</small>
    """
    for r in day_data["neg_items"][:5]:
        html += f"""
            <div style="margin:8px 0;padding:8px;background:var(--bg,#0f1117);border-radius:6px;font-size:12px">
                [{r['rating']}★] <strong>{r['user_name']}</strong>: "{r['content'][:150]}"
            </div>
        """
    html += "</div></div>"
    return html


def tool_version_trend(reviews: list) -> str:
    """[Tool] Version reputation trend line chart. Returns Chart.js HTML snippet."""
    ver_stats = defaultdict(lambda: {"total": 0, "neg": 0, "ratings": []})
    for r in reviews:
        v = r.get("major_minor", "")
        if not v or v == "unknown":
            continue
        ver_stats[v]["total"] += 1
        ver_stats[v]["ratings"].append(r["rating"])
        if r.get("sentiment") == "negative":
            ver_stats[v]["neg"] += 1

    versions = sorted(ver_stats.keys())
    if len(versions) < 2:
        return "<p>Insufficient version data for trend analysis</p>"

    avg_data = [round(sum(ver_stats[v]["ratings"]) / max(len(ver_stats[v]["ratings"]), 1), 2) for v in versions]
    neg_data = [round(ver_stats[v]["neg"] / max(ver_stats[v]["total"], 1) * 100, 1) for v in versions]
    total_data = [ver_stats[v]["total"] for v in versions]

    chart_id = "versionTrend"

    return f"""
    <div style="margin:20px 0">
        <canvas id="{chart_id}" style="max-height:300px"></canvas>
    </div>
    <script>
    (function() {{
        var ctx = document.getElementById('{chart_id}');
        if (!ctx) return;
        new Chart(ctx, {{
            type: 'line',
            data: {{
                labels: {json.dumps(versions)},
                datasets: [
                    {{ label: 'Avg Rating', data: {json.dumps(avg_data)}, borderColor: '#6c8cff', backgroundColor: 'rgba(108,140,255,.1)', tension: 0.3, yAxisID: 'y' }},
                    {{ label: 'Neg%', data: {json.dumps(neg_data)}, borderColor: '#e0556a', backgroundColor: 'rgba(224,85,106,.1)', tension: 0.3, yAxisID: 'y1', borderDash: [5,5] }},
                ]
            }},
            options: {{
                responsive: true,
                scales: {{
                    x: {{ ticks: {{ color: '#8b8fa3' }}, grid: {{ display: false }} }},
                    y: {{ type: 'linear', position: 'left', title: {{ display: true, text: 'Avg Rating', color: '#8b8fa3' }}, min: 2.5, max: 5, ticks: {{ color: '#8b8fa3' }}, grid: {{ color: '#2a2d3a' }} }},
                    y1: {{ type: 'linear', position: 'right', title: {{ display: true, text: 'Negative %', color: '#8b8fa3' }}, min: 0, ticks: {{ color: '#8b8fa3', callback: function(v) {{ return v+'%' }} }}, grid: {{ display: false }} }}
                }},
                plugins: {{ legend: {{ labels: {{ color: '#e1e4ed' }} }} }}
            }}
        }});
    }})();
    </script>
    """


def tool_evidence_table(reviews: list, top_n: int = 20) -> str:
    """[Tool] Generate evidence table from high-quality negative reviews. Returns HTML table."""
    neg = [r for r in reviews if r.get("sentiment") == "negative" and r.get("quality_score", 0) >= 0.3]
    neg.sort(key=lambda x: x.get("quality_score", 0), reverse=True)

    rows = ""
    for i, r in enumerate(neg[:top_n]):
        sev = "🔴" if r["rating"] == 1 else ("🟠" if r["rating"] == 2 else "🟡")
        rows += f"""
        <tr>
            <td style="padding:8px;border-bottom:1px solid var(--border,#2a2d3a);font-size:12px">{sev} {r['rating']}★</td>
            <td style="padding:8px;border-bottom:1px solid var(--border,#2a2d3a);font-size:12px">{r['user_name'][:15]}</td>
            <td style="padding:8px;border-bottom:1px solid var(--border,#2a2d3a);font-size:12px">{r.get('updated','')[:10]}</td>
            <td style="padding:8px;border-bottom:1px solid var(--border,#2a2d3a);font-size:12px">v{r.get('version','?')}</td>
            <td style="padding:8px;border-bottom:1px solid var(--border,#2a2d3a);font-size:12px">{r['content'][:100]}{'...' if len(r['content'])>100 else ''}</td>
        </tr>
        """

    return f"""
    <div style="overflow-x:auto;margin:20px 0">
        <table style="width:100%;border-collapse:collapse">
            <thead>
                <tr style="text-align:left;color:var(--muted,#8b8fa3);font-size:12px">
                    <th style="padding:8px;border-bottom:2px solid var(--border,#2a2d3a)">评分</th>
                    <th style="padding:8px;border-bottom:2px solid var(--border,#2a2d3a)">用户</th>
                    <th style="padding:8px;border-bottom:2px solid var(--border,#2a2d3a)">日期</th>
                    <th style="padding:8px;border-bottom:2px solid var(--border,#2a2d3a)">版本</th>
                    <th style="padding:8px;border-bottom:2px solid var(--border,#2a2d3a)">评价内容</th>
                </tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>
    </div>
    """


def tool_neg_summary(analysis: dict) -> str:
    """[Tool] Generate a narrative paragraph summarizing negative review causes. Returns HTML."""
    issues = analysis.get("issues", []) if analysis else []
    stats = analysis.get("statistics", {}) if analysis else {}
    total = stats.get("total_reviews", "?")
    neg_count = stats.get("neg_reviews", stats.get("neg_count", 0))

    # Build narrative based on findings
    issue_descs = []
    for iss in issues:
        count = len(iss.get("review_ids", []))
        cat = iss.get("category", "")
        pct = count / max(neg_count, 1) * 100
        if cat == "subscription_paywall":
            issue_descs.append(f"付费体验问题（{count}条，{pct:.0f}%）：用户反映免费试用承诺不兑现、App内无法管理订阅、不付费则完全无法使用")
        elif cat == "ux_ui":
            issue_descs.append(f"UX/广告体验问题（{count}条，{pct:.0f}%）：广告关闭按钮被隐藏、广告过长破坏训练节奏")
        elif cat == "content_quality":
            issue_descs.append(f"内容质量问题（{count}条，{pct:.0f}%）：第三方广告跳转、个性化训练计划未生效")
        else:
            issue_descs.append(f"{iss.get('title','其他')}（{count}条，{pct:.0f}%）")

    paragraph = "；".join(issue_descs) if issue_descs else "暂无分类数据"

    html = f"""
    <div style="background:var(--card-bg,#1a1d27);border:1px solid var(--border,#2a2d3a);border-radius:10px;padding:20px;margin-bottom:20px">
        <h3 style="color:var(--accent,#6c8cff);margin-bottom:12px">📊 差评原因摘要</h3>
        <p>共分析 <strong>{total}</strong> 条评价，其中 <strong style="color:#e0556a">{neg_count}</strong> 条为差评（{neg_count/max(int(total),1)*100:.0f}%）。</p>
        <p style="margin-top:12px;line-height:1.8">{paragraph}。</p>
    </div>
    """
    return html


def tool_save_dashboard(html_content: str) -> str:
    """[Tool] Save the analysis dashboard as an HTML file"""
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html_content)
    kb = os.path.getsize(OUTPUT_FILE) / 1024
    return f"Dashboard saved to {OUTPUT_FILE} ({kb:.1f} KB)"


# ============================================================
# Agent Prompt
# ============================================================

AGENT_SYSTEM_PROMPT = """You are a Data Analyst specialized in App Store review analytics.
Your job: generate a comprehensive, multi-dimensional analysis dashboard as an HTML page.

## Workflow

1. Call `get_data()` to load all reviews and analysis results
2. For EACH dimension below, call the corresponding tool:
   a. `wordcloud(neg_reviews)` — keyword word cloud from negative reviews
   b. `sentiment_timeline(all_reviews)` — sentiment stacked bar chart over time
   c. `high_risk_versions(all_reviews)` — identify high-risk versions with core issues
   d. `peak_negative_day(all_reviews)` — find the day with most negative reviews
   e. `version_trend(all_reviews)` — version reputation trend line chart
   f. `evidence_table(neg_reviews)` — evidence table with actual negative review quotes
3. Assemble ALL tool outputs into a complete HTML page
4. Call `save_dashboard(html)` to save the result

## HTML Template

Assemble the HTML using this structure. Replace `{N}` placeholders with tool outputs:

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>App Review Analysis Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root { --bg: #0f1117; --card-bg: #1a1d27; --border: #2a2d3a; --text: #e1e4ed; --muted: #8b8fa3; --accent: #6c8cff; }
* { margin:0; padding:0; box-sizing:border-box; }
body { background:var(--bg); color:var(--text); font-family:-apple-system,sans-serif; padding:24px; max-width:1200px; margin:0 auto; }
h1 { text-align:center; margin-bottom:8px; font-size:24px; }
h2 { font-size:18px; margin:24px 0 12px; color:var(--accent); }
.section { margin:24px 0; }
.grid-2 { display:grid; grid-template-columns:1fr 1fr; gap:20px; }
@media (max-width:768px) { .grid-2 { grid-template-columns:1fr; } }
</style>
</head>
<body>
<h1>📊 App Review Analysis Dashboard</h1>
<p style="text-align:center;color:var(--muted)">Generated: {timestamp}</p>

<h2>1. 差评关键词词云</h2>
<div class="section">{N1: wordcloud output}</div>

<h2>2. 评论情绪时间线</h2>
<div class="section">{N2: sentiment_timeline output}</div>

<div class="grid-2">
<div>
<h2>4. 高风险版本</h2>
{N4: high_risk_versions output}
</div>
<div>
<h2>5. 差评高峰日</h2>
{N5: peak_negative_day output}
</div>
</div>

<h2>6. 版本口碑趋势</h2>
<div class="section">{N6: version_trend output}</div>

<h2>7. 差评证据</h2>
<div class="section">{N7: evidence_table output}</div>

<p style="text-align:center;color:var(--muted);margin-top:32px">LaienTech Review Analysis · Auto-generated Dashboard</p>
</body>
</html>
```

## Rules
1. Every tool output must be placed exactly where the `{N}` placeholder is
2. Chart.js CDN MUST be included in <head> for charts to render
3. Preserve the HTML structure — do NOT add extra sections
4. Use actual tool output — do NOT fabricate data
5. The wordcloud ONLY shows negative review keywords, not positive ones
"""


# ============================================================
# Rule-Based Dashboard Generator (No LLM needed)
# ============================================================

def generate_rule_based_dashboard():
    """Generate dashboard without LLM — uses tools directly"""
    data = tool_get_data()
    reviews = data["reviews"]
    analysis = data.get("analysis", {})

    neg_reviews = [r for r in reviews if r.get("sentiment") == "negative"]

    wc = tool_wordcloud(neg_reviews)
    st = tool_sentiment_timeline(reviews)
    hr = tool_high_risk_versions(reviews)
    pk = tool_peak_negative_day(reviews)
    vt = tool_version_trend(reviews)
    ev = tool_evidence_table(neg_reviews)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>App Review Analysis Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root {{ --bg: #0f1117; --card-bg: #1a1d27; --border: #2a2d3a; --text: #e1e4ed; --muted: #8b8fa3; --accent: #6c8cff; }}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:var(--bg); color:var(--text); font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; padding:24px; max-width:1200px; margin:0 auto; }}
h1 {{ text-align:center; margin-bottom:8px; font-size:24px; }}
h2 {{ font-size:18px; margin:24px 0 12px; color:var(--accent); border-bottom:1px solid var(--border); padding-bottom:8px; }}
.section {{ margin:24px 0; }}
.grid-2 {{ display:grid; grid-template-columns:1fr 1fr; gap:20px; }}
@media (max-width:768px) {{ .grid-2 {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body>
<h1>📊 App Review Analysis Dashboard</h1>
<p style="text-align:center;color:var(--muted);margin-bottom:24px">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} | {len(reviews)} reviews analyzed</p>

<h2>1. 差评关键词词云</h2>
<div class="section">{wc}</div>

<h2>2. 评论情绪时间线</h2>
<div class="section">{st}</div>

<h2>3. 版本口碑趋势</h2>
<div class="section">{vt}</div>

<div class="grid-2">
<div>
<h2>4. 高风险版本</h2>
{hr}
</div>
<div>
<h2>5. 差评高峰日</h2>
{pk}
</div>
</div>

<h2>6. 差评证据 (Top 20)</h2>
<div class="section">{ev}</div>

<p style="text-align:center;color:var(--muted);margin-top:32px;padding:24px">LaienTech Review Analysis · Auto-generated Dashboard</p>
</body>
</html>"""

    tool_save_dashboard(html)
    return html


# ============================================================
# Main
# ============================================================
def main():
    print("=" * 60)
    print("  Step 3.5: Analysis Dashboard Generator")
    print("=" * 60)
    print(f"\n  Generating dashboard...")
    generate_rule_based_dashboard()
    kb = os.path.getsize(OUTPUT_FILE) / 1024
    print(f"  Saved: {OUTPUT_FILE} ({kb:.1f} KB)")
    print(f"  Open in browser to view interactive charts")
    print(f"  Done.")


if __name__ == "__main__":
    main()
