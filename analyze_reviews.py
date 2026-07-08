"""
Step 3: Review Analysis & Issue Discovery
============================================
三层分析架构:
  Layer 1 — 规则预处理: TF-IDF 关键词 + 统计 (纯本地, 零成本)
  Layer 2 — LLM 语义聚类: 1次 API call 做主题聚类+根因分析 (可选)
  Layer 3 — Grounding 验证: review_id 溯源, 防幻觉

输出: analysis_result.json (结构化问题列表 + 统计)

用法:
  # 仅规则分析 (无需 API key)
  python analyze_reviews.py

  # 使用 LLM 增强 (需要 OpenAI 兼容 API)
  python analyze_reviews.py --llm openai --api-key sk-xxx
  python analyze_reviews.py --llm ollama --ollama-model llama3
"""

import json
import os
import re
import sys
from datetime import datetime
from collections import Counter, defaultdict

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer, ENGLISH_STOP_WORDS

# ============================================================
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE = os.path.join(PROJECT_DIR, "reviews_clean.json")
OUTPUT_FILE = os.path.join(PROJECT_DIR, "analysis_result.json")

# 分析参数
QUALITY_THRESHOLD = 0.3   # 高质量阈值
SENTIMENT_TARGET = "negative"  # 分析目标: 差评
TOP_NGRAM = 30            # 提取 top-N 关键词


# ============================================================
# Layer 1: 规则预处理
# ============================================================

def load_and_split(reviews):
    """按情感 + 质量分组"""
    neg = [r for r in reviews if r["sentiment"] == SENTIMENT_TARGET]
    neg_high = [r for r in neg if r["quality_score"] >= QUALITY_THRESHOLD]
    pos = [r for r in reviews if r["sentiment"] == "positive"]
    neu = [r for r in reviews if r["sentiment"] == "neutral"]
    return neg, neg_high, pos, neu


def extract_keywords(texts, top_n=TOP_NGRAM):
    """TF-IDF + N-gram 关键词提取"""
    stop_words = set(ENGLISH_STOP_WORDS)
    # 额外停用词 (app 名称变体)
    custom_stops = {"app", "workout", "women", "gym", "home", "im", "ve", "don", "didn", "doesn", "can", "get"}
    stop_words.update(custom_stops)

    vec = TfidfVectorizer(
        stop_words=list(stop_words),
        ngram_range=(1, 3),      # unigrams, bigrams, trigrams
        max_features=200,
        min_df=2,                # 至少出现 2 次
        max_df=0.8,              # 过滤掉出现在 80% 文档中的通用词
    )
    tfidf = vec.fit_transform(texts)
    feature_names = vec.get_feature_names_out()
    scores = np.asarray(tfidf.sum(axis=0)).flatten()

    top_indices = scores.argsort()[::-1][:top_n]
    return [(feature_names[i], round(float(scores[i]), 3)) for i in top_indices]


def build_keyword_count_map(keywords, reviews_subset):
    """统计每条关键词在多少条评价中出现"""
    result = {}
    for kw, _ in keywords:
        count = sum(1 for r in reviews_subset if kw.lower() in r["content"].lower())
        result[kw] = count
    return result


