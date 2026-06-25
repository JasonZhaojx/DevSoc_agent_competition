"""PM 洞察抽取 Agent。

本节点把 EvidenceCard 转换成产品经理关心的issue：user是谁、场景是什么、
competitor优势/短板在哪里、对我们的路线有什么启发。它不负责写长报告。
"""

from __future__ import annotations

OUTPUT_LANGUAGE = "English"

import json
from collections import defaultdict
from typing import Dict, List

try:
    from .batch_runner import run_parallel_batches
    from .chunking import chunk_evidence_cards, evidence_prompt_payload
    from .llm_utils import call_json_llm, clamp_confidence, clean_text, valid_ids
    from .models import EvidenceCard, PMInsight, WritingAgentConfig
except ImportError:
    from report_agent.batch_runner import run_parallel_batches
    from report_agent.chunking import chunk_evidence_cards, evidence_prompt_payload
    from report_agent.llm_utils import (
        call_json_llm,
        clamp_confidence,
        clean_text,
        valid_ids,
    )
    from report_agent.models import EvidenceCard, PMInsight, WritingAgentConfig


INSIGHT_TYPES = ["user_pain", "product_gap", "differentiation", "risk", "opportunity"]


_DIMENSION_TO_INSIGHT = {
    "user_and_scenario": ("user_pain", "目标user与高频场景需要被优先验证"),
    "task_completion": ("product_gap", "任务闭环能力决定产品可用性"),
    "agent_capability": ("differentiation", "Agent 能力是核心差异化source"),
    "trust_and_control": ("risk", "信任与控制机制是企业落地risk点"),
    "experience": ("opportunity", "低门槛体验是提升激活的机会"),
    "integration": ("differentiation", "系统集成能力影响企业采购价值"),
    "pricing_and_gtm": ("risk", "定价和销售路径会影响增长效率"),
    "moat": ("differentiation", "生态与数据沉淀可能形成长期壁垒"),
    "user_feedback": ("opportunity", "user反馈暴露可切入的未满足brief"),
}


def extract_pm_insights(
    evidence_cards: List[EvidenceCard],
    config: WritingAgentConfig,
    *,
    analysis_goal: str,
    target_domain: str,
) -> List[PMInsight]:
    """从evidence卡抽取结构化 PM 洞察。"""

    if not evidence_cards:
        return []

    insights = _insights_from_llm(
        evidence_cards=evidence_cards,
        config=config,
        analysis_goal=analysis_goal,
        target_domain=target_domain,
    )
    if insights:
        return insights
    return _fallback_pm_insights(evidence_cards)


