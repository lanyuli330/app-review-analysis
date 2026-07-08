# 第四步：PRD 与版本规划

**脚本**: `generate_prd.py` | **输入**: `analysis_result.json` | **输出**: `prd_version_plan.json`

---

## 设计思路

核心不是写死一个针对 Workout App 的 PRD，而是**设计一个通用 Prompt**。换任意 App 的 `analysis_result.json`，LLM 都能产出符合以下要求的 PRD:

1. 基于问题严重度自动拆分为 2-3 个版本
2. 每条需求可追溯到具体用户评价
3. 商业化建议平衡体验与收入

---

## Prompt 设计 (核心资产)

Prompt 保存在 `prd_prompt.txt`，运行 `python generate_prd.py` 即可导出用于任何兼容 LLM。

### 结构

| 区块 | 内容 |
|------|------|
| **Task** | 总目标: 基于分析数据生成版本化 PRD |
| **Input** | `{analysis_json}` 占位符, 注入分析数据 |
| **Version Splitting** | vNext=P0(critical) + vNext+1=P1(high+medium) + vNext+2=P2(可选) |
| **Business Constraints** | 不强拆付费墙, 优化信任与透明度 |
| **Output Format** | 完整 JSON schema, 含 source_review_ids 追溯 |
| **Rules** | 7 条硬规则: 不编造 ID, 不编造引用, 覆盖所有问题 |

### 版本拆分逻辑

```
critical (>30 reviews) → 拆为 2-3 个独立 REQ, 每个解决一个具体痛点
critical (≤30)        → 1 REQ
high                   → vNext+1, 1 REQ each
medium                 → vNext+1 或 vNext+2, 1 REQ each
```

### 商业约束

Prompt 明确命令 LLM:
- **不做**: 取消付费墙、移除所有付费功能
- **要做**: 清晰试用条款、app 内订阅管理、免费层+激励广告、灵活定价、首月折扣

---

## 输出结构

```json
{
  "app_context": {
    "inferred_name": "...",
    "inferred_business_model": "..."
  },
  "version_plan": [
    {
      "version": "vNext",
      "codename": "Trust & Transparency",
      "priority": "P0",
      "requirements": [
        {
          "id": "REQ-001",
          "source_issue": "ISSUE-001",
          "source_review_ids": ["id1", "id2"],
          "source_quotes": ["原文"],
          "verification_method": "30天内无此类型1星差评",
          "business_impact": "修复信任不影响收入"
        }
      ]
    }
  ],
  "executive_summary": {
    "root_cause_analysis": "...",
    "recommended_strategy": "...",
    "risk_of_inaction": "..."
  }
}
```

---

## 用法

```bash
# 导出 Prompt (不调 LLM)
python generate_prd.py

# LLM 生成 PRD
python generate_prd.py --llm openai --api-key sk-xxx
python generate_prd.py --llm ollama --ollama-model llama3.1
```

## 通用性验证

换 App 只需三步: 跑 Step 1-3 获取新 `analysis_result.json` → 运行 `python generate_prd.py` 导出新 prompt → 喂给 LLM。Prompt 模板和输出 schema 零改动。

---

*最后更新: 2026-07-07*
