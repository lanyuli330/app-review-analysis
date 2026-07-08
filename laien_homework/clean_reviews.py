"""
Step 2: Review Cleaning Pipeline
==================================
对 reviews_raw.json 执行 7 步清洗:

  1. 内容清洗     — 智能引号→ASCII, 控制字符移除, 空白归一化
  2. ID + 内容去重 — 精确 ID 去重 + 相近内容相似度去重
  3. 质量评分     — 0-1 连续分数 (长度+实质性+投票)
  4. 语言检测     — langdetect
  5. 版本清洗     — 归一化 + major_minor 提取
  6. 衍生字段     — word_count, sentiment, year_month
  7. 输出         — reviews_clean.json + cleaning_report.json

用法:
    python clean_reviews.py
"""

import json
import os
import re
import hashlib
from datetime import datetime
from difflib import SequenceMatcher

try:
    from langdetect import detect as detect_lang
    HAS_LANGDETECT = True
except ImportError:
    HAS_LANGDETECT = False

# ============================================================
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE = os.path.join(PROJECT_DIR, "reviews_raw.json")
OUTPUT_FILE = os.path.join(PROJECT_DIR, "reviews_clean.json")
REPORT_FILE = os.path.join(PROJECT_DIR, "cleaning_report.json")

# 质量评分权重
W_LENGTH = 0.3    # 文本长度贡献
W_SUBSTANCE = 0.4 # 实质性内容贡献
W_VOTES = 0.3     # 有用投票贡献

# 去重相似度阈值
SIM_THRESHOLD = 0.85

# ============================================================
# Step 1: 内容清洗
# ============================================================
def step1_clean_content(records):
    """文本归一化"""
    smart_quotes = {
        "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
        "\u2013": "-", "\u2014": "--", "\u00a0": " ",
    }
    for rec in records:
        text = rec.get("content", "")
        title = rec.get("title", "")
        for smart, ascii in smart_quotes.items():
            text = text.replace(smart, ascii)
            title = title.replace(smart, ascii)
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
        title = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", title)
        text = re.sub(r"\s+", " ", text).strip()
        title = re.sub(r"\s+", " ", title).strip()
        rec["content"] = text
        rec["title"] = title
    return records


# ============================================================
# Step 2: 去重
# ============================================================
def step2_deduplicate(records):
    """ID 精确去重 + 内容相似度去重"""
    # 2a: ID 精确去重
    seen_ids = {}
    for rec in records:
        rid = rec.get("id", "")
        if not rid:
            continue
        if rid not in seen_ids:
            seen_ids[rid] = rec
        else:
            # 保留 content 更长的那条
            if len(rec.get("content", "")) > len(seen_ids[rid].get("content", "")):
                seen_ids[rid] = rec

    result = list(seen_ids.values())
    id_dup = len(records) - len(result)

    # 2b: 内容相似度去重 (同一用户相似内容)
    final = []
    for rec in result:
        content = rec.get("content", "").lower().strip()
        uid = rec.get("user_name", "")
        is_dup = False
        for existing in final:
            if existing.get("user_name") != uid:
                continue
            existing_content = existing.get("content", "").lower().strip()
            if abs(len(content) - len(existing_content)) < 5 and len(content) > 20:
                sim = SequenceMatcher(None, content, existing_content).ratio()
                if sim >= SIM_THRESHOLD:
                    is_dup = True
                    break
        if not is_dup:
            final.append(rec)

    sim_dup = len(result) - len(final)
    print(f"  ID 去重: {len(records)} → {len(result)} (-{id_dup})")
    print(f"  内容去重: {len(result)} → {len(final)} (-{sim_dup})")
    return final


# ============================================================
# Step 3: 质量评分
# ============================================================
def step3_quality_score(records):
    """0-1 连续质量分数 (不删除数据)"""
    all_words = [len(r.get("content", "").split()) for r in records]
    wc_max = max(all_words) if all_words else 1
    all_votes = [r.get("vote_count", 0) for r in records]
    vote_max = max(all_votes) if all_votes and max(all_votes) > 0 else 10

    # 实质性词汇 (用于判断是否有实质内容)
    substance_indicators = re.compile(
        r"\b(bug|crash|freeze|broken|fix|update|subscription|"
        r"pay|money|price|feature|need|want|wish|please|"
        r"workout|exercise|train|gym|weight|calorie|"
        r"love|great|amazing|best|helpful|easy|simple|"
        r"hard|difficult|boring|hate|terrible|worst|"
        r"would|should|could|suggest|recommend)\b",
        re.IGNORECASE
    )

    for rec in records:
        content = rec.get("content", "")
        wc = len(content.split())

        # 长度分数
        if wc < 3:
            len_score = 0
        elif wc < 10:
            len_score = 0.1
        elif wc < 30:
            len_score = 0.2
        else:
            len_score = 0.3

        # 实质性分数
        sub_matches = len(substance_indicators.findall(content))
        sub_score = min(0.4, sub_matches * 0.08)

        # 投票分数
        votes = rec.get("vote_count", 0)
        vote_score = min(0.3, (votes / vote_max) * 0.3)

        rec["quality_score"] = round(len_score + sub_score + vote_score, 2)
        rec["low_info"] = (wc < 10)

    scores = [r["quality_score"] for r in records]
    avg_q = sum(scores) / len(scores) if scores else 0
    print(f"  Quality: avg={avg_q:.2f}, "
          f"high(>0.4)={sum(1 for s in scores if s>0.4)}, "
          f"low(<0.1)={sum(1 for s in scores if s<0.1)}, "
          f"low_info flagged={sum(1 for r in records if r['low_info'])}")
    return records


