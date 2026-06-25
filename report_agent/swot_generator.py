"""SWOT Generate Agent。

SWOT 是报告里的战略判断层。本节点只基于已有 EvidenceCard、PMInsight 和
competitor画像Generate结论，每条 SWOT 都Must绑定 evidence_ids。
"""

from __future__ import annotations

OUTPUT_LANGUAGE = "English"

import json
from typing import Any, Dict, List

try:
    from .batch_runner import run_parallel_batches
    from .chunking import chunk_evidence_cards, evidence_prompt_payload
    from .llm_utils import call_json_llm, clamp_confidence, clean_text, valid_ids
    from .models import (
        EvidenceCard,
        PMInsight,
        SWOTItem,
        SWOTResult,
        WritingAgentConfig,
    )
except ImportError:
    from report_agent.batch_runner import run_parallel_batches
    from report_agent.chunking import chunk_evidence_cards, evidence_prompt_payload
    from report_agent.llm_utils import (
        call_json_llm,
        clamp_confidence,
        clean_text,
        valid_ids,
    )
    from report_agent.models import (
        EvidenceCard,
        PMInsight,
        SWOTItem,
        SWOTResult,
        WritingAgentConfig,
    )


def generate_swot(
    evidence_cards: List[EvidenceCard],
    pm_insights: List[PMInsight],
    competitor_profiles: List[Dict[str, Any]],
    config: WritingAgentConfig,
) -> SWOTResult:
    """Generateevidence驱动的 SWOT。"""

    if not evidence_cards:
        return SWOTResult()

    swot = _swot_from_llm(evidence_cards, pm_insights, competitor_profiles, config)
    if _has_any_swot(swot):
        return swot
    return _fallback_swot(evidence_cards, pm_insights)


def _swot_from_llm(
    evidence_cards: List[EvidenceCard],
    pm_insights: List[PMInsight],
    competitor_profiles: List[Dict[str, Any]],
    config: WritingAgentConfig,
) -> SWOTResult:
    """使用 LLM Generate SWOT，并过滤没有evidence绑定的条目。"""

    chunks = chunk_evidence_cards(evidence_cards)
    if len(chunks) > 1:
        result = SWOTResult()
        batch_results = run_parallel_batches(
            label="SWOT",
            batches=chunks,
            config=config,
            worker=lambda cards: _swot_from_llm(
                cards,
                _insights_for_cards(pm_insights, cards),
                competitor_profiles,
                config,
            ),
        )
        for partial in batch_results:
            result.strengths.extend(partial.strengths)
            result.weaknesses.extend(partial.weaknesses)
            result.opportunities.extend(partial.opportunities)
            result.threats.extend(partial.threats)
        return result

    data = call_json_llm(
        config=config,
        system_prompt="你是产品战略Analyze师，只Output JSON。",
        user_prompt=f"""
Evidence Cards:
{json.dumps(evidence_prompt_payload(evidence_cards), ensure_ascii=False, indent=2)}

PM Insights:
{json.dumps([insight.to_dict() for insight in pm_insights], ensure_ascii=False, indent=2)}

Competitor Profiles:
{json.dumps(competitor_profiles, ensure_ascii=False, indent=2)}

请Generateevidence驱动的 SWOT。规则:
- Strength / Weakness 是competitor内部因素。
- Opportunity / Threat 是外部环境因素。
- 我方产品parameters词库或已知产品parameters词库应作为识别 Strength/Weakness 的重要参照：它来自user自己的产品/我方产品，不是competitor事实；某competitor在共同parameters点上evidence充分可形成优势，缺evidence或明显不足可形成弱点。
- questionnaireAnalyze应作为 Opportunity/Threat 的重要参照：user价格敏感、替换意愿、采购顾虑、risk偏好、场景优先级都可以影响机会和威胁判断。
- questionnaireAnalyze不能直接证明某个competitor具备官方能力，只能noteuser侧brief、偏好和顾虑。
- 每条Must绑定 evidence_ids，且Must来自输入。
- Do notGenerate无evidence判断。

返回严格 JSON:
{{
  "swot": {{
    "strengths": [],
    "weaknesses": [],
    "opportunities": [],
    "threats": []
  }}
}}
Each item 字段为 point, why_it_matters, evidence_ids, pm_implication, confidence。
""".strip(),
    )
    if not isinstance(data, dict):
        return SWOTResult()
    raw_swot = data.get("swot", data)
    if not isinstance(raw_swot, dict):
        return SWOTResult()

    allowed = {card.evidence_id for card in evidence_cards}
    return SWOTResult(
        strengths=_parse_swot_items(raw_swot.get("strengths"), allowed),
        weaknesses=_parse_swot_items(raw_swot.get("weaknesses"), allowed),
        opportunities=_parse_swot_items(raw_swot.get("opportunities"), allowed),
        threats=_parse_swot_items(raw_swot.get("threats"), allowed),
    )


