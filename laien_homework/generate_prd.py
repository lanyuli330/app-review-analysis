"""
Step 4: LangChain Agent — PRD & Version Plan Generator
=========================================================
使用 LangChain Agent 基于分析结果生成 PRD + 多版本计划。
Agent 工具: read_analysis() → 读取 analysis_result.json
           save_prd() → 保存生成的 PRD

用法:
  python generate_prd.py                               # 仅导出 prompt
  python generate_prd.py --llm deepseek --api-key sk-xxx  # DeepSeek V4
  python generate_prd.py --llm openai --api-key sk-xxx     # OpenAI
  python generate_prd.py --llm ollama                       # Ollama
"""

import json
import os
import sys
from datetime import datetime

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
ANALYSIS_FILE = os.path.join(PROJECT_DIR, "analysis_result.json")
OUTPUT_FILE = os.path.join(PROJECT_DIR, "prd_version_plan.json")
PROMPT_FILE = os.path.join(PROJECT_DIR, "prd_prompt.txt")


# ============================================================
# Agent 工具函数
# ============================================================

def tool_read_analysis() -> str:
    """[Tool] 读取分析结果, 返回 issues + statistics + keywords"""
    if not os.path.exists(ANALYSIS_FILE):
        return json.dumps({"error": f"Analysis file not found: {ANALYSIS_FILE}"})
    with open(ANALYSIS_FILE, "r", encoding="utf-8") as f:
        analysis = json.load(f)
    # 提取 agent 需要的关键信息
    return json.dumps({
        "statistics": analysis.get("statistics", {}),
        "issues": analysis.get("issues", []),
        "keywords": analysis.get("keywords", {}),
        "positive_signals": analysis.get("positive_signals", ""),
    }, ensure_ascii=False, indent=2)