def _insights_from_llm(
    *,
    evidence_cards: List[EvidenceCard],
    config: WritingAgentConfig,
    analysis_goal: str,
    target_domain: str,
) -> List[PMInsight]:
    """调用 LLM 抽取洞察，并强制校验 evidence_ids。

    只有绑定到现有 evidence_id 的洞察才会进入下游，防止模型Generate无evidence观点。
    """

    chunks = chunk_evidence_cards(evidence_cards)
    if len(chunks) > 1:
        merged: List[PMInsight] = []
        batch_results = run_parallel_batches(
            label="PM insights",
            batches=chunks,
            config=config,
            worker=lambda cards: _insights_from_llm(
                    evidence_cards=cards,
                    config=config,
                    analysis_goal=analysis_goal,
                    target_domain=target_domain,
            ),
        )
        for insights in batch_results:
            merged.extend(insights)
        for index, insight in enumerate(merged, 1):
            insight.insight_id = f"ins_{index:03d}"
        return merged

    payload = evidence_prompt_payload(evidence_cards)
    data = call_json_llm(
        config=config,
        system_prompt="你是资深产品经理，只Output JSON。",
        user_prompt=f"""
Analyze目标:
{analysis_goal}

Analyze领域:
{target_domain}

Evidence Cards:
{json.dumps(payload, ensure_ascii=False, indent=2)}

请提炼产品经理关心的结构化洞察。要求:
- 每条洞察Must绑定 evidence_ids，且 evidence_ids Must来自输入。
- Do not只复述资料，要解释“这意味着什么”：对定位、目标user、功能优先级、商业化、增长、可信任机制或差异化路线有什么启发。
- Ifevidence中包含我方产品parameters词库或已知产品parameters词库，要理解为user自己的产品/我方产品基准parameters，不是competitor事实；围绕这些parameters点提炼“哪些parameters会影响competitor判断、哪些competitor缺evidence、哪些parameters应进入后续验证清单”。
- Ifevidence中包含questionnaireAnalyze，要把它作为userbrief和采购决策背景，提炼user画像、场景优先级、价格敏感度、替换意愿、risk顾虑对产品路线的启发。
- 注意区分competitor事实和questionnaire结论：questionnaire只能支撑user侧/brief侧洞察，不能支撑某个competitor官方能力判断。
- 返回严格 JSON:
{{
  "insights": [
    {{
      "type": "user_pain|product_gap|differentiation|risk|opportunity",
      "title": "洞察标题",
      "description": "洞察note",
      "related_competitors": ["competitor"],
      "evidence_ids": ["ev_001"],
      "pm_value": "对产品经理的价值",
      "confidence": 0.0
    }}
  ]
}}
""".strip(),
    )
    if not isinstance(data, dict):
        return []

    allowed = {card.evidence_id for card in evidence_cards}
    insights: List[PMInsight] = []
    for raw in data.get("insights", []):
        if not isinstance(raw, dict):
            continue
        evidence_ids = valid_ids(raw.get("evidence_ids"), allowed)
        if not evidence_ids:
            continue
        insight_type = str(raw.get("type") or "").strip()
        if insight_type not in INSIGHT_TYPES:
            insight_type = "opportunity"
        title = clean_text(raw.get("title"), 160)
        description = clean_text(raw.get("description"), 360)
        pm_value = clean_text(raw.get("pm_value"), 260)
        if not title or not description:
            continue
        insights.append(
            PMInsight(
                insight_id=f"ins_{len(insights) + 1:03d}",
                type=insight_type,
                title=title,
                description=description,
                related_competitors=_clean_string_list(raw.get("related_competitors")),
                evidence_ids=evidence_ids,
                pm_value=pm_value or "可作为产品路线和优先级判断依据。",
                confidence=clamp_confidence(raw.get("confidence"), 0.74),
            )
        )
    return insights


def _fallback_pm_insights(evidence_cards: List[EvidenceCard]) -> List[PMInsight]:
    """按evidence维度聚合成本地洞察。

    fallback 的目标是流程稳定和结构完整，不替代真实 PM Analyze；真实模式下可由
    LLM 给出更细的洞察。
    """

    grouped: Dict[str, List[EvidenceCard]] = defaultdict(list)
    for card in evidence_cards:
        grouped[card.dimension].append(card)

    insights: List[PMInsight] = []
    for dimension, cards in grouped.items():
        insight_type, title = _DIMENSION_TO_INSIGHT.get(
            dimension,
            ("opportunity", "资料显示存在可进一步验证的产品机会"),
        )
        selected = cards[:4]
        competitors = []
        for card in selected:
            if card.competitor and card.competitor not in competitors:
                competitors.append(card.competitor)
        description = "；".join(card.claim for card in selected[:2])
        confidence = sum(card.confidence for card in selected) / len(selected)
        insights.append(
            PMInsight(
                insight_id=f"ins_{len(insights) + 1:03d}",
                type=insight_type,
                title=title,
                description=description,
                related_competitors=competitors,
                evidence_ids=[card.evidence_id for card in selected],
                pm_value=_pm_value_for_dimension(dimension),
                confidence=round(confidence, 2),
            )
        )
        if len(insights) >= 8:
            break
    return insights


def _pm_value_for_dimension(dimension: str) -> str:
    values = {
        "user_and_scenario": "用于确定优先服务的user画像、场景边界和任务频率。",
        "task_completion": "用于拆解产品Must补齐的任务规划、执行和异常处理能力。",
        "agent_capability": "用于判断核心技术能力投入和差异化方向。",
        "trust_and_control": "用于设计权限、人审、日志和可回滚机制。",
        "experience": "用于优化首次使用、配置向导和结果交付体验。",
        "integration": "用于规划 API、MCP、企业数据源和业务系统连接。",
        "pricing_and_gtm": "用于判断商业模式、套餐和销售路径。",
        "moat": "用于识别长期壁垒和防御strategy。",
        "user_feedback": "用于定位未满足brief和高优先级改进点。",
    }
    return values.get(dimension, "用于支持产品路线优先级判断。")


def _clean_string_list(value) -> List[str]:
    if not isinstance(value, list):
        return []
    results: List[str] = []
    for item in value:
        text = clean_text(item, 80)
        if text and text not in results:
            results.append(text)
    return results