def _parse_swot_items(raw_items: Any, allowed_ids: set[str]) -> List[SWOTItem]:
    """解析并校验 SWOT item。

    关键校验是 evidence_ids Must来自当前 evidence 集合，避免报告出现不可检测
    的战略判断。
    """

    if not isinstance(raw_items, list):
        return []
    items: List[SWOTItem] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        evidence_ids = valid_ids(raw.get("evidence_ids"), allowed_ids)
        if not evidence_ids:
            continue
        point = clean_text(raw.get("point"), 180)
        why = clean_text(raw.get("why_it_matters"), 300)
        implication = clean_text(raw.get("pm_implication"), 300)
        if not point or not why:
            continue
        items.append(
            SWOTItem(
                point=point,
                why_it_matters=why,
                evidence_ids=evidence_ids,
                pm_implication=implication or "需要把该判断转化为产品路线优先级。",
                confidence=clamp_confidence(raw.get("confidence"), 0.75),
            )
        )
    return items


def _insights_for_cards(
    pm_insights: List[PMInsight], evidence_cards: List[EvidenceCard]
) -> List[PMInsight]:
    allowed = {card.evidence_id for card in evidence_cards}
    return [
        insight
        for insight in pm_insights
        if any(evidence_id in allowed for evidence_id in insight.evidence_ids)
    ]


def _fallback_swot(
    evidence_cards: List[EvidenceCard],
    pm_insights: List[PMInsight],
) -> SWOTResult:
    """离线 SWOT。

    按维度把evidence映射到 SWOT 四象限，保证 offline 流程有完整结构输出。
    """

    del pm_insights
    return SWOTResult(
        strengths=[
            _make_item(
                "Strength",
                _pick_cards(
                    evidence_cards,
                    ["agent_capability", "task_completion", "integration"],
                ),
            )
        ],
        weaknesses=[
            _make_item(
                "Weakness",
                _pick_cards(evidence_cards, ["experience", "user_feedback"]),
            )
        ],
        opportunities=[
            _make_item(
                "Opportunity",
                _pick_cards(evidence_cards, ["user_and_scenario", "pricing_and_gtm"]),
            )
        ],
        threats=[
            _make_item(
                "Threat",
                _pick_cards(
                    evidence_cards, ["moat", "trust_and_control", "pricing_and_gtm"]
                ),
            )
        ],
    )


def _pick_cards(
    evidence_cards: List[EvidenceCard], dimensions: List[str]
) -> List[EvidenceCard]:
    picked = [card for card in evidence_cards if card.dimension in dimensions]
    if picked:
        return picked[:3]
    return evidence_cards[:2]


def _make_item(kind: str, cards: List[EvidenceCard]) -> SWOTItem:
    evidence_ids = [card.evidence_id for card in cards]
    avg_confidence = (
        sum(card.confidence for card in cards) / len(cards) if cards else 0.5
    )
    lead_claim = cards[0].claim if cards else "当前资料有限，需要补充evidence。"
    if kind == "Strength":
        return SWOTItem(
            point="competitor在已披露能力上具备可感知优势",
            why_it_matters=clean_text(lead_claim, 220),
            evidence_ids=evidence_ids,
            pm_implication="我们需要把competitor强项拆成可测试能力，并明确自身差异化位置。",
            confidence=round(avg_confidence, 2),
        )
    if kind == "Weakness":
        return SWOTItem(
            point="现有资料暴露出体验或user反馈层面的改进空间",
            why_it_matters=clean_text(lead_claim, 220),
            evidence_ids=evidence_ids,
            pm_implication="优先寻找user配置、信任、结果采纳上的低成本突破点。",
            confidence=round(avg_confidence, 2),
        )
    if kind == "Opportunity":
        return SWOTItem(
            point="市场仍存在围绕高频场景做深的机会",
            why_it_matters=clean_text(lead_claim, 220),
            evidence_ids=evidence_ids,
            pm_implication="Do not泛化做通用 Agent，先用场景闭环证明业务价值。",
            confidence=round(avg_confidence, 2),
        )
    return SWOTItem(
        point="外部竞争会快速压缩同质化功能空间",
        why_it_matters=clean_text(lead_claim, 220),
        evidence_ids=evidence_ids,
        pm_implication="需要用可信控制、集成深度和评测数据形成防御。",
        confidence=round(avg_confidence, 2),
    )


def _has_any_swot(swot: SWOTResult) -> bool:
    return bool(swot.strengths or swot.weaknesses or swot.opportunities or swot.threats)