def tool_save_prd(prd_json: dict) -> str:
    """[Tool] 保存 PRD 到 JSON 文件"""
    prd_json["metadata"] = {
        "step": 4, "stage": "PRD & Version Plan",
        "generated_at": datetime.now().isoformat(),
        "source": os.path.basename(ANALYSIS_FILE),
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(prd_json, f, ensure_ascii=False, indent=2)
    kb = os.path.getsize(OUTPUT_FILE) / 1024
    return f"PRD saved to {OUTPUT_FILE} ({kb:.1f} KB)"


# ============================================================
# Agent System Prompt (通用)
# ============================================================

AGENT_SYSTEM_PROMPT = """You are a Senior Product Manager with 10 years of mobile app growth experience.
Your specialty: turning user complaints into actionable, measurable product requirements
that balance user trust with business sustainability.

**Language: Write ALL output in Chinese (Simplified Chinese). Field names (keys) stay in English, but ALL text values — titles, descriptions, user stories, implementation plans, summaries — must be in Chinese.**

## Task

Based on App Store review analysis data, create a comprehensive PRD.
The PRD must feel like a real product document — data-driven, specific, traceable.

## Workflow

1. Call `read_analysis()` to get: statistics (rating trend, version breakdown), issues (with review IDs)
2. For EACH issue:
   a. Read the rating trend — is it getting worse? Which version is worse?
   b. Read the review quotes carefully — identify the SPECIFIC user pain points (not just "paywall bad")
   c. Perform ROOT CAUSE ANALYSIS — WHY are users complaining?
   d. Write a SPECIFIC, ACTIONABLE solution — do NOT write vague fixes like "improve UX"
3. Group issues into 2-3 version plans by severity
4. Call `save_prd(prd_json)` with the complete PRD

## Root Cause Analysis (CRITICAL)

For EACH issue, you MUST answer these questions in your solution:
- What EXACTLY are users experiencing? (cite specific review quotes)
- Is this a TRUST problem or a PRICE problem? (they are different)
- If a subscription/paywall complaint: is the user angry about paying at all, or about HOW they were charged?
- What would make the user say "this is fair" instead of "I feel cheated"?

## Version Splitting Logic

- **vNext (P0 — Must Fix)**: ALL `critical` severity issues. These cause the MOST 1-star ratings. Fix first.
  CRITICAL RULE: If a critical issue has >30 affected reviews, you MUST split it into 2-3 INDEPENDENT,
  SPECIFIC sub-requirements. Each sub-requirement targets ONE distinct pain point.
  Example: "Subscription Paywall (76 reviews)" is NOT acceptable as one requirement.
  Correct split → "Fix trial period" + "Add in-app subscription management" + "Free tier with ads"
  Each sub-requirement must reference THE SAME source issue but target DIFFERENT user complaints.

- **vNext+1 (P1 — Should Fix)**: ALL `high` issues + the most impactful `medium` issues.
  These improve retention and experience after critical fires are out.

- **vNext+2 (P2 — Optional)**: Remaining `medium` and `low` issues. Skip if empty.

## Business Constraints (MUST FOLLOW)

1. **DO NOT** suggest removing all monetization — that bankrupts the company
2. **DO** suggest: clearer trial terms, grace periods, in-app subscription management, 
   free content tier with ads, flexible pricing (monthly/quarterly/annual), first-time discounts,
   transparent pricing display, payment confirmation flows
3. **DO** distinguish "HOW they were charged" vs "they don't want to pay" — these require completely different solutions
4. **DO** use positive keywords from the analysis to identify features that MUST NOT be broken

## How to Write a Good Requirement

Each requirement must have ALL of these:

1. **Implementation Plan**: A step-by-step HOW to build the solution (not just WHAT to build).
   For example: "1. Add a subscription management screen in Settings. 2. Display current plan, next billing date, amount. 3. Add Cancel and Restore buttons. 4. Show confirmation dialog before cancelling."

2. **Concrete Acceptance Criteria**: Specific, testable criteria. NOT "it should work". 
   For example: "New user activates 7-day trial → no charge on Apple bill for 7 days."
   "Cancel button is reachable in 3 taps or fewer from home screen."

3. **Verification Method**: HOW will we know the fix worked? Reference future review data.
   For example: "30 days after release, 0 new 1-star reviews contain 'charged after 1 day' or 'charged immediately'."
   "App Store refund rate drops by 50% within 60 days."

4. **Business Impact**: Honest assessment. "Neutral — compliance fix, no revenue impact." 
   "Short-term: may reduce direct conversion by 10%. Long-term: DAU increase compensates via ad revenue."
   Do NOT lie — if a change loses money, say so.

5. **Source Review IDs**: Copy the EXACT `review_ids` from the analysis `issues` array.
   These prove the requirement is grounded in real user feedback.

6. **Source Quotes**: Copy the EXACT `representative_quotes` from the analysis.
   NEVER paraphrase — use the exact text.

## Output JSON Structure

Call `save_prd()` with this exact JSON:

```json
{
  "app_context": {
    "inferred_name": "App name",
    "inferred_category": "e.g. Fitness, Education, Finance",
    "inferred_business_model": "e.g. Subscription (Freemium), One-time Purchase",
    "inferred_target_users": "From review language patterns"
  },
  "version_plan": [
    {
      "version": "vNext",
      "codename": "Trust & Transparency",
      "priority": "P0",
      "timeline": "2-3 weeks",
      "objective": "Fix critical trust and payment issues affecting N reviews",
      "rationale": "Why THIS version contains THESE items specifically",
      "success_metrics": {
        "target_rating": "4.0+",
        "target_negative_ratio": "<15%",
        "key_metric": "e.g. 0 new complaints about 'charged after 1 day' within 30 days"
      },
      "requirements": [
        {
          "id": "REQ-001",
          "title": "Clear, specific title",
          "user_story": "As a [user type], I want [capability] so that [outcome]",
          "priority": "P0",
          "category": "monetization_fix|compliance|ux_fix|feature|content|performance|bug",
          "source_issue": "ISSUE-001",
          "source_review_ids": ["actual_id_1", "actual_id_2"],
          "source_quotes": ["exact excerpt from the analysis data"],
          "implementation_plan": [
            "Step 1: ...",
            "Step 2: ..."
          ],
          "acceptance_criteria": [
            "Specific criterion 1",
            "Specific criterion 2"
          ],
          "verification_method": "How to verify using future reviews",
          "effort_estimate": "S|M|L|XL",
          "business_impact": "Honest revenue/retention assessment"
        }
      ]
    }
  ],
  "executive_summary": {
    "data_summary": "Total reviews, avg rating, neg ratio, version trends",
    "root_cause_analysis": "For each major issue: WHY are users dissatisfied? What is the common thread?",
    "recommended_strategy": "What to fix first, second, third — and WHY in that order",
    "do_not_break": "What users love — features and qualities to preserve",
    "risk_of_inaction": "What happens if we ignore these issues"
  }
}
```

## Critical Rules

1. Every `source_review_ids` MUST be REAL IDs from the analysis data → NO fabrication
2. Every `source_quotes` MUST be EXACT excerpts from `representative_quotes` in the analysis → NO paraphrasing
3. Cover ALL issues from the analysis → no issue left unaddressed
4. Critical issues with >30 reviews → 2-3 sub-requirements (each targets a distinct pain point)
5. `implementation_plan` must be a step-by-step HOW TO BUILD list → not just "what to build"
6. `business_impact` must honestly describe effects → do NOT claim revenue gain if it costs money
7. `verification_method` must describe how to check using FUTURE review data
"""


# ============================================================
# LangChain Agent
# ============================================================

def run_langchain_agent(llm_mode, api_key=None, ollama_model="llama3.1"):
    from langchain_core.tools import tool as lc_tool
    from langchain.agents import create_tool_calling_agent, AgentExecutor
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

    @lc_tool
    def read_analysis() -> str:
        """Read the review analysis results: issues, statistics, keywords, and monthly trends."""
        return tool_read_analysis()

    @lc_tool
    def save_prd(prd_json: str) -> str:
        """Save the generated PRD as a JSON string. Input must match the required schema."""
        data = json.loads(prd_json)
        return tool_save_prd(data)

    tools = [read_analysis, save_prd]

    # 创建 LLM
    if llm_mode == "deepseek":
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(
            model="deepseek-chat",
            openai_api_key=api_key,
            openai_api_base="https://api.deepseek.com/v1",
            temperature=0.3, max_tokens=8192,
        )
    elif llm_mode == "openai":
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(model="gpt-4o-mini", openai_api_key=api_key, temperature=0.3)
    elif llm_mode == "ollama":
        from langchain_ollama import ChatOllama
        llm = ChatOllama(model=ollama_model, temperature=0.3)
    else:
        raise ValueError(f"Unknown LLM mode: {llm_mode}")

    prompt = ChatPromptTemplate.from_messages([
        ("system", AGENT_SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="chat_history", optional=True),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])

    agent = create_tool_calling_agent(llm, tools, prompt)
    executor = AgentExecutor(
        agent=agent, tools=tools, verbose=True,
        handle_parsing_errors=True, max_iterations=15,
    )

    task = (
        "Generate a versioned PRD. "
        "1) Call read_analysis() to get all issues, statistics, and keywords. "
        "2) Create version plans: vNext(P0/critical) + vNext+1(P1/high+medium). "
        "If any critical issue has >30 reviews, split it into multiple specific requirements. "
        "3) Call save_prd() with the complete JSON. "
        "Make sure every requirement references REAL review IDs and quotes from the analysis."
    )

    result = executor.invoke({"input": task})
    return result["output"]


# ============================================================
def rule_based_prd():
    """无 LLM 时的规则版本 — 始终可用, 始终产出 prd_version_plan.json"""
    analysis = json.load(open(ANALYSIS_FILE, "r", encoding="utf-8"))
    issues = sorted(analysis.get("issues", []), key=lambda x: len(x.get("review_ids", [])), reverse=True)
    stats = analysis.get("statistics", {})

    vnext_reqs, vnext1_reqs = [], []
    for iss in issues:
        rids = iss.get("review_ids", [])[:5]
        quotes = iss.get("representative_quotes", [])[:2]
        title_cn = iss["title"]  # Already Chinese from analyze_reviews
        if iss["severity"] in ("critical", "high"):
            vnext_reqs.append({"id": f"REQ-{len(vnext_reqs)+1:03d}", "title": f"修复: {title_cn}",
                "user_story": f"作为用户，我希望 {title_cn} 得到修复",
                "priority": "P0", "category": iss.get("category","other"),
                "source_issue": iss.get("id",""), "source_review_ids": rids,
                "source_quotes": quotes, "acceptance_criteria": ["30天内无此类新投诉"],
                "effort_estimate": "M", "business_impact": "提升用户信任与留存"})
        else:
            vnext1_reqs.append({"id": f"REQ-{len(vnext_reqs)+len(vnext1_reqs)+1:03d}", "title": f"优化: {title_cn}",
                "user_story": f"作为用户，我希望 {title_cn} 得到改善",
                "priority": "P2", "category": iss.get("category","other"),
                "source_issue": iss.get("id",""), "source_review_ids": rids,
                "source_quotes": quotes, "acceptance_criteria": ["30天内无此类新投诉"],
                "effort_estimate": "S", "business_impact": "用户体验提升"})

    prd = {
        "app_context": {"inferred_name": "移动应用", "inferred_category": "通用", "inferred_business_model": "Freemium"},
        "version_plan": [
            {"version": "vNext", "codename": "信任与透明", "priority": "P0",
             "objective": f"修复 {len(vnext_reqs)} 个关键问题", "requirements": vnext_reqs},
            {"version": "vNext+1", "codename": "体验打磨", "priority": "P1",
             "objective": f"改善 {len(vnext1_reqs)} 个体验问题", "requirements": vnext1_reqs},
        ],
        "executive_summary": {"situation": f"{stats.get('total_reviews','?')} 条评价，均分 {stats.get('rating_avg','?')}",
                              "recommended_strategy": "vNext: 修复关键信任问题；vNext+1: 体验优化"},
        "_generation_method": "rule-based",
    }
    tool_save_prd(prd)
    print(f"  Saved {sum(len(vp.get('requirements',[])) for vp in prd['version_plan'])} requirements across {len(prd['version_plan'])} versions")
    return prd


def main():
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

    print("=" * 60)
    print("  Step 4: LangChain Agent — PRD Generator")
    print(f"  Mode: {'LLM-' + llm_mode if llm_mode else 'prompt-only'}")
    print("=" * 60)

    if not os.path.exists(ANALYSIS_FILE):
        print(f"\n  ERROR: {ANALYSIS_FILE} not found. Run analyze_reviews.py first.")
        return

    # 导出 prompt
    with open(PROMPT_FILE, "w", encoding="utf-8") as f:
        f.write(AGENT_SYSTEM_PROMPT)
    print(f"\n  Agent prompt: {PROMPT_FILE}")

    if not llm_mode:
        print("\n  [Rule-based fallback] Generating PRD from analysis...")
        rule_based_prd()
        return

    print(f"\n  Running LangChain Agent ({llm_mode})...")
    try:
        output = run_langchain_agent(llm_mode, api_key, ollama_model)
        print(f"\n  Agent: {output[:300]}")
    except Exception as e:
        print(f"\n  Agent failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