# ============================================================
# Step 4: 语言检测
# ============================================================
def step4_detect_language(records):
    """langdetect 语言识别"""
    if not HAS_LANGDETECT:
        for rec in records:
            rec["lang"] = "unknown"
        return records

    stats = {}
    for rec in records:
        text = rec.get("content", "") + " " + rec.get("title", "")
        if len(text.strip()) < 5:
            rec["lang"] = "unknown"
            stats["unknown"] = stats.get("unknown", 0) + 1
            continue
        try:
            lang = detect_lang(text)
        except Exception:
            lang = "unknown"
        rec["lang"] = lang
        stats[lang] = stats.get(lang, 0) + 1

    print(f"  Language: {dict(sorted(stats.items(), key=lambda x: -x[1])[:5])}")
    return records


# ============================================================
# Step 5: 版本清洗
# ============================================================
def step5_normalize_version(records):
    """版本号归一化 + major_minor 提取"""
    versions_seen = set()
    for rec in records:
        v = rec.get("version", "").strip()
        rec["version"] = v
        # 提取 major.minor
        match = re.match(r"(\d+\.\d+)", v)
        rec["major_minor"] = match.group(1) if match else v if v else "unknown"
        versions_seen.add(rec["major_minor"])

    print(f"  Version: {len(versions_seen)} major.minor groups")
    return records


# ============================================================
# Step 6: 衍生字段
# ============================================================
def step6_derive_fields(records):
    """word_count, sentiment, year_month, has_dev_response"""
    for rec in records:
        rec["word_count"] = len(rec.get("content", "").split())

        r = rec.get("rating", 0)
        rec["sentiment"] = "positive" if r >= 4 else ("neutral" if r == 3 else "negative")

        updated = rec.get("updated", "")
        rec["year_month"] = updated[:7] if len(updated) >= 7 else "unknown"

        # RSS Feed 不直接提供 developer response，保留字段供后续扩展
        rec["has_developer_response"] = False

    print(f"  Derived: word_count, sentiment, year_month, has_developer_response")
    return records


# ============================================================
# Step 7: 输出
# ============================================================
def step7_output(records, report):
    records.sort(key=lambda r: r.get("updated", ""), reverse=True)

    result = {"metadata": report, "reviews": records}
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    kb = os.path.getsize(OUTPUT_FILE) / 1024
    print(f"\n  Output: {OUTPUT_FILE} ({kb:.1f} KB)")
    print(f"  Report: {REPORT_FILE}")


# ============================================================
def main():
    print("=" * 55)
    print("  Step 2: Review Cleaning Pipeline")
    print("=" * 55)

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        raw = json.load(f)
    records = raw.get("reviews", raw if isinstance(raw, list) else [])
    input_count = len(records)
    print(f"\n  Input: {input_count} reviews from {os.path.basename(INPUT_FILE)}")
    print()

    # Pipeline
    records = step1_clean_content(records)
    records = step2_deduplicate(records)
    records = step3_quality_score(records)
    records = step4_detect_language(records)
    records = step5_normalize_version(records)
    records = step6_derive_fields(records)

    # Build report
    ratings = [r["rating"] for r in records]
    langs = {}
    for r in records:
        l = r.get("lang", "?")
        langs[l] = langs.get(l, 0) + 1
    sents = {}
    for r in records:
        s = r.get("sentiment", "?")
        sents[s] = sents.get(s, 0) + 1
    words = [r["word_count"] for r in records]
    versions = set(r["major_minor"] for r in records)
    quality_scores = [r["quality_score"] for r in records]

    report = {
        "step": 2,
        "stage": "Review Cleaning & Normalization",
        "input_file": os.path.basename(INPUT_FILE),
        "input_count": input_count,
        "output_count": len(records),
        "cleaned_at": datetime.now().isoformat(),
        "pipeline": [
            "1. content_cleaning: smart quotes→ASCII, control chars removed, whitespace normalized",
            "2. deduplication: ID exact + content similarity (>0.85)",
            "3. quality_scoring: 0-1 score (length 0.3 + substance 0.4 + votes 0.3)",
            "4. language_detection: langdetect (unknown for <5 chars)",
            "5. version_normalization: major_minor extraction",
            "6. derived_fields: word_count, sentiment, year_month, has_developer_response",
            "7. output: reviews_clean.json + cleaning_report.json",
        ],
        "rating_distribution": {str(s): ratings.count(s) for s in range(5, 0, -1)},
        "avg_rating": round(sum(ratings) / len(ratings), 2),
        "language_distribution": langs,
        "sentiment_distribution": sents,
        "avg_word_count": round(sum(words) / len(words), 1),
        "word_count_range": [min(words), max(words)],
        "versions": len(versions),
        "quality_score": {
            "avg": round(sum(quality_scores) / len(quality_scores), 2),
            "high_quality": sum(1 for s in quality_scores if s > 0.4),
            "low_quality": sum(1 for s in quality_scores if s < 0.1),
        },
        "low_info_count": sum(1 for r in records if r.get("low_info")),
    }

    step7_output(records, report)

    # Summary
    print(f"\n{'='*55}")
    print(f"  CLEANING SUMMARY")
    print(f"{'='*55}")
    print(f"  Reviews:     {input_count} → {len(records)}")
    print(f"  Rating avg:  {report['avg_rating']}")
    print(f"  Quality avg: {report['quality_score']['avg']}")
    print(f"  High quality: {report['quality_score']['high_quality']} (>0.4)")
    print(f"  Languages:   {dict(sorted(langs.items(), key=lambda x: -x[1]))}")
    print(f"  Sentiment:   pos={sents.get('positive',0)}, "
          f"neu={sents.get('neutral',0)}, neg={sents.get('negative',0)}")
    print(f"  Done.")


if __name__ == "__main__":
    main()
