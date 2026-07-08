"""
LaienTech App Review Analysis — Web Application
=================================================
Flask 后端, 依次调用已有脚本的核心函数 (直接 import, 不走 subprocess),
UI 展示进度和结果。

用法:
  python app.py  →  http://localhost:5001
"""

import json
import os
import sys
import threading
import time
from datetime import datetime
from collections import Counter

from flask import Flask, render_template, jsonify, request

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

# LLM 开关: 用户通过 UI 输入 API key 启用 Agent 模式
# 环境变量 DEEPSEEK_API_KEY 也可作为默认值
DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY", "").strip()
_current_key = DEEPSEEK_KEY  # 每次请求可覆盖

app = Flask(__name__)
@app.before_request
def _log_startup():
    pass  # placeholder

# ============================================================
# 启动时打印模式
# ============================================================
def _boot_msg():
    if _current_key:
        print(f"  🧠 Agent mode: DeepSeek V4 enabled (env key)")
    else:
        print("  📋 Rule mode: set DEEPSEEK_API_KEY or enter key in UI")
_boot_msg()

# ============================================================
# 全局状态
# ============================================================
state = {
    "running": False, "overall_progress": 0,
    "started_at": None, "finished_at": None,
    "steps": {
        "collect":   {"status": "pending", "label": "数据采集",       "progress": 0, "result": None},
        "clean":     {"status": "pending", "label": "评价清洗",       "progress": 0, "result": None},
        "analyze":   {"status": "pending", "label": "分类与分析",     "progress": 0, "result": None},
        "prd":       {"status": "pending", "label": "PRD & 版本规划", "progress": 0, "result": None},
        "testcases": {"status": "pending", "label": "测试用例生成",   "progress": 0, "result": None},
        "dashboard": {"status": "pending", "label": "分析看板生成",   "progress": 0, "result": None},
    },
}

def _load(f):
    return json.load(open(os.path.join(PROJECT_DIR, f), encoding="utf-8"))