def compute_statistics(reviews, neg_high, neg, pos, neu):
    """多维度统计"""
    # 评分趋势 (按月)
    monthly = defaultdict(lambda: {"total": 0, "neg": 0, "pos": 0, "ratings": []})
    for r in reviews:
        ym = r.get("year_month", "unknown")
        monthly[ym]["total"] += 1
        monthly[ym]["ratings"].append(r["rating"])
        if r["sentiment"] == "negative":
            monthly[ym]["neg"] += 1
        elif r["sentiment"] == "positive":
            monthly[ym]["pos"] += 1

    timeline = []
    for ym in sorted(monthly.keys()):
        m = monthly[ym]
        timeline.append({
            "year_month": ym,
            "total": m["total"],
            "neg_count": m["neg"],
            "pos_count": m["pos"],
            "neg_ratio": round(m["neg"] / m["total"], 3) if m["total"] else 0,
            "avg_rating": round(sum(m["ratings"]) / len(m["ratings"]), 2),
        })

    # 版本维度
    version_stats = defaultdict(lambda: {"total": 0, "neg": 0, "ratings": []})
    for r in reviews:
        v = r.get("major_minor", "unknown")
        version_stats[v]["total"] += 1
        version_stats[v]["ratings"].append(r["rating"])
        if r["sentiment"] == "negative":
            version_stats[v]["neg"] += 1

    versions = {}
    for v, s in sorted(version_stats.items()):
        versions[v] = {
            "total": s["total"],
            "neg_count": s["neg"],
            "neg_ratio": round(s["neg"] / s["total"], 3) if s["total"] else 0,
            "avg_rating": round(sum(s["ratings"]) / len(s["ratings"]), 2),
        }

    return {
        "total_reviews": len(reviews),
        "rating_avg": round(sum(r["rating"] for r in reviews) / len(reviews), 2),
        "neg_reviews": len(neg),
        "neg_high_quality": len(neg_high),
        "pos_reviews": len(pos),
        "neu_reviews": len(neu),
        "quality_threshold": QUALITY_THRESHOLD,
        "monthly_timeline": timeline,
        "version_breakdown": versions,
    }


def run_layer1_analysis(reviews):
    """Layer 1: 规则预处理"""
    neg, neg_high, pos, neu = load_and_split(reviews)
    stats = compute_statistics(reviews, neg_high, neg, pos, neu)

    # 差评关键词
    neg_texts = [r["content"] for r in neg_high]
    neg_keywords = extract_keywords(neg_texts)

    # 好评关键词 (对照组)
    pos_texts = [r["content"] for r in pos if r["quality_score"] >= QUALITY_THRESHOLD]
    pos_keywords = extract_keywords(pos_texts, top_n=20) if pos_texts else []

    # 关键词覆盖数
    neg_kw_map = build_keyword_count_map(neg_keywords, neg_high)

    print(f"  [Layer 1] Rules: {len(neg_high)} negative reviews analyzed")
    print(f"    Top neg keywords: {[kw for kw, _ in neg_keywords[:10]]}")
    return stats, neg_keywords, pos_keywords, neg_kw_map, neg_high, neg


# ============================================================
# Layer 2: LLM 语义聚类
# ============================================================

def build_llm_prompt(neg_high, stats, neg_keywords):
    """构造 LLM 分析 prompt"""
    # 差评数据 (含 ID, 必须可追溯)
    review_lines = []
    for r in neg_high[:80]:  # 取 top-80 高质量差评 (约 6K tokens)
        review_lines.append(
            f"[id:{r['id']}] [{r['rating']}*] [{r['major_minor']}] "
            f"\"{r['content']}\""
        )
    reviews_text = "\n".join(review_lines)

    prompt = f"""You are a product analyst. Analyze the following App Store reviews for a workout app.

APP CONTEXT: "Workout for Women: Home Gym" — a fitness app for women.
Total reviews analyzed: {stats['total_reviews']}, Negative: {stats['neg_reviews']}, Avg rating: {stats['rating_avg']}
Top negative keywords from TF-IDF: {[kw for kw, _ in neg_keywords[:15]]}

BELOW ARE {len(neg_high[:80])} HIGH-QUALITY NEGATIVE REVIEWS. Each has a unique review ID.

{reviews_text}

TASK: Cluster these reviews into 5-8 thematic issues. For each issue, output:

```json
{{
  "issues": [
    {{
      "id": "ISSUE-001",
      "category": "one of: bug_crash, subscription_paywall, ux_ui, content_quality, performance, feature_request, onboarding, other",
      "title": "Short descriptive title",
      "severity": "critical|high|medium|low",
      "description": "2-3 sentence root cause analysis of what users are experiencing",
      "review_ids": ["id1", "id2", ...],
      "representative_quotes": ["quote from review id1", "quote from review id2"],
      "affected_version": "8.4" or "8.3",
      "reproducible": true/false,
      "user_impact": "Brief statement of how this impacts user experience"
    }}
  ],
  "summary": "Executive summary of top 3 issues",
  "positive_signals": "What users like (from context, not just these negative reviews)"
}}
```

RULES:
- Every review_id MUST be an actual id from the reviews above
- representative_quotes MUST be exact excerpts from the review content
- Do NOT fabricate issues or reviews — only cluster what exists
- Severity: critical(>15 reviews), high(8-15), medium(3-7), low(1-2)
"""

    return prompt, len(neg_high[:80])


