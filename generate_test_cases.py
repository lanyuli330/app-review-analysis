"""
Step 5: LangChain Agent — Test Case Generator
================================================
基于 PRD (prd_version_plan.json) 自动生成测试用例。
每个测试用例可追溯到源用户评价。

Agent 工具:
  1. read_prd()           — 读取 PRD 文件和所有需求
  2. lookup_reviews(ids)  — 根据 review_id 批量查询原始评价内容
  3. save_test_cases(json) — 保存生成的测试用例

用法:
  python generate_test_cases.py                               # 导出 prompt
  python generate_test_cases.py --llm deepseek --api-key sk-xxx  # 运行 Agent
  python generate_test_cases.py --llm ollama                    # 本地 Ollama
"""

import json
import os
import sys
from datetime import datetime
from typing import List

# ============================================================
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
PRD_FILE = os.path.join(PROJECT_DIR, "prd_version_plan.json")
REVIEWS_FILE = os.path.join(PROJECT_DIR, "reviews_clean.json")
OUTPUT_FILE = os.path.join(PROJECT_DIR, "test_cases.json")
PROMPT_FILE = os.path.join(PROJECT_DIR, "test_cases_prompt.txt")


# ============================================================
# LangChain Tools
# ============================================================

def _load_reviews_index():
    """加载评价索引: review_id → review"""
    with open(REVIEWS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {r["id"]: r for r in data["reviews"]}


def tool_read_prd() -> dict:
    """[Tool] 读取 PRD 文件, 返回所有版本计划和需求"""
    if not os.path.exists(PRD_FILE):
        return {"error": f"PRD file not found: {PRD_FILE}. Run generate_prd.py first."}
    with open(PRD_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def tool_lookup_reviews(review_ids: List[str]) -> list:
    """[Tool] 根据 review_id 列表批量查询原始评价内容, 返回带引用的评价数据"""
    index = _load_reviews_index()
    results = []
    for rid in review_ids:
        if rid in index:
            r = index[rid]
            results.append({
                "review_id": rid,
                "rating": r["rating"],
                "user_name": r["user_name"],
                "title": r["title"],
                "content": r["content"],
                "version": r["version"],
                "updated": r["updated"][:10],
            })
        else:
            results.append({"review_id": rid, "error": "not found"})
    return results


def tool_save_test_cases(test_cases_json: dict) -> str:
    """[Tool] 保存测试用例到 JSON 文件"""
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(test_cases_json, f, ensure_ascii=False, indent=2)
    kb = os.path.getsize(OUTPUT_FILE) / 1024
    return f"Saved {len(test_cases_json.get('test_cases', []))} test cases to {OUTPUT_FILE} ({kb:.1f} KB)"


# ============================================================
# Agent Prompt (通用)
# ============================================================

AGENT_SYSTEM_PROMPT = """You are a Senior QA Engineer with 8 years of mobile app testing experience.
Your specialty: designing test cases that verify a specific user complaint has been resolved,
with full traceability back to the original App Store review.

**Language: Write ALL output in Chinese (Simplified Chinese). Field names (keys) stay in English, but ALL text values — titles, preconditions, test steps, expected results, verifications — must be in Chinese.**

## Task

Read a PRD with requirements, look up the actual user reviews behind each requirement,
then design detailed, executable test cases. Each test case must be traceable to 
specific user complaints.

## Workflow

1. Call `read_prd()` to get all version plans and requirements with their `source_review_ids`
2. For EACH requirement:
   a. Call `lookup_reviews(ids)` with that requirement's `source_review_ids`
   b. READ the actual review content — UNDERSTAND what the user experienced
   c. Design test cases that VERIFY the requirement fixes THAT SPECIFIC user problem
   d. Include the exact review quotes in the test case for traceability
3. After designing all test cases, call `save_test_cases(json)` to save

## How to Design Each Test Case

For each requirement, generate 1-3 test cases (P0→3, P1→2, P2→1). Each test case must:

1. **Target a specific user complaint from the reviews**: 
   Read the quotes from `lookup_reviews()`. If a user said "was charged $29.99 immediately after accepting free trial",
   your test case MUST verify that "user accepts 7-day trial and is NOT charged for 7 days".
   Do NOT write generic tests like "verify trial works" — be SPECIFIC.

2. **Write REALISTIC test steps**:
   Write steps that a junior QA can execute without guessing. Include:
   - `preconditions`: What state must the device/app be in before testing?
   - `step-by-step`: Tap this → see that → enter this → verify that
   - `expected_result`: What the QA should observe at the END
   For example, NOT "Step 1: Test payment". Instead:
   "Step 1: Fresh install app → Step 2: Complete onboarding → Step 3: Tap 'Start Free Trial'
   → Step 4: Authenticate with Face ID → Step 5: Verify Apple Pay sheet shows '$0.00 for 7 days'"

3. **Include source evidence**:
   - `source_review_ids`: The exact IDs from the PRD requirement
   - `source_quotes`: The exact user quotes from `lookup_reviews()` that this TC addresses
   - This proves the TC is not invented — it directly addresses a real complaint

4. **Define verification**:
   How do we CONFIRM the fix worked? NOT "check if it works".
   Example: "Check App Store Connect → no refund request for trial-related charge within 30 days."
   "After vNext release, search new reviews for 'charged after 1 day' → count must be 0."

## Prioritization

- P0 requirements → 2-3 test cases (critical, must be thorough)
- P1 requirements → 1-2 test cases
- P2 requirements → 1 test case

## Test Case Categories

Choose the right category for each TC:
- `functional`: Verifying a feature works correctly (happy path)
- `regression`: Verifying a previously broken scenario is now fixed (based on user complaint)
- `edge_case`: Testing boundary conditions (what if trial expired? what if payment fails?)
- `compliance`: Verifying platform policy requirements (e.g. Apple Guideline 3.1.2)

## Output: Call save_test_cases with this JSON

```json
{
  "metadata": {
    "title": "Test Cases for [App Name] — vNext + vNext+1",
    "source_prd": "prd_version_plan.json",
    "generated_at": "ISO datetime",
    "total_test_cases": 0
  },
  "test_cases": [
    {
      "id": "TC-001",
      "requirement_id": "REQ-001",
      "title": "Verify: 7-day free trial does not charge before day 8",
      "priority": "P0",
      "category": "regression",
      "preconditions": [
        "iPhone with iOS 16+",
        "App fresh installed (not previously subscribed)",
        "Valid Apple ID with payment method",
        "Logged out of any existing subscriptions"
      ],
      "test_steps": [
        {"step": 1, "action": "Launch app → complete onboarding (gender, goals, fitness level)", "expected": "Onboarding completes without paywall"},
        {"step": 2, "action": "Tap 'Start Free Trial' button", "expected": "Apple Pay subscription sheet appears showing '$0.00 for 7 days, then $29.99/year'"},
        {"step": 3, "action": "Authenticate with Face ID / Touch ID", "expected": "Confirmation: 'Subscription active — free until [date+7]'"},
        {"step": 4, "action": "Check Settings → Apple ID → Subscriptions", "expected": "App listed with status 'Active (Trial)', next billing: [today+7]"},
        {"step": 5, "action": "Wait 1 day, check Apple bill / purchase history", "expected": "No charge appears on day 1-6"}
      ],
      "expected_result": "User is NOT charged during the 7-day trial period. First charge occurs on day 8.",
      "source_review_ids": ["14174937162", "14204125134"],
      "source_quotes": [
        "I wanted to try the 1-week free trial, but once I used Apple Pay I was charged $29.99",
        "It made me pay after the first day"
      ],
      "verification": "After release: 0 new 1-star reviews containing 'charged after 1 day' OR 'charged immediately' OR 'made me pay' within 30 days. App Store Connect refund requests for trial-related charges drop to 0."
    }
  ],
  "coverage_summary": {
    "total_requirements_covered": 0,
    "total_source_reviews_referenced": 0,
    "traceability_matrix": {
      "REQ-001": ["TC-001", "TC-002"],
      "REQ-002": ["TC-003"]
    }
  }
}
```

## Critical Rules

1. Every `source_review_ids` must be REAL IDs from `lookup_reviews()` output
2. Every `source_quotes` must be EXACT excerpts from `lookup_reviews()` — NEVER invent
3. Test steps must be specific enough that a JUNIOR QA can execute without asking questions
4. Cover ALL requirements from the PRD — no requirement left untested
5. The `verification` field must describe HOW we KNOW the original user complaint is resolved
6. `preconditions` must describe the EXACT device/app state before testing
7. `category` must be one of: functional, regression, edge_case, compliance
"""


# ============================================================
# LangChain Agent
# ============================================================

def run_langchain_agent(llm_mode, api_key=None, ollama_model="llama3.1"):
    """使用 LangChain Agent 生成测试用例"""
    from langchain_core.tools import tool as lc_tool
    from langchain.agents import create_tool_calling_agent, AgentExecutor
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

    # 注册工具
    @lc_tool
    def read_prd() -> str:
        """Read the PRD file to get all version plans and requirements with their source review IDs."""
        result = tool_read_prd()
        if isinstance(result, dict) and "error" in result:
            return result["error"]
        # 提取关键信息: 版本计划 + 需求 + source_review_ids
        summary = {
            "app_context": result.get("app_context", {}),
            "executive_summary": result.get("executive_summary", {}),
            "version_plan": []
        }
        for vp in result.get("version_plan", []):
            vp_summary = {
                "version": vp["version"],
                "priority": vp["priority"],
                "objective": vp.get("objective", ""),
                "requirements": []
            }
            for req in vp.get("requirements", []):
                vp_summary["requirements"].append({
                    "id": req["id"],
                    "title": req["title"],
                    "priority": req.get("priority", ""),
                    "user_story": req.get("user_story", ""),
                    "acceptance_criteria": req.get("acceptance_criteria", []),
                    "category": req.get("category", ""),
                    "source_review_ids": req.get("source_review_ids", []),
                    "source_quotes": req.get("source_quotes", []),
                })
            summary["version_plan"].append(vp_summary)
        return json.dumps(summary, ensure_ascii=False, indent=2)

    @lc_tool
    def lookup_reviews(review_ids: str) -> str:
        """Look up original review content by a comma-separated list of review IDs. 
        Use this to get the actual user complaints that motivated each requirement."""
        ids = [rid.strip() for rid in review_ids.split(",") if rid.strip()]
        results = tool_lookup_reviews(ids)
        return json.dumps(results, ensure_ascii=False, indent=2)

    @lc_tool
    def save_test_cases(test_cases_json: str) -> str:
        """Save the generated test cases as a JSON string. 
        Input must be valid JSON matching the required schema."""
        data = json.loads(test_cases_json)
        data["metadata"]["generated_at"] = datetime.now().isoformat()
        return tool_save_test_cases(data)

    tools = [read_prd, lookup_reviews, save_test_cases]

    # 创建 LLM
    if llm_mode == "deepseek":
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(
            model="deepseek-chat",
            openai_api_key=api_key,
            openai_api_base="https://api.deepseek.com/v1",
            temperature=0.3,
            max_tokens=8192,
        )
    elif llm_mode == "openai":
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(model="gpt-4o-mini", openai_api_key=api_key, temperature=0.3)
    elif llm_mode == "ollama":
        from langchain_ollama import ChatOllama
        llm = ChatOllama(model=ollama_model, temperature=0.3)
    else:
        raise ValueError(f"Unknown LLM mode: {llm_mode}")

    # 创建 Agent
    prompt = ChatPromptTemplate.from_messages([
        ("system", AGENT_SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="chat_history", optional=True),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])

    agent = create_tool_calling_agent(llm, tools, prompt)
    executor = AgentExecutor(
        agent=agent, tools=tools, verbose=True,
        handle_parsing_errors=True, max_iterations=20,
    )

    task = (
        "Please generate test cases for the PRD. "
        "1) First call read_prd() to get all requirements. "
        "2) For each requirement, call lookup_reviews() with its source_review_ids to see what users actually complained about. "
        "3) Design test cases that verify the requirement fixes those specific user problems. "
        "4) Call save_test_cases() with the complete test case JSON following the required schema. "
        "Make sure every test case references real source_review_ids and uses exact quotes from the reviews."
    )

    result = executor.invoke({"input": task})
    return result["output"]


# ============================================================
def rule_based_test_cases():
    """无 LLM 时的规则版本 — 始终可用, 始终产出 test_cases.json"""
    prd = json.load(open(PRD_FILE, "r", encoding="utf-8"))
    clean = json.load(open(REVIEWS_FILE, "r", encoding="utf-8"))
    id_map = {r["id"]: r for r in clean["reviews"]}

    tcs = []
    for vp in prd.get("version_plan", []):
        for req in vp.get("requirements", []):
            rids = req.get("source_review_ids", [])[:3]
            quotes = req.get("source_quotes", [])[:2]
            if not quotes:
                for rid in rids:
                    if rid in id_map:
                        quotes.append(id_map[rid]["content"][:200])

            tc = {"id": f"TC-{len(tcs)+1:03d}", "requirement_id": req["id"],
                "title": f"验证: {req['title'][:50]}",
                "priority": req.get("priority","P1"), "category": "functional",
                "source_review_ids": rids, "source_quotes": quotes,
                "preconditions": ["App 已安装", "测试账号已就绪"],
                "test_steps": [{"step":1, "action": "按要求执行测试", "expected": "结果符合预期"}],
                "expected_result": "需求得到验证",
                "verification": "30天内无相关差评"}
            tcs.append(tc)
            if req.get("priority") == "P0":
                tcs.append({**tc, "id": f"TC-{len(tcs)+1:03d}", "title": f"边界测试: {req['title'][:50]}"})

    result = {"metadata": {"title": "测试用例", "total_test_cases": len(tcs)}, "test_cases": tcs,
        "coverage_summary": {"total_requirements_covered": sum(len(vp.get("requirements",[])) for vp in prd.get("version_plan",[]))}}
    tool_save_test_cases(result)
    print(f"  Saved {len(tcs)} test cases")


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
    print("  Step 5: LangChain Agent — Test Case Generator")
    print(f"  Mode: {'LLM-' + llm_mode if llm_mode else 'prompt-only'}")
    print("=" * 60)

    # 检查前置文件
    if not os.path.exists(PRD_FILE):
        print(f"\n  ERROR: PRD file not found: {PRD_FILE}")
        print("  Run generate_prd.py first to create the PRD.")
        return
    if not os.path.exists(REVIEWS_FILE):
        print(f"\n  ERROR: Reviews file not found: {REVIEWS_FILE}")
        return

    # 保存 Agent Prompt
    with open(PROMPT_FILE, "w", encoding="utf-8") as f:
        f.write(AGENT_SYSTEM_PROMPT)
    print(f"\n  Agent prompt saved: {PROMPT_FILE}")

    if not llm_mode:
        print("\n  [Rule-based fallback] Generating test cases from PRD...")
        rule_based_test_cases()
        return

    # 运行 Agent
    print(f"\n  Running LangChain Agent ({llm_mode})...")
    try:
        output = run_langchain_agent(llm_mode, api_key, ollama_model)
        print(f"\n  Agent output:\n{output[:500]}...")
    except Exception as e:
        print(f"\n  Agent failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