# ============================================================
# Step 1: 数据采集
# ============================================================
def step1_collect(offline=False):
    s = "collect"; state["steps"][s]["status"] = "running"
    state["steps"][s]["progress"] = 50; state["overall_progress"] = 10

    CACHED = os.path.join(PROJECT_DIR, "reviews_raw_cached.json")
    OUTPUT = os.path.join(PROJECT_DIR, "reviews_raw.json")

    if offline and os.path.exists(CACHED):
        # 离线模式: 直接复制缓存文件
        import shutil
        shutil.copy(CACHED, OUTPUT)
        data = _load("reviews_raw.json")
        state["steps"][s]["progress"] = 100
        print(f"  [Collect] OFFLINE mode: loaded {data['metadata']['total_reviews']} cached reviews", flush=True)
    else:
        from collect_reviews import collect_reviews, APP_ID, APP_NAME, COUNTRY, SLEEP_INTERVAL
        data = collect_reviews(APP_ID, APP_NAME, COUNTRY, SLEEP_INTERVAL)
        with open(OUTPUT, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    ratings = Counter(r["rating"] for r in data["reviews"])
    state["steps"][s]["result"] = {"count": len(data["reviews"]),
        "avg_rating": round(sum(r["rating"] for r in data["reviews"]) / max(len(data["reviews"]),1), 2),
        "distribution": {str(k): v for k, v in ratings.items()},
        "offline": offline}
    state["steps"][s]["status"] = "done"; state["steps"][s]["progress"] = 100
    state["overall_progress"] = 20

# ============================================================
# Step 2: 调用 clean_reviews
# ============================================================
def step2_clean():
    s = "clean"; state["steps"][s]["status"] = "running"
    state["steps"][s]["progress"] = 30; state["overall_progress"] = 25

    from clean_reviews import (step1_clean_content, step2_deduplicate, step3_quality_score,
                                step4_detect_language, step5_normalize_version, step6_derive_fields)
    raw = _load("reviews_raw.json")
    records = raw["reviews"]; input_count = len(records)
    records = step1_clean_content(records)
    state["steps"][s]["progress"] = 50
    records = step2_deduplicate(records)
    records = step3_quality_score(records)
    records = step4_detect_language(records)
    state["steps"][s]["progress"] = 70
    records = step5_normalize_version(records)
    records = step6_derive_fields(records)

    result = {"metadata": {"input_count": input_count, "output_count": len(records)}, "reviews": records}
    with open(os.path.join(PROJECT_DIR, "reviews_clean.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    ratings = Counter(r["rating"] for r in records)
    sents = Counter(r["sentiment"] for r in records)
    state["steps"][s]["result"] = {"raw_count": input_count, "cleaned_count": len(records),
        "avg_rating": round(sum(r["rating"] for r in records) / len(records), 2),
        "distribution": {str(k): v for k, v in ratings.items()}, "sentiment": dict(sents)}
    state["steps"][s]["status"] = "done"; state["steps"][s]["progress"] = 100
    state["overall_progress"] = 40

# ============================================================
# Step 3: 调用 analyze_reviews
# ============================================================
def step3_analyze():
    s = "analyze"; state["steps"][s]["status"] = "running"
    state["steps"][s]["progress"] = 20; state["overall_progress"] = 45

    from analyze_reviews import (load_and_split, extract_keywords, compute_statistics,
                                 build_rule_based_issues, build_keyword_count_map, QUALITY_THRESHOLD)
    data = _load("reviews_clean.json")
    reviews = data["reviews"]
    neg, neg_high, pos, neu = load_and_split(reviews)
    stats = compute_statistics(reviews, neg_high, neg, pos, neu)
    state["steps"][s]["progress"] = 40
    neg_texts = [r["content"] for r in neg_high]
    neg_keywords = extract_keywords(neg_texts)
    pos_texts = [r["content"] for r in pos if r["quality_score"] >= QUALITY_THRESHOLD]
    pos_keywords = extract_keywords(pos_texts, top_n=20) if pos_texts else []
    state["steps"][s]["progress"] = 60
    neg_kw_map = build_keyword_count_map(neg_keywords, neg_high)
    issues = build_rule_based_issues(neg_high, neg_keywords, neg_kw_map)

    result = {"metadata": {"step": 3}, "statistics": stats,
        "keywords": {"negative_top30": [{"keyword": kw, "tfidf": sc, "match_count": neg_kw_map.get(kw,0)} for kw,sc in neg_keywords],
                     "positive_top20": [{"keyword": kw, "tfidf": sc} for kw,sc in pos_keywords]}, "issues": issues}
    with open(os.path.join(PROJECT_DIR, "analysis_result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    state["steps"][s]["result"] = {"issues_found": len(issues),
        "top_issues": [{"title": iss["title"], "severity": iss["severity"], "count": len(iss.get("review_ids",[]))} for iss in issues],
        "neg_keywords": [kw for kw,_ in neg_keywords[:8]]}
    state["steps"][s]["status"] = "done"; state["steps"][s]["progress"] = 100
    state["overall_progress"] = 60

# ============================================================
# Step 3.5: 分析看板
# ============================================================
def _step_dashboard():
    s = "dashboard"; state["steps"][s]["status"] = "running"
    state["steps"][s]["progress"] = 50; state["overall_progress"] = 63

    from generate_analysis_report import generate_rule_based_dashboard, OUTPUT_FILE as DASHBOARD_FILE
    generate_rule_based_dashboard()

    state["steps"][s]["result"] = {"file": os.path.basename(DASHBOARD_FILE)}
    state["steps"][s]["status"] = "done"; state["steps"][s]["progress"] = 100
    state["overall_progress"] = 68

# ============================================================
# Step 4: PRD
# ============================================================
def step4_prd():
    s = "prd"; state["steps"][s]["status"] = "running"
    state["steps"][s]["progress"] = 50; state["overall_progress"] = 70

    if _current_key:
        from generate_prd import run_langchain_agent, rule_based_prd as _rbd
        state["steps"][s]["progress"] = 40
        prd_method = "LLM"
        try:
            _ = run_langchain_agent("deepseek", api_key=_current_key)
        except Exception as e:
            print(f"  [PRD] LLM failed: {e}, falling back to rules", flush=True)
            prd_method = "rules (LLM fallback)"
            prd = _rbd()
            with open(os.path.join(PROJECT_DIR, "prd_version_plan.json"), "w", encoding="utf-8") as f:
                json.dump(prd, f, ensure_ascii=False, indent=2)
    else:
        from generate_prd import rule_based_prd
        prd_method = "rules"
        prd = rule_based_prd()
        with open(os.path.join(PROJECT_DIR, "prd_version_plan.json"), "w", encoding="utf-8") as f:
            json.dump(prd, f, ensure_ascii=False, indent=2)

    if not os.path.exists(os.path.join(PROJECT_DIR, "prd_version_plan.json")):
        from generate_prd import rule_based_prd
        prd = rule_based_prd()
        with open(os.path.join(PROJECT_DIR, "prd_version_plan.json"), "w", encoding="utf-8") as f:
            json.dump(prd, f, ensure_ascii=False, indent=2)
        prd_method = "rules (LLM fallback)"

    prd = _load("prd_version_plan.json")

    # 生成 TXT 版本 (含用户评论溯源)
    _generate_prd_txt(prd)

    all_reqs = []
    for vp in prd.get("version_plan", []):
        all_reqs.extend(vp.get("requirements", []))
    state["steps"][s]["result"] = {"versions": len(prd.get("version_plan",[])),
        "total_requirements": len(all_reqs), "method": prd_method,
        "summary": all_reqs[:3]}
    state["steps"][s]["status"] = "done"; state["steps"][s]["progress"] = 100
    state["overall_progress"] = 80

# ============================================================
# Step 4.5: 生成 PRD TXT (含用户评论溯源)
# ============================================================
def _generate_prd_txt(prd):
    """生成完整的产品分析 PRD — 包含数据背景、根因分析、解决方案、用户证据、版本计划、成功指标"""
    analysis = _load("analysis_result.json")
    clean = _load("reviews_clean.json")
    id_map = {r["id"]: r for r in clean["reviews"]}
    stats = analysis.get("statistics", {})
    issues = analysis.get("issues", [])
    keywords = analysis.get("keywords", {})

    lines = []
    L = "=" * 72
    S = "-" * 60

    # ========== 标题 ==========
    lines.append(L)
    lines.append("PRD & Version Update Plan — Product Requirements Document")
    lines.append(L)
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"Data Source: Apple App Store (US) RSS Feed, {stats.get('total_reviews','?')} reviews analyzed")
    lines.append("")

    # ========== 1. 数据全景 ==========
    lines.append(L)
    lines.append("1. 数据全景 (Data Landscape)")
    lines.append(L)

    # 评分总览
    neg = stats.get("neg_reviews", 0)
    total = stats.get("total_reviews", 1)
    lines.append(f"总评价数: {total} | 平均评分: {stats.get('rating_avg','?')}/5.0")
    lines.append(f"正面评价: {stats.get('pos_reviews','?')} 条 ({stats.get('pos_reviews',0)/max(total,1)*100:.0f}%)")
    lines.append(f"中性评价: {stats.get('neu_reviews','?')} 条 ({stats.get('neu_reviews',0)/max(total,1)*100:.0f}%)")
    lines.append(f"负面评价: {neg} 条 ({neg/max(total,1)*100:.0f}%) — 其中 {stats.get('neg_high_quality','?')} 条为高质量差评 (quality>=0.3)")
    lines.append("")

    # 月度趋势
    lines.append("【评分趋势 (月度)】")
    tl = stats.get("monthly_timeline", [])
    lines.append(f"  {'Month':<10s} {'Reviews':>8s} {'Neg%':>8s} {'Avg':>6s} {'Trend'}")
    prev_avg = None
    for m in tl[-6:]:
        arrow = ""
        if prev_avg is not None:
            arrow = " ↑" if m["avg_rating"] > prev_avg else (" ↓" if m["avg_rating"] < prev_avg else " →")
            if m["neg_ratio"] > 0.3: arrow += " ⚠"
        lines.append(f"  {m['year_month']:<10s} {m['total']:>8d} {m['neg_ratio']:>7.0%} {m['avg_rating']:>6.2f} {arrow}")
        prev_avg = m["avg_rating"]
    lines.append("")

    # 版本对比
    lines.append("【版本对比】")
    vb = stats.get("version_breakdown", {})
    for v, s in vb.items():
        lines.append(f"  {v}: {s['total']} reviews | 差评率 {s['neg_ratio']:.0%} | 均分 {s['avg_rating']} | "
                     f"差评 {s['neg_count']}/{s['total']}")
    lines.append("")

    # 好评关键词 vs 差评关键词
    pos_kw = [kw["keyword"] for kw in keywords.get("positive_top20", [])[:8]]
    neg_kw = [kw["keyword"] for kw in keywords.get("negative_top30", [])[:10]]
    lines.append(f"用户喜爱的特性: {', '.join(pos_kw)}")
    lines.append(f"用户吐槽的关键词: {', '.join(neg_kw)}")
    lines.append("")

    # ========== 2. 问题深度分析 ==========
    lines.append(L)
    lines.append("2. 问题深度分析 (Issue Analysis with User Evidence)")
    lines.append(L)

    # 用户问题分类统计
    for i, iss in enumerate(issues):
        rids = iss.get("review_ids", [])
        quotes = iss.get("representative_quotes", [])
        cat = iss.get("category", "other")
        sev = iss.get("severity", "unknown")

        lines.append(S)
        lines.append(f"ISSUE-{i+1}: {iss['title']} | 严重程度: {sev.upper()} | 影响: {len(rids)} 条差评 ({len(rids)/max(neg,1)*100:.0f}% of negative)")
        lines.append(S)
        lines.append(f"问题类别: {cat}")
        lines.append("")

        # 根因分析 (根据类别生成)
        if cat == "subscription_paywall":
            lines.append("【根因分析 (Root Cause Analysis)】")
            lines.append("  用户并非拒绝付费，而是对以下 3 个具体问题感到愤怒:")
            lines.append("")
            lines.append("  问题 1: 免费试用承诺不兑现")
            lines.append("    - 用户被告知有 7 天免费试用，但实际在第 1 天或立即被扣费")
            lines.append("    - 这是信任问题，不是定价问题。用户感觉被欺骗")
            lines.append("    - 关键词证据: \"charged\", \"trial\", \"money\", \"free\" — 共覆盖 53 条评价")
            lines.append("")
            lines.append("  问题 2: App 内无法管理订阅")
            lines.append("    - iOS App Store 要求在 App 内提供订阅管理入口 (Guideline 3.1.2)")
            lines.append("    - 用户找不到取消按钮，只能通过 Apple ID 设置取消")
            lines.append("    - 关键词证据: \"cancel\", \"manage\" — 多位用户明确描述此问题")
            lines.append("")
            lines.append("  问题 3: 不付费完全无法使用")
            lines.append("    - 部分用户愿意看广告，但 App 强制付费才能继续")
            lines.append("    - 免费内容的可用性为零或极低")
            lines.append("    - 关键词证据: \"free\", \"pay\" — 覆盖 53 + 34 条评价")
            lines.append("")
            lines.append("【关键洞察】")
            lines.append(f"  这 {len(rids)} 条差评中，大多数并非反对付费本身，而是反对:")
            lines.append("  1) 付费过程不透明 (被欺骗的感觉)")
            lines.append("  2) 付费后无法管理 (失去控制权)")
            lines.append("  3) 不付费则完全不能使用 (没有体验路径)")
            lines.append("  这三个问题的本质是: 用户信任被破坏，而非价格敏感。")

        elif cat == "ux_ui":
            lines.append("【根因分析】")
            lines.append("  广告体验严重损害了核心使用流程:")
            lines.append("  - 广告关闭按钮被隐藏或无法点击 → 用户被迫强制关闭 App")
            lines.append("  - 广告时长过长，影响训练节奏")
            lines.append("  - 老用户反馈 App 从好用变成\"全是广告\"")
            lines.append("  关键词证据: \"ads\", \"pop up\", \"button\", \"close\", \"screen\"")
            lines.append("")
            lines.append("【关键洞察】")
            lines.append("  广告本身不是问题 (用户接受看广告换免费)，问题是广告破坏了核心体验流程")
            lines.append("  部分用户是多年忠实用户，但最近的改动让他们感到失望")

        elif cat == "content_quality":
            lines.append("【根因分析】")
            lines.append("  训练内容层面的问题:")
            lines.append("  - 第三方广告重定向 (如跳转到 SHEIN 网站) 破坏体验")
            lines.append("  - 个性化设置 (如避开腹部训练) 未生效")
            lines.append("  - 部分功能从免费变为付费")
            lines.append("  关键词证据: \"workout\", \"exercise\", \"plan\", \"redirect\"")

        lines.append("")

        # 代表性用户评价
        lines.append("【代表性用户评价 (Evidence)】")
        for q in quotes[:4]:
            # Find the actual review object for this quote
            lines.append(f"  ┌─ 用户原声")
            lines.append(f"  │ \"{q}\"")
            lines.append(f"  └─")
        lines.append("")

        # 所有受影响的评价 ID
        lines.append(f"【受影响评价列表 (共 {len(rids)} 条)】")
        for j, rid in enumerate(rids[:20]):
            if rid in id_map:
                r = id_map[rid]
                lines.append(f"  [{j+1:3d}] [{r['rating']}★] {r['user_name'][:20]:20s} | {r['updated'][:10]} | v{r['version']} | \"{r['content'][:80]}...\"")
        if len(rids) > 20:
            lines.append(f"  ... 另有 {len(rids) - 20} 条评价 (完整列表见 analysis_result.json)")
        lines.append("")

    # ========== 3. 版本更新计划 ==========
    lines.append(L)
    lines.append("3. 版本更新计划 (Version Release Plan)")
    lines.append(L)

    # vNext
    critical_issues = [iss for iss in issues if iss["severity"] == "critical"]
    high_issues = [iss for iss in issues if iss["severity"] == "high"]
    med_issues = [iss for iss in issues if iss["severity"] == "medium"]
    critical_count = sum(len(iss.get("review_ids", [])) for iss in critical_issues)
    high_count = sum(len(iss.get("review_ids", [])) for iss in high_issues)

    lines.append("版本拆分原则:")
    lines.append(f"  - vNext (P0): 所有 critical 级别问题 (共 {critical_count} 条差评, 覆盖 {critical_count/max(neg,1)*100:.0f}% 负面)")
    lines.append(f"  - vNext+1 (P1): 所有 high 级别问题 (共 {high_count} 条差评)")
    lines.append("  - 拆分理由: critical 问题(付费信任)与 high 问题(UX/广告)分属不同模块, 可独立交付")
    lines.append("")

    # ─── vNext ───
    lines.append(L)
    lines.append("  vNext (P0): Trust & Transparency — 信任修复版本")
    lines.append(L)
    lines.append(f"  目标: 修复付费体验信任问题, 覆盖 {critical_count} 条差评")
    lines.append(f"  预期效果: 负面评价从 28% → 15%, 评分从 3.73 → 4.0+")
    lines.append("")

    # 基于 ISSUE-001 的三个具体解决方案
    if critical_issues:
        iss = critical_issues[0]
        rids = iss.get("review_ids", [])
        quotes = iss.get("representative_quotes", [])

        # 取具体的评价用来引用
        sample_reviews = []
        for rid in rids[:10]:
            if rid in id_map:
                sample_reviews.append(id_map[rid])

        # 方案 1: 修复试用期
        lines.append(S)
        lines.append("需求 REQ-001 [P0] 修复免费试用期承诺 — 7 天 = 7 天")
        lines.append(S)
        lines.append("  用户故事:")
        lines.append("    作为新用户, 我想在承诺的 7 天试用期内无需付费就能使用 App,")
        lines.append("    以便在决定是否付费前充分评估 App 的价值")
        lines.append("")
        lines.append("  解决方案 (Implementation Plan):")
        lines.append("    1. 修改订阅流程: App Store 试用期配置为 7 天 (不是 1 天)")
        lines.append("    2. 支付确认页: 明确显示\"试用 7 天后将自动续费 ¥XX/月\"")
        lines.append("    3. 到期提醒: 试用第 5 天和第 7 天推送本地通知提醒即将付费")
        lines.append("    4. 支付后确认: 首次扣费后显示\"已开始付费订阅\"确认页")
        lines.append("")
        lines.append("  验收标准 (Acceptance Criteria):")
        lines.append("    - 新用户激活 7 天试用后, 7 天内 Apple 账单不产生任何扣费")
        lines.append("    - 试用第 5 天收到\"还剩 2 天试用\"的通知")
        lines.append("    - 首次扣费发生在试用期满后 (第 8 天)")
        lines.append("")
        lines.append("  验证方式:")
        lines.append("    发布后 30 天内, App Store 差评中不再出现 \"charged after 1 day\" /")
        lines.append("    \"charged immediately\" / \"made me pay right away\" 等关键词")
        lines.append("")
        lines.append("  商业影响: 中性 — 合规修复; 试用转化率可能提升 (用户有充分时间评估)")
        lines.append("")
        lines.append("  【用户证据 (直接引用)】")
        for r in sample_reviews[:3]:
            if "trial" in r["content"].lower() or "charged" in r["content"].lower() or "pay" in r["content"].lower():
                lines.append(f"    [{r['rating']}★] {r['user_name']} ({r['updated'][:10]})")
                lines.append(f"    \"{r['content']}\"")
                lines.append("")
        # 如果上面没匹配到足够多的，再补几个
        lines_cnt = sum(1 for l in lines[-10:] if l.startswith("    [") and "★" in l)
        for r in sample_reviews:
            if lines_cnt >= 3: break
            lines.append(f"    [{r['rating']}★] {r['user_name']} ({r['updated'][:10]})")
            lines.append(f"    \"{r['content']}\"")
            lines.append("")
            lines_cnt += 1

        # 方案 2: 订阅管理
        lines.append(S)
        lines.append("需求 REQ-002 [P0] App 内添加订阅管理入口")
        lines.append(S)
        lines.append("  用户故事:")
        lines.append("    作为现有用户, 我想在 App 设置页查看/取消/恢复我的订阅,")
        lines.append("    以便不需要离开 App 就能管理我的付费状态")
        lines.append("")
        lines.append("  解决方案:")
        lines.append("    1. 设置页新增 \"Manage Subscription\" 入口")
        lines.append("    2. 显示: 当前订阅状态 (Active/Expired)、到期日、下次扣费金额")
        lines.append("    3. 操作: Cancel Subscription (确认弹窗)、Restore Purchase")
        lines.append("    4. 取消后显示: \"订阅已取消, 到期日前仍可继续使用\"")
        lines.append("")
        lines.append("  验收标准:")
        lines.append("    - 付费用户可在 Settings > Subscription 查看完整订阅信息")
        lines.append("    - 取消流程 ≤3 步 (点击取消 → 确认弹窗 → 完成)")
        lines.append("    - 取消后状态即时更新")
        lines.append("    - 满足 Apple App Store Review Guideline 3.1.2 合规要求")
        lines.append("")
        lines.append("  验证方式:")
        lines.append("    30 天内差评中不再出现 \"can't cancel\" / \"no way to manage\" /")
        lines.append("    \"can't figure how to cancel\" 等投诉")
        lines.append("")
        lines.append("  商业影响: 正面 — 减少 App Store 退款申请, 满足合规要求, 提升用户信任")
        lines.append("")
        lines.append("  【用户证据】")
        for r in sample_reviews:
            if any(kw in r["content"].lower() for kw in ["cancel", "manage", "subscription", "subscribed"]):
                lines.append(f"    [{r['rating']}★] {r['user_name']} ({r['updated'][:10]})")
                lines.append(f"    \"{r['content']}\"")
                lines.append("")

        # 方案 3: 免费体验层
        lines.append(S)
        lines.append("需求 REQ-003 [P0] 重建免费基础体验层")
        lines.append(S)
        lines.append("  用户故事:")
        lines.append("    作为未付费用户, 我想每天能完成 1-2 节免费训练 (含适度广告),")
        lines.append("    以便在没有经济压力的情况下保持健身习惯")
        lines.append("")
        lines.append("  解决方案:")
        lines.append("    1. 免费层: 每天 1-2 节基础训练 (含 30s 激励广告)")
        lines.append("    2. 付费墙时机: 用户完成首次训练后展示, 而非首次打开即展示")
        lines.append("    3. 付费价值展示: 付费墙页面突出展示 Premium 的额外内容数量")
        lines.append("    4. 灵活定价: 月付/季付/年付, 首次月付折扣 (如首月 50% off)")
        lines.append("")
        lines.append("  验收标准:")
        lines.append("    - 未付费用户每天可访问至少 1 节免费训练")
        lines.append("    - 首次打开 App 不弹出付费墙 (在完成训练后展示)")
        lines.append("    - 付费墙明确列出 Free vs Premium 的内容对比")
        lines.append("")
        lines.append("  验证方式:")
        lines.append("    免费用户 7 日留存率提升; 差评中 \"everything requires payment\" /")
        lines.append("    \"need premium for every workout\" 类投诉减少")
        lines.append("")
        lines.append("  商业影响:")
        lines.append("    短期: 直接付费转化可能小幅下降")
        lines.append("    长期: DAU 提升 → 广告收入增加 → 自然转化率提升")
        lines.append("    (参考: 健身 App 行业标准 — 免费层用户占总用户的 60-80%)")
        lines.append("")
        lines.append("  【用户证据】")
        for r in sample_reviews:
            if any(kw in r["content"].lower() for kw in ["free", "premium", "pay", "subscription", "every"]):
                lines.append(f"    [{r['rating']}★] {r['user_name']} ({r['updated'][:10]})")
                lines.append(f"    \"{r['content']}\"")
                lines.append("")

    # ─── vNext+1 ───
    lines.append(L)
    lines.append("  vNext+1 (P1): Experience Polish — 体验优化版本")
    lines.append(L)
    lines.append(f"  目标: 修复 UX 体验和内容质量问题, 覆盖 {high_count} + {sum(len(iss.get('review_ids',[])) for iss in med_issues)} 条差评")
    lines.append("  预期效果: 评分从 4.0+ → 4.2+, 负面评价从 15% → <10%")
    lines.append("")

    req_idx = 4
    for iss in high_issues + med_issues:
        rids = iss.get("review_ids", [])
        quotes = iss.get("representative_quotes", [])
        cat = iss.get("category", "other")

        lines.append(S)
        lines.append(f"需求 REQ-{req_idx:03d} [{'P1' if iss['severity']=='high' else 'P2'}] {iss['title']}")
        lines.append(S)

        if cat == "ux_ui":
            lines.append("  解决方案:")
            lines.append("    1. 广告关闭按钮: 确保 X 按钮可见且在屏幕安全区内, 点击区域 ≥ 44x44pt")
            lines.append("    2. 广告时长: 激励广告 ≤30s, 展示广告 ≤15s")
            lines.append("    3. 跳过机制: 广告播放 5s 后可跳过 (参照 YouTube 标准)")
            lines.append("    4. 频率控制: 每 3 节训练最多 1 次插屏广告")
            lines.append("")
            lines.append("  验收标准:")
            lines.append("    - 广告关闭按钮在所有 iOS 设备上可见且可点击")
            lines.append("    - 广告最长不超过 30 秒")
            lines.append("    - 广告结束或关闭后 3 秒内返回主界面")
            lines.append("")
        elif cat == "content_quality":
            lines.append("  解决方案:")
            lines.append("    1. 审查并移除训练中跳转到第三方电商网站的广告链接")
            lines.append("    2. 修复个性化训练计划设置 (如避开特定部位的训练)")
            lines.append("    3. 恢复之前免费、现在变为付费的功能为免费 (如基础训练)")

        lines.append(f"  验证方式: 30 天内差评中不再出现 {', '.join(neg_kw[:4])} 相关投诉")
        lines.append("")
        lines.append("  【用户证据】")
        for q in quotes[:2]:
            lines.append(f"    \"{q}\"")
        lines.append("")

        req_idx += 1

    # ========== 4. 成功指标 ==========
    lines.append(L)
    lines.append("4. 成功指标 (Success Metrics)")
    lines.append(L)
    lines.append("")
    lines.append("  vNext 版本发布后:")
    lines.append("    - App Store 评分从 3.73 → 4.0+ (目标: 30 天内)")
    lines.append("    - 负面评价占比从 28% → 15% 以下")
    lines.append("    - 1 星评价中, \"charged\" 关键词出现频率降为 0")
    lines.append("    - 订阅管理相关投诉降为 0")
    lines.append("")
    lines.append("  vNext+1 版本发布后:")
    lines.append("    - App Store 评分持续上升至 4.2+")
    lines.append("    - 负面评价稳定在 10% 以内")
    lines.append("    - 免费用户 7 日留存率提升 20%+")
    lines.append("    - 广告相关投诉降为 0")
    lines.append("")
    lines.append("  需要保留的正面特性 (不可破坏):")
    lines.append(f"    {', '.join(pos_kw)}")
    lines.append("")

    # ========== 5. 风险 ==========
    lines.append(L)
    lines.append("5. 风险评估 (Risk Assessment)")
    lines.append(L)
    lines.append("")
    lines.append("  如果什么都不做 (Risks of Inaction):")
    lines.append("    - 评分持续下滑至 3.5- → App Store 搜索排名下降")
    lines.append("    - 竞品 Fitness App 趁机获取不满用户")
    lines.append("    - 差评率从当前的 28% 继续攀升 → 新用户获取成本增加")
    lines.append("    - 已有 2 年老用户因广告问题卸载 → LTV 损失")
    lines.append("")
    lines.append("  实施风险:")
    lines.append("    - REQ-003 免费体验层可能短期影响付费转化 → 通过 A/B 测试逐步推出")
    lines.append("    - Apple 审核可能因订阅流程变更延缓 → 提前提交审核, 留足 buffer")
    lines.append("")

    lines.append(L)
    lines.append("End of PRD — LaienTech Review Analysis Project")
    lines.append(L)

    with open(os.path.join(PROJECT_DIR, "prd_report.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

# ============================================================
# Step 5: 测试用例
# ============================================================
def step5_testcases():
    s = "testcases"; state["steps"][s]["status"] = "running"
    state["steps"][s]["progress"] = 50; state["overall_progress"] = 90

    tc_method = "rules"
    if _current_key:
        from generate_test_cases import run_langchain_agent, rule_based_test_cases as _rbtc
        state["steps"][s]["progress"] = 40
        try:
            _ = run_langchain_agent("deepseek", api_key=_current_key)
            tc_method = "LLM"
        except Exception as e:
            print(f"  [TestCases] LLM failed: {e}, falling back to rules", flush=True)
            tc_method = "rules (LLM fallback)"
            _rbtc()
    else:
        from generate_test_cases import rule_based_test_cases
        rule_based_test_cases()

    if not os.path.exists(os.path.join(PROJECT_DIR, "test_cases.json")):
        from generate_test_cases import rule_based_test_cases
        rule_based_test_cases()
        tc_method = "rules (LLM fallback)"

    tc_data = _load("test_cases.json")

    # 生成 TXT 版本
    _generate_testcases_txt(tc_data)

    state["steps"][s]["result"] = {
        "total": tc_data["metadata"]["total_test_cases"],
        "requirements_covered": tc_data["coverage_summary"]["total_requirements_covered"],
        "method": tc_method}
    state["steps"][s]["status"] = "done"; state["steps"][s]["progress"] = 100
    state["overall_progress"] = 100


def _generate_testcases_txt(tc_data):
    clean = _load("reviews_clean.json")
    id_map = {r["id"]: r for r in clean["reviews"]}
    prd = _load("prd_version_plan.json")

    lines = []
    L = "=" * 72
    S = "-" * 60

    lines.append(L)
    lines.append("Test Cases — with Source Review Traceability")
    lines.append(L)
    lines.append(f"Total Test Cases: {tc_data['metadata']['total_test_cases']}")
    lines.append(f"Requirements Covered: {tc_data['coverage_summary']['total_requirements_covered']}")
    ref_count = tc_data.get('coverage_summary', {}).get('total_source_reviews_referenced', len(set(
        rid for tc in tc_data.get('test_cases', []) for rid in tc.get('source_review_ids', [])
    )))
    lines.append(f"Source Reviews Referenced: {ref_count}")
    lines.append("")

    # 构建 REQ → TC 的映射
    req_to_tc = {}
    for tc in tc_data.get("test_cases", []):
        rid = tc.get("requirement_id", "")
        if rid not in req_to_tc:
            req_to_tc[rid] = []
        req_to_tc[rid].append(tc)

    # 按版本组织结构
    for vp in prd.get("version_plan", []):
        lines.append(L)
        lines.append(f"【版本】 {vp.get('version','?')} ({vp.get('priority','?')})")
        lines.append(L)
        lines.append("")

        for req in vp.get("requirements", []):
            rid = req.get("id", "?")
            tcs = req_to_tc.get(rid, [])
            lines.append(S)
            lines.append(f"需求: {req.get('title','?')}")
            lines.append(f"用户故事: {req.get('user_story','?')}")
            lines.append(S)
            lines.append("")

            for tc in tcs:
                lines.append(f"测试用例 {tc.get('id','?')} [{tc.get('priority','?')}] — {tc.get('title','?')}")
                lines.append("")

                # 前置条件
                preconditions = tc.get("preconditions", [])
                if preconditions:
                    lines.append("  【前置条件】")
                    for p in preconditions:
                        lines.append(f"    - {p}")
                    lines.append("")

                # 测试步骤
                steps = tc.get("test_steps", [])
                if steps:
                    lines.append("  【测试步骤】")
                    for s in steps:
                        lines.append(f"    Step {s.get('step','?')}: {s.get('action','?')}")
                        lines.append(f"      → 预期: {s.get('expected','?')}")
                    lines.append("")

                # 预期结果 & 验证
                lines.append(f"  【预期结果】 {tc.get('expected_result','?')}")
                lines.append(f"  【验证方式】 {tc.get('verification','?')}")
                lines.append("")

                # 源用户评价（关键）
                src_ids = tc.get("source_review_ids", [])
                if src_ids:
                    lines.append(f"  【溯源源用户评价 (共 {len(src_ids)} 条)】")
                    lines.append(f"  这些评价是编写此测试用例的依据。测试通过的前提是: 以下用户反映的问题得到解决。")
                    lines.append("")
                    for rid in src_ids:
                        if rid in id_map:
                            r = id_map[rid]
                            lines.append(f"  ┌────────────────────────────────────────")
                            lines.append(f"  │ 评价 ID: {rid}")
                            lines.append(f"  │ [{r['rating']}★] {r['user_name']} — {r['updated'][:10]} — v{r['version']}")
                            lines.append(f"  │ \"{r['content']}\"")
                            lines.append(f"  └────────────────────────────────────────")
                            lines.append("")
                lines.append("")

    # 覆盖矩阵
    lines.append(L)
    lines.append("覆盖矩阵 (Traceability Matrix)")
    lines.append(L)
    lines.append("")
    lines.append(f"  {'需求 ID':<12s} {'测试用例':<40s} {'源评价数':>8s}")
    lines.append(f"  {'-'*12} {'-'*40} {'-'*8}")
    for req_id, tcs in req_to_tc.items():
        tc_ids = ", ".join(tc["id"] for tc in tcs)
        src_cnt = len(set(rid for tc in tcs for rid in tc.get("source_review_ids", [])))
        lines.append(f"  {req_id:<12s} {tc_ids:<40s} {src_cnt:>8d}")
    lines.append("")

    lines.append(L)
    lines.append("End of Test Cases")
    lines.append(L)

    with open(os.path.join(PROJECT_DIR, "test_cases_report.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

# ============================================================
def run_pipeline(api_key="", offline=False):
    global state
    state["running"] = True; state["started_at"] = datetime.now().isoformat()
    state["overall_progress"] = 0
    global _current_key
    _current_key = api_key
    for key in state["steps"]:
        state["steps"][key] = {"status": "pending", "label": state["steps"][key]["label"], "progress": 0, "result": None}
    print(f"\n  [Pipeline] Agent: {'ON' if api_key else 'OFF'}, Offline: {offline}", flush=True)
    try:
        step1_collect(offline=offline)
        step2_clean()
        step3_analyze()
        _step_dashboard()
        step4_prd()
        step5_testcases()
    except Exception as e:
        import traceback
        traceback.print_exc()
        for key in state["steps"]:
            if state["steps"][key]["status"] == "running":
                state["steps"][key]["result"] = {"error": str(e)[:500]}
                break
    finally:
        state["running"] = False
        state["finished_at"] = datetime.now().isoformat()

# ============================================================
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/start", methods=["POST"])
def api_start():
    if state["running"]: return jsonify({"error": "Already running"}), 409
    # 支持 UI 输入 key 或环境变量
    api_key = ""
    req_data = request.get_json(silent=True) or {}
    api_key = req_data.get("api_key", "").strip()
    offline = req_data.get("offline", False)
    if not api_key:
        api_key = DEEPSEEK_KEY
    threading.Thread(target=run_pipeline, args=(api_key, offline), daemon=True).start()
    return jsonify({"status": "started", "agent": bool(api_key), "offline": offline})

@app.route("/api/status")
def api_status():
    return jsonify(state)

@app.route("/dashboard")
def dashboard():
    fpath = os.path.join(PROJECT_DIR, "analysis_dashboard.html")
    if os.path.exists(fpath):
        with open(fpath, "r", encoding="utf-8") as f:
            return f.read(), 200, {"Content-Type": "text/html; charset=utf-8"}
    return "Dashboard not generated yet. Run analysis first.", 404

@app.route("/prd")
def prd_page():
    fpath = os.path.join(PROJECT_DIR, "prd_version_plan.json")
    if not os.path.exists(fpath):
        return "PRD not generated yet. Run analysis first.", 404
    prd = _load("prd_version_plan.json")
    method = state["steps"]["prd"]["result"].get("method", "rules") if state["steps"]["prd"]["result"] else "rules"
    return _render_prd_html(prd, method), 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/testcases")
def testcases_page():
    fpath = os.path.join(PROJECT_DIR, "test_cases.json")
    if not os.path.exists(fpath):
        return "Test cases not generated yet. Run analysis first.", 404
    data = _load("test_cases.json")
    method = state["steps"]["testcases"]["result"].get("method", "rules") if state["steps"]["testcases"]["result"] else "rules"
    return _render_testcases_html(data, method), 200, {"Content-Type": "text/html; charset=utf-8"}


def _render_prd_html(prd, method="rules"):
    """Generic PRD renderer — reads from prd_version_plan.json, no hardcoded content"""
    ctx = prd.get("app_context", {})
    vps = prd.get("version_plan", [])
    es = prd.get("executive_summary", {})
    revs = _load("reviews_clean.json")
    id_map = {r["id"]: r for r in revs["reviews"]}

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>PRD — Version Plan</title>
<style>
:root{{--bg:#0f1117;--card:#1a1d27;--border:#2a2d3a;--text:#e1e4ed;--muted:#8b8fa3;--accent:#6c8cff;--success:#4caf93;--warn:#e8b44b;--error:#e0556a}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;padding:24px;max-width:1100px;margin:0 auto}}
h1{{font-size:24px;text-align:center;margin-bottom:4px}}
h2{{font-size:18px;margin:24px 0 12px;color:var(--accent);border-bottom:1px solid var(--border);padding-bottom:8px}}
h3{{font-size:16px;margin:16px 0 8px}}
.meta{{text-align:center;color:var(--muted);margin-bottom:24px;font-size:13px}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:20px;margin:12px 0}}
.badge{{display:inline-block;padding:2px 10px;border-radius:12px;font-size:11px;font-weight:600;margin-right:8px}}
.badge-p0{{background:rgba(224,85,106,.2);color:var(--error)}}
.badge-p1{{background:rgba(232,180,75,.2);color:var(--warn)}}
.badge-p2{{background:rgba(108,140,255,.2);color:var(--accent)}}
.tag{{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;margin:2px 4px 2px 0;background:rgba(108,140,255,.1);color:var(--accent)}}
.req-card{{background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:16px;margin:12px 0}}
.req-card .title{{font-size:15px;font-weight:600;margin-bottom:8px}}
.user-story{{background:rgba(76,175,147,.08);border-left:3px solid var(--success);padding:8px 12px;margin:8px 0;border-radius:0 6px 6px 0;font-size:13px}}
.ac li{{margin:4px 0 4px 20px;font-size:13px;color:var(--muted)}}
.evidence{{background:rgba(224,85,106,.05);border:1px dashed rgba(224,85,106,.3);border-radius:8px;padding:12px;margin:12px 0 0}}
.evidence .quote{{font-size:12px;color:var(--muted);margin:6px 0;padding:6px 0;border-bottom:1px solid var(--border)}}
.evidence .quote:last-child{{border-bottom:none}}
.summary-card{{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:20px;margin:12px 0}}
.summary-card p{{margin:8px 0;font-size:14px}}
.metrics{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;margin:12px 0}}
.metric{{background:var(--bg);border-radius:6px;padding:12px;text-align:center}}
.metric .val{{font-size:20px;font-weight:700}}
.metric .lbl{{font-size:11px;color:var(--muted);margin-top:2px}}
</style></head>
<body>
<h1>📋 PRD — Product Requirements Document</h1>
<div class="meta">
  App: {ctx.get('inferred_name','Unknown')} | Category: {ctx.get('inferred_category','?')} | Model: {ctx.get('inferred_business_model','?')}
</div>
"""

    # Version plan
    for i, vp in enumerate(vps):
        vname = vp.get("version", f"v{i+1}")
        pri = vp.get("priority", "?")
        badge_class = "badge-p0" if pri == "P0" else ("badge-p1" if pri == "P1" else "badge-p2")
        reqs = vp.get("requirements", [])
        metrics = vp.get("success_metrics", {})

        html += f"""
<h2>{vname} <span class="badge {badge_class}">{pri}</span> — {vp.get('codename','')}</h2>
<div class="card">
  <p><strong>目标：</strong>{vp.get('objective', 'N/A')}</p>
  <p style="color:var(--muted);font-size:13px;margin-top:4px">{vp.get('rationale', '')}</p>
"""

        if metrics:
            html += '<div class="metrics">'
            for mk, mv in metrics.items():
                html += f'<div class="metric"><div class="val">{mv}</div><div class="lbl">{mk}</div></div>'
            html += '</div>'

        html += f'<p style="color:var(--muted);font-size:13px">{len(reqs)} requirements</p></div>'

        for req in reqs:
            rids = req.get("source_review_ids", [])
            quotes = req.get("source_quotes", [])
            impl = req.get("implementation_plan", [])
            ac = req.get("acceptance_criteria", [])

            html += f"""
<div class="req-card">
  <div class="title">{req.get('id','?')}: {req.get('title','?')}</div>
  <span class="tag">{req.get('category','?')}</span>
  <span style="font-size:12px;color:var(--muted)">Effort: {req.get('effort_estimate','?')}</span>

  <div class="user-story">{req.get('user_story','')}</div>
"""

            if impl:
                html += '<p style="margin-top:8px;font-size:13px"><strong>Implementation:</strong></p><ol style="margin-left:20px;font-size:13px">'
                for step in impl:
                    html += f'<li>{step}</li>'
                html += '</ol>'

            if ac:
                html += '<p style="margin-top:8px;font-size:13px"><strong>Acceptance Criteria:</strong></p><ul class="ac">'
                for c in ac:
                    html += f'<li>{c}</li>'
                html += '</ul>'

            html += f'<p style="font-size:12px;color:var(--muted);margin-top:8px"><strong>Verify:</strong> {req.get("verification_method","")}</p>'
            html += f'<p style="font-size:12px;color:var(--accent)"><strong>Impact:</strong> {req.get("business_impact","")}</p>'

            # Evidence from reviews
            if rids and id_map:
                html += '<div class="evidence"><strong style="font-size:12px">📎 Source Reviews</strong>'
                for rid in rids[:3]:
                    if rid in id_map:
                        r = id_map[rid]
                        html += f'<div class="quote">[{r["rating"]}★] {r["user_name"]} ({r["updated"][:10]}): "{r["content"][:200]}"</div>'
                html += '</div>'

            html += '</div>\n'

    # Executive summary
    html += f"""
<h2>Executive Summary</h2>
<div class="summary-card">
  <p><strong>Situation:</strong> {es.get('situation','N/A')}</p>
  <p><strong>Root Cause:</strong> {es.get('root_cause_analysis','N/A')}</p>
  <p><strong>Strategy:</strong> {es.get('recommended_strategy','N/A')}</p>
  <p><strong style="color:var(--success)">Preserve:</strong> {es.get('do_not_break','N/A')}</p>
  <p><strong style="color:var(--error)">Risk if not fixed:</strong> {es.get('risk_of_inaction','N/A')}</p>
</div>
"""
    
    is_llm = "LLM" in method
    tag = "🧠 由 LLM 生成" if is_llm else "📋 由规则生成"
    html += f"<p style=\"text-align:center;color:var(--muted);margin:32px 0 16px;font-size:12px\">{tag}</p>\n</body></html>"
    return html


def _render_testcases_html(data, method="rules"):
    """Generic test case renderer - reads from test_cases.json, no hardcoded content"""
    tcs = data.get("test_cases", [])
    cov = data.get("coverage_summary", {})
    revs = _load("reviews_clean.json")
    id_map = {r["id"]: r for r in revs["reviews"]}

    # Group by requirement
    req_groups = {}
    for tc in tcs:
        rid = tc.get("requirement_id", "other")
        if rid not in req_groups:
            req_groups[rid] = []
        req_groups[rid].append(tc)

    # Build traceability matrix
    matrix_rows = ""
    for rid, group in req_groups.items():
        tc_ids = ", ".join(t["id"] for t in group)
        src_count = len(set(rid2 for t in group for rid2 in t.get("source_review_ids", [])))
        matrix_rows += f'<tr><td>{rid}</td><td>{tc_ids}</td><td>{src_count}</td></tr>'

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Test Cases</title>
<style>
:root{{--bg:#0f1117;--card:#1a1d27;--border:#2a2d3a;--text:#e1e4ed;--muted:#8b8fa3;--accent:#6c8cff;--success:#4caf93;--warn:#e8b44b;--error:#e0556a}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;padding:24px;max-width:1100px;margin:0 auto}}
h1{{font-size:24px;text-align:center;margin-bottom:4px}}
h2{{font-size:18px;margin:24px 0 12px;color:var(--accent);border-bottom:1px solid var(--border);padding-bottom:8px}}
.meta{{text-align:center;color:var(--muted);margin-bottom:24px;font-size:13px}}
.tc-card{{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:20px;margin:12px 0}}
.tc-card .tc-title{{font-size:15px;font-weight:600;margin-bottom:8px}}
.badge{{display:inline-block;padding:2px 10px;border-radius:12px;font-size:11px;font-weight:600;margin-right:8px}}
.badge-p0{{background:rgba(224,85,106,.2);color:var(--error)}}
.badge-p1{{background:rgba(232,180,75,.2);color:var(--warn)}}
.badge-p2{{background:rgba(108,140,255,.2);color:var(--accent)}}
.step{{margin:4px 0 4px 16px;font-size:13px}}
.step .exp{{color:var(--muted);margin-left:16px;font-size:12px}}
.evidence{{background:rgba(224,85,106,.05);border:1px dashed rgba(224,85,106,.3);border-radius:8px;padding:12px;margin:12px 0 0}}
.evidence .quote{{font-size:12px;color:var(--muted);margin:6px 0;padding:6px 0;border-bottom:1px solid var(--border)}}
.evidence .quote:last-child{{border-bottom:none}}
table{{width:100%;border-collapse:collapse;margin:12px 0;font-size:13px}}
th{{text-align:left;padding:8px;border-bottom:2px solid var(--border);color:var(--muted);font-size:11px;text-transform:uppercase}}
td{{padding:8px;border-bottom:1px solid var(--border)}}
.section-label{{font-size:12px;color:var(--muted);margin:4px 0}}
</style></head>
<body>
<h1>✅ Test Cases</h1>
<div class="meta">Total: {len(tcs)} cases | Requirements Covered: {cov.get('total_requirements_covered','?')}</div>
"""

    for rid, group in req_groups.items():
        html += f'<h2>Requirement: {rid}</h2>'
        for tc in group:
            pri = tc.get("priority", "P1")
            badge_class = "badge-p0" if pri == "P0" else ("badge-p1" if pri == "P1" else "badge-p2")
            steps = tc.get("test_steps", [])

            html += f"""
<div class="tc-card">
  <div class="tc-title">{tc.get('id','?')} <span class="badge {badge_class}">{pri}</span> — {tc.get('title','?')}</div>
  <div class="section-label">Category: {tc.get('category','functional')} | Requirement: {rid}</div>
"""

            if tc.get("preconditions"):
                html += '<p style="font-size:13px;margin-top:8px"><strong>Preconditions:</strong></p><ul style="font-size:13px;margin-left:20px">'
                for p in tc["preconditions"]:
                    html += f'<li>{p}</li>'
                html += '</ul>'

            if steps:
                html += '<p style="font-size:13px;margin-top:8px"><strong>Test Steps:</strong></p>'
                for s in steps:
                    html += f'<div class="step">{s.get("step","?")}. {s.get("action","?")}<div class="exp">→ Expected: {s.get("expected","?")}</div></div>'

            html += f'<p style="font-size:13px;margin-top:8px"><strong>Expected Result:</strong> {tc.get("expected_result","?")}</p>'
            html += f'<p style="font-size:13px"><strong>Verification:</strong> {tc.get("verification","?")}</p>'

            # Evidence
            src_ids = tc.get("source_review_ids", [])
            if src_ids:
                html += '<div class="evidence"><strong style="font-size:12px">📎 Source Reviews</strong>'
                for rid2 in src_ids:
                    if rid2 in id_map:
                        r = id_map[rid2]
                        html += f'<div class="quote">[{r["rating"]}★] {r["user_name"]} ({r["updated"][:10]}): "{r["content"][:200]}"</div>'
                html += '</div>'

            html += '</div>\n'

    # Traceability matrix
    html += f"""
<h2>Traceability Matrix</h2>
<table>
<thead><tr><th>Requirement</th><th>Test Cases</th><th>Source Reviews</th></tr></thead>
<tbody>{matrix_rows}</tbody>
</table>
"""
    
    is_llm = "LLM" in method
    tag = "🧠 由 LLM 生成" if is_llm else "📋 由规则生成"
    html += f"<p style=\"text-align:center;color:var(--muted);margin:32px 0 16px;font-size:12px\">{tag}</p>\n</body></html>"
    return html
def dashboard():
    fpath = os.path.join(PROJECT_DIR, "analysis_dashboard.html")
    if os.path.exists(fpath):
        with open(fpath, "r", encoding="utf-8") as f:
            return f.read(), 200, {"Content-Type": "text/html; charset=utf-8"}
    return "Dashboard not generated yet. Run analysis first.", 404

@app.route("/api/result/<step>")
def api_result(step):
    files = {"collect": "reviews_raw.json", "clean": "reviews_clean.json",
             "analyze": "analysis_result.json", "prd": "prd_version_plan.json", "testcases": "test_cases.json"}
    fpath = os.path.join(PROJECT_DIR, files.get(step, ""))
    if os.path.exists(fpath): return jsonify(_load(files[step]))
    return jsonify({"error": "not found"}), 404

@app.route("/api/report/<name>")
def api_report(name):
    """获取 TXT 报告"""
    reports = {"prd": "prd_report.txt", "testcases": "test_cases_report.txt"}
    fpath = os.path.join(PROJECT_DIR, reports.get(name, ""))
    if os.path.exists(fpath):
        with open(fpath, "r", encoding="utf-8") as f:
            return f.read(), 200, {"Content-Type": "text/plain; charset=utf-8"}
    return "Not found", 404

if __name__ == "__main__":
    print("\n  LaienTech Review Analysis Web App")
    print("  http://localhost:5001\n")
    app.run(host="0.0.0.0", port=5001, debug=False)