def call_openai(prompt, api_key, model="gpt-4o-mini"):
    """调用 OpenAI 兼容 API"""
    import requests
    resp = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.3},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def call_ollama(prompt, model="llama3.1"):
    """调用本地 Ollama"""
    import requests
    resp = requests.post(
        "http://localhost:11434/api/generate",
        json={"model": model, "prompt": prompt, "stream": False},
        timeout=300,
    )
    resp.raise_for_status()
    return resp.json()["response"]


def run_layer2_analysis(neg_high, stats, neg_keywords, llm_mode=None, **kwargs):
    """Layer 2: LLM 分析 (可选)"""
    if not llm_mode:
        print("  [Layer 2] LLM: SKIPPED (no --llm flag)")
        return None

    prompt, count = build_llm_prompt(neg_high, stats, neg_keywords)
    print(f"  [Layer 2] LLM: {count} reviews → prompt (~{len(prompt)//4} tokens)")

    try:
        if llm_mode == "openai":
            response = call_openai(prompt, kwargs.get("api_key", ""))
        elif llm_mode == "ollama":
            response = call_ollama(prompt, kwargs.get("ollama_model", "llama3.1"))
        else:
            print(f"  [Layer 2] Unknown LLM mode: {llm_mode}")
            return None
    except Exception as e:
        print(f"  [Layer 2] LLM call failed: {e}")
        return None

    # 尝试解析 JSON
    try:
        json_match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(1))
        return json.loads(response)
    except json.JSONDecodeError:
        print("  [Layer 2] LLM response not valid JSON, saving raw")
        return {"raw_response": response}

    return None


# ============================================================
# Layer 3: Grounding 验证
# ============================================================

def run_layer3_grounding(llm_result, reviews):
    """验证 LLM 输出的每个 review_id 是否真实存在 + claim 是否有原文支撑"""
    if not llm_result or "issues" not in llm_result:
        print("  [Layer 3] Grounding: SKIPPED (no LLM result)")
        return None

    # 构建 review_id → content 索引
    id_to_review = {r["id"]: r for r in reviews}

    issues = llm_result.get("issues", [])
    grounding_results = []

    for issue in issues:
        review_ids = issue.get("review_ids", [])
        quotes = issue.get("representative_quotes", [])
        title_keywords = set(re.findall(r"\w+", issue.get("title", "").lower()))

        verified = 0
        unverified = 0
        verified_details = []

        for rid in review_ids:
            if rid not in id_to_review:
                unverified += 1
                continue
            content = id_to_review[rid]["content"].lower()
            # 检查 claim 是否在原文中有支撑
            found = any(kw in content for kw in title_keywords if len(kw) > 3)
            if found:
                verified += 1
                verified_details.append({"review_id": rid, "verified": True, "content": id_to_review[rid]["content"][:150]})
            else:
                unverified += 1
                verified_details.append({"review_id": rid, "verified": False, "content": id_to_review[rid]["content"][:150]})

        confidence = "high" if verified / max(len(review_ids), 1) >= 0.7 else ("medium" if verified > 0 else "low")
        grounding_results.append({
            "issue_id": issue["id"],
            "total_review_ids": len(review_ids),
            "verified": verified,
            "unverified": unverified,
            "confidence": confidence,
            "details": verified_details,
        })

    verified_total = sum(g["verified"] for g in grounding_results)
    total_ids = sum(g["total_review_ids"] for g in grounding_results)
    print(f"  [Layer 3] Grounding: {verified_total}/{total_ids} reviews verified, "
          f"{sum(1 for g in grounding_results if g['confidence']=='high')}/{len(grounding_results)} issues high confidence")
    return grounding_results


# ============================================================
# Layer 1 增强: 规则聚类 (无 LLM 时的后备方案)
# ============================================================

def build_rule_based_issues(neg_high, neg_keywords, neg_kw_map):
    """基于关键词共现的简单规则聚类，作为无 LLM 时的基线"""
    patterns = {
        "payment_and_subscription": [
            "pay", "subscription", "subscribed", "charged", "charge",
            "money", "free trial", "trial", "purchase", "price", "cancel",
            "refund", "billed", "cost", "expensive", "worth", "paid",
        ],
        "ux_and_ads": [
            "screen", "button", "click", "interface", "confusing", "hard navigate",
            "find", "menu", "option", "setting", "pop up", "popup", "ad",
            "design", "layout",
        ],
        "content_quality": [
            "exercise", "workout", "routine", "train", "plan", "program",
            "video", "instruction", "repeat", "same", "boring", "variety",
            "custom", "beginner", "advanced",
        ],
        "bug_crash": [
            "bug", "crash", "freeze", "broken", "glitch", "error",
            "doesn work", "doesnt work", "stuck", "loading",
            "failed", "issue", "problem",
        ],
        "performance": [
            "slow", "lag", "battery", "drain", "buffering", "download",
            "offline", "data", "wifi", "streaming",
        ],
        "feature_suggestions": [
            "wish", "would like", "could add", "suggest", "need",
            "please add", "hope", "want",
        ],
        "onboarding": [
            "first", "start", "begin", "question", "quiz", "sign",
            "account", "login", "register",
        ],
    }

    # Chinese display names for categories
    CATEGORY_NAMES_CN = {
        "payment_and_subscription": "付费与订阅问题",
        "ux_and_ads": "用户体验与广告问题",
        "content_quality": "内容质量问题",
        "bug_crash": "Bug与崩溃问题",
        "performance": "性能问题",
        "feature_suggestions": "功能建议",
        "onboarding": "新手引导问题",
    }

    issues = []
    assigned_ids = set()

    for category, keywords in patterns.items():
        matched = []
        for r in neg_high:
            if r["id"] in assigned_ids:
                continue
            content = r["content"].lower()
            if any(kw in content for kw in keywords):
                matched.append(r)
                assigned_ids.add(r["id"])

        if len(matched) >= 2:
            severity = "critical" if len(matched) >= 15 else ("high" if len(matched) >= 8 else ("medium" if len(matched) >= 3 else "low"))
            issues.append({
                "id": f"ISSUE-{len(issues)+1:03d}",
                "category": category,
                "title": CATEGORY_NAMES_CN.get(category, category),
                "severity": severity,
                "description": f"{len(matched)} 条差评提到 {CATEGORY_NAMES_CN.get(category, category)}。关键词: {', '.join([kw for kw in keywords if any(kw in r['content'].lower() for r in matched)])[:100]}。",
                "review_ids": [r["id"] for r in matched],
                "representative_quotes": [r["content"][:200] for r in matched[:3]],
                "affected_version": Counter(r["major_minor"] for r in matched).most_common(1)[0][0],
                "reproducible": len(matched) >= 5,
                "user_impact": f"影响 {len(matched)} 位用户 ({len(matched)/len(neg_high)*100:.0f}% 的不满用户)。",
                "_method": "rule_based",
            })

    # Unassigned → "other"
    unassigned = [r for r in neg_high if r["id"] not in assigned_ids]
    if unassigned:
        issues.append({
            "id": f"ISSUE-{len(issues)+1:03d}",
            "category": "other",
            "title": "其他问题",
            "severity": "low",
            "description": f"{len(unassigned)} 条差评未归类到具体类别。",
            "review_ids": [r["id"] for r in unassigned],
            "representative_quotes": [r["content"][:200] for r in unassigned[:5]],
            "affected_version": Counter(r["major_minor"] for r in unassigned).most_common(1)[0][0],
            "reproducible": False,
            "user_impact": f"散布的 {len(unassigned)} 条其他类型的差评。",
            "_method": "rule_based",
        })

    print(f"  [Layer 1+] Rule-based clustering: {len(issues)} issues, {len(assigned_ids)}/{len(neg_high)} assigned")
    return issues


# ============================================================
def main():
    mode = "llm" if "--llm" in sys.argv else "rules"
    llm_mode = None
    api_key = None
    ollama_model = "llama3.1"

    for i, arg in enumerate(sys.argv):
        if arg == "--llm" and i + 1 < len(sys.argv):
            llm_mode = sys.argv[i + 1]
        if arg == "--api-key" and i + 1 < len(sys.argv):
            api_key = sys.argv[i + 1]
        if arg == "--ollama-model" and i + 1 < len(sys.argv):
            ollama_model = sys.argv[i + 1]

    print("=" * 55)
    print(f"  Step 3: Review Analysis (mode: {mode})")
    print("=" * 55)

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    reviews = data["reviews"]
    print(f"\n  Input: {len(reviews)} reviews from {os.path.basename(INPUT_FILE)}")
    print()

    # Layer 1
    stats, neg_keywords, pos_keywords, neg_kw_map, neg_high, neg_all = run_layer1_analysis(reviews)

    # Layer 1+: Rule-based clustering (always run as baseline)
    rule_issues = build_rule_based_issues(neg_high, neg_keywords, neg_kw_map)

    # Layer 2: LLM (optional)
    llm_result = run_layer2_analysis(neg_high, stats, neg_keywords, llm_mode,
                                      api_key=api_key, ollama_model=ollama_model)

    # Prefer LLM issues if available and valid, else use rule-based
    if llm_result and "issues" in llm_result and len(llm_result.get("issues", [])) > 0:
        issues = llm_result["issues"]
        issues_source = "llm"
        llm_summary = llm_result.get("summary", "")
        pos_signals = llm_result.get("positive_signals", "")
    else:
        issues = rule_issues
        issues_source = "rule_based"
        llm_summary = ""
        pos_signals = ""

    # Layer 3: Grounding
    grounding = run_layer3_grounding({"issues": issues}, reviews) if issues else None

    # Build final result
    result = {
        "metadata": {
            "step": 3,
            "stage": "Review Analysis & Issue Discovery",
            "analysis_mode": issues_source,
            "analyzed_at": datetime.now().isoformat(),
            "input_reviews": len(reviews),
            "negative_analyzed": len(neg_high),
            "quality_threshold": QUALITY_THRESHOLD,
        },
        "statistics": stats,
        "keywords": {
            "negative_top30": [{"keyword": kw, "tfidf": score, "match_count": neg_kw_map.get(kw, 0)} for kw, score in neg_keywords],
            "positive_top20": [{"keyword": kw, "tfidf": score} for kw, score in pos_keywords],
        },
        "issues": issues,
        "llm_summary": llm_summary,
        "positive_signals": pos_signals,
        "grounding_verification": grounding,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    kb = os.path.getsize(OUTPUT_FILE) / 1024

    # Report
    print(f"\n{'='*55}")
    print(f"  ANALYSIS REPORT ({issues_source})")
    print(f"{'='*55}")
    print(f"  Output:  {OUTPUT_FILE} ({kb:.1f} KB)")
    print(f"  Issues:  {len(issues)}")
    for iss in issues:
        rids = len(iss.get("review_ids", []))
        print(f"    [{iss['severity']:8s}] {iss['title'][:50]:50s} ({rids} reviews)")

    print(f"\n  Statistics:")
    print(f"    Monthly trend: {len(stats['monthly_timeline'])} months")
    recent = stats['monthly_timeline'][-1] if stats['monthly_timeline'] else {}
    if recent:
        print(f"    Latest month: {recent['year_month']} — "
              f"{recent['neg_count']}/{recent['total']} negative ({recent['neg_ratio']*100:.0f}%)")

    for v, s in stats.get("version_breakdown", {}).items():
        print(f"    {v}: {s['total']} reviews, "
              f"{s['neg_ratio']*100:.0f}% negative, avg={s['avg_rating']}")

    if grounding:
        high = sum(1 for g in grounding if g["confidence"] == "high")
        print(f"\n  Grounding: {high}/{len(grounding)} issues high confidence")

    print(f"\n  Done.")


if __name__ == "__main__":
    main()
