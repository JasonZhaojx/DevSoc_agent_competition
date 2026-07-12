"""报告撰写 Agent。

Composer 只负责表达，把结构化Analyze渲染为 Markdown。它不重新搜索、不重新推理，
也不新增 evidence/insight/SWOT/recommendation 之外的事实。
"""

from __future__ import annotations

OUTPUT_LANGUAGE = "English"

import json
import re
from typing import Any, Dict, Iterable, List

try:
    from .llm_utils import call_json_llm, clean_text, contains_cjk, rewrite_text_to_english
    from .models import ReportState, SWOTItem, WritingAgentConfig
except ImportError:
    from report_agent.llm_utils import call_json_llm, clean_text, contains_cjk, rewrite_text_to_english
    from report_agent.models import ReportState, SWOTItem, WritingAgentConfig


def compose_report(state: ReportState, config: WritingAgentConfig) -> str:
    """Generate最终 Markdown 报告。"""

    use_llm_composer = getattr(config, "use_llm_report_composer", False)
    if not use_llm_composer:
        return _fallback_report_markdown(state)

    report = _report_from_llm(state, config)
    if report:
        cleaned = _clean_report(report)
        if contains_cjk(cleaned):
            cleaned = rewrite_text_to_english(cleaned, config)
        if not contains_cjk(cleaned) and not _has_invalid_empty_tables(cleaned):
            return cleaned
        if config.verbose and config.progress_printer:
            config.progress_printer(
                "[writing-agent] LLM report contains empty tables, using fallback renderer"
            )
    fallback = _fallback_report_markdown(state)
    if contains_cjk(fallback):
        fallback = rewrite_text_to_english(fallback, config)
    return fallback


def _report_from_llm(state: ReportState, config: WritingAgentConfig) -> str:
    """让 LLM 根据结构化Analyze润色报告。

    这里要求模型返回 JSON，是为了继续用程序校验输出；If返回失败，直接走
    本地 Markdown fallback。
    """

    data = call_json_llm(
        config=config,
        system_prompt="You are an expert competitor-analysis report writer for product managers. Output strict JSON only.",
        user_prompt=f"""
Write the report in English only. Use only the structured analysis below; do not add unsupported facts.

Structured analysis:
{json.dumps(_structured_payload(state), ensure_ascii=False, indent=2)}

Sources:
{json.dumps([source.to_dict() for source in state.sources], ensure_ascii=False, indent=2)}

Return strict JSON:
{{"report_markdown": "Markdown body"}}

The report must contain these English sections:
Executive Summary, Analysis Background and Goal, Competitor Segmentation, User Scenarios, Key Competitor Breakdown, Cross-Competitor Capability Comparison, SWOT, Product Opportunities and Risks, Product Strategy Recommendations, Sources.
Additional requirements:
- If structured analysis includes own-product parameters or known product parameters, include a "Shared Parameter Alignment" perspective. These parameters come from the user's own product, not competitor facts. Note which competitor parameters have evidence, which lack evidence, and which parameters drive product choice.
- If structured analysis includes questionnaire analysis, include a "User and Buyer Calibration" perspective covering user profiles, scenario priorities, price sensitivity, switching intent, purchase concerns, and risk preference.
- Clearly separate competitor factual evidence from questionnaire/user-side evidence. Questionnaire conclusions can support user and decision analysis only; do not present them as official competitor capabilities or promises.
- Do not output empty tables. If a cell has no evidence, write "No explicit evidence found". If an entire table lacks valid data, write "No comparable data available".
""".strip(),
    )
    if isinstance(data, dict):
        report = data.get("report_markdown")
        return "" if report is None else str(report).strip()
    return ""


def _fallback_report_markdown(state: ReportState) -> str:
    """离线 Markdown 报告。

    章节结构固定，确保 smoke test 和下游检测 Agent 能稳定找到核心部分。
    """

    lines: List[str] = [
        f"# {state.target_domain} Competitor Analysis Report",
        "",
        "## Executive Summary",
        _executive_summary(state),
        "",
        "## Analysis Background and Goal",
        f"This report supports: {state.analysis_goal}. The analysis focuses on {state.target_domain} and is generated from upstream search results as a structured, auditable report package.",
        "",
        "## Competitor Segmentation and Selection Rationale",
    ]

    if state.competitor_profiles:
        for profile in state.competitor_profiles:
            lines.append(
                "- {competitor}: {judgement} evidence: {evidence}".format(
                    competitor=_cell(profile.get("competitor", "Unknown competitor")),
                    judgement=_cell(profile.get("strategic_judgement", "Further assessment needed")),
                    evidence=", ".join(profile.get("evidence_ids", []) or ["none"]),
                )
            )
    else:
        lines.append("- The current material does not support clear competitor profiles yet. Additional search results are needed.")

    lines.extend(
        [
            "",
            "## User Scenarios and Task Analysis",
        ]
    )
    if state.pm_insights:
        for insight in state.pm_insights:
            lines.append(
                f"- {insight.title}: {insight.description} Product implication: {insight.pm_value} evidence: {', '.join(insight.evidence_ids)}"
            )
    else:
        lines.append("- The current material is insufficient to form clear user-scenario insights.")

    lines.extend(
        [
            "",
            "## Key Competitor Breakdown",
        ]
    )
    for profile in state.competitor_profiles:
        lines.append(f"### {_cell(profile.get('competitor', 'Unknown competitor'))}")
        lines.append(f"- Target users: {_cell(profile.get('target_user'))}")
        lines.append(f"- Core scenarios: {_cell(profile.get('core_scenario'))}")
        lines.append(f"- Product form: {_cell(profile.get('product_form'))}")
        lines.append(f"- Business model: {_cell(profile.get('business_model'))}")
        lines.append(f"- Strategic assessment: {_cell(profile.get('strategic_judgement'))}")
    if not state.competitor_profiles:
        lines.append("- No competitor profiles are available for breakdown yet.")

    lines.extend(
        [
            "",
            "## Cross-Competitor Capability Comparison",
            _markdown_tables(state.comparison_tables),
            "",
            "## SWOT Analysis",
            _swot_markdown(state),
            "",
            "## Product Opportunities and Risks",
        ]
    )
    opportunities = [item for item in state.swot.opportunities] + [
        item for item in state.swot.weaknesses
    ]
    if opportunities:
        for item in opportunities:
            lines.append(
                f"- {item.point}: {item.pm_implication} evidence: {', '.join(item.evidence_ids)}"
            )
    else:
        lines.append("- The current material is insufficient to define clear opportunities or risks.")

    lines.extend(
        [
            "",
            "## Product Strategy Recommendations",
        ]
    )
    for rec in state.recommendations:
        lines.append(
            f"- [{rec.timeframe}][{rec.priority}] {rec.action}. Rationale: {rec.reason}. Expected impact: {rec.expected_impact}. Risk: {rec.risk}. Success metric: {rec.success_metric}. evidence: {', '.join(rec.evidence_ids)}"
        )
    if not state.recommendations:
        lines.append("- The current material is insufficient to generate strategy recommendations.")

    lines.extend(
        [
            "",
            "## Sources",
        ]
    )
    for source in state.sources:
        lines.append(f"- [{source.source_id}] {source.title} {source.url}".rstrip())

    return "\n".join(lines).strip() + "\n"


def _executive_summary(state: ReportState) -> str:
    parts: List[str] = []
    if state.pm_insights:
        parts.append("; ".join(insight.title for insight in state.pm_insights[:3]))
    if state.recommendations:
        parts.append(f"Priority action: {state.recommendations[0].action}")
    if not parts:
        return "The current material is limited. Add competitor facts and user feedback evidence before making decisions."
    return ". ".join(parts) + "."


def _markdown_tables(tables: List[Dict[str, Any]]) -> str:
    """把结构化 comparison_tables 渲染成 Markdown table。"""

    sections: List[str] = []
    for table in tables:
        name = table.get("table_name", "comparison_table")
        sections.append(f"### {_table_title(name)}")
        if name == "competitor_positioning_matrix":
            rows = table.get("rows", [])
            columns = [
                "competitor",
                "target_user",
                "core_scenario",
                "product_form",
                "main_entry",
                "business_model",
                "strategic_judgement",
                "evidence_ids",
            ]
            sections.append(
                _simple_table_or_empty(
                    _columns_for_rows(rows, columns),
                    rows,
                    header_map=_header_map(),
                )
            )
        elif name == "agent_capability_scorecard":
            rows = table.get("dimensions", [])
            sections.append(_score_table_or_empty(rows))
        elif name == "user_journey_comparison":
            rows = table.get("rows", [])
            columns = [
                "stage",
                "user_goal",
                "competitor_experience",
                "opportunity",
                "evidence_ids",
            ]
            sections.append(
                _simple_table_or_empty(
                    _columns_for_rows(rows, columns),
                    rows,
                    header_map=_header_map(),
                )
            )
        else:
            rows = _clean_table_rows(table.get("rows") or table.get("dimensions") or [])
            columns = table.get("columns")
            if not isinstance(columns, list):
                columns = _columns_for_rows(rows, [])
            else:
                columns = [str(column) for column in columns if str(column) != "pending_search_query"]
            if not columns:
                columns = ["Information Needed", "evidence_ids"]
            if not rows and columns:
                rows = [_pending_row_for_columns(columns, name)]
            sections.append(
                _simple_table_or_empty(
                    [str(column) for column in columns],
                    rows,
                    header_map=_header_map(),
                )
            )
    return "\n\n".join(section for section in sections if section)


def _table_title(name: Any) -> str:
    mapping = {
        "competitor_positioning_matrix": "Competitor Positioning Matrix",
        "agent_capability_scorecard": "Agent Capability Scorecard",
        "user_journey_comparison": "User Journey Comparison",
    }
    return mapping.get(str(name), str(name))


def _header_map() -> Dict[str, str]:
    return {
        "dimension": "Dimension",
        "competitor": "Competitor",
        "target_user": "Target User",
        "core_scenario": "Core Scenario",
        "product_form": "Product Form",
        "main_entry": "Main Entry Point",
        "business_model": "Business Model",
        "strategic_judgement": "Strategic Assessment",
        "stage": "Stage",
        "user_goal": "User Goal",
        "competitor_experience": "Competitor Experience",
        "opportunity": "Opportunity",
        "evidence_ids": "Evidence ID",
        "competitor_name": "Competitor",
        "product": "Competitor",
        "product_name": "Competitor",
        "target_users": "Target Users",
        "core_positioning": "Core Positioning",
        "capability": "Capability",
        "score": "Score",
        "scores": "Scores",
        "reason": "Rationale",
        "journey_stage": "Stage",
        "source_ids": "Evidence ID",
    }


def _row_has_content(row: Dict[str, Any]) -> bool:
    for key, value in row.items():
        if key == "pending_search_query":
            continue
        if key == "evidence_ids":
            if value:
                return True
            continue
        if isinstance(value, dict) and value:
            return True
        if isinstance(value, list) and value:
            return True
        if isinstance(value, str) and value.strip():
            return True
        if isinstance(value, (int, float)) and value != 0:
            return True
    return False


def _valid_rows(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [row for row in rows if isinstance(row, dict) and _row_has_content(row)]


def _clean_table_rows(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cleaned: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        next_row = dict(row)
        next_row.pop("pending_search_query", None)
        cleaned.append(next_row)
    return cleaned


def _pending_row_for_columns(columns: Iterable[Any], table_name: Any) -> Dict[str, Any]:
    row: Dict[str, Any] = {}
    subject = clean_text(table_name, 80) or "cross-product comparison table"
    for raw_column in columns:
        column = str(raw_column)
        if column in {"evidence_ids", "evidenceID", "evidenceids", "source_ids", "pending_search_query"}:
            continue
        if column in {"competitor", "产品", "产品名称", "competitor"}:
            row[column] = "Pending search"
        else:
            row[column] = f"Pending search for {subject} {column}"
    row["evidence_ids"] = []
    return row


def _columns_for_rows(rows: Iterable[Dict[str, Any]], preferred: List[str]) -> List[str]:
    keys: List[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in row.keys():
            if key == "pending_search_query":
                continue
            if key not in keys:
                keys.append(str(key))
    columns = [key for key in preferred if key in keys]
    columns.extend(key for key in keys if key not in columns)
    return columns or preferred


def _simple_table_or_empty(
    columns: List[str],
    rows: Iterable[Dict[str, Any]],
    *,
    header_map: Dict[str, str] | None = None,
) -> str:
    valid = _valid_rows(rows)
    if not valid:
        return "No comparable data available."
    return _simple_table(columns, valid, header_map=header_map or {})


def _simple_table(
    columns: List[str],
    rows: Iterable[Dict[str, Any]],
    *,
    header_map: Dict[str, str] | None = None,
) -> str:
    header_map = header_map or {}
    lines = [
        "| " + " | ".join(header_map.get(column, column) for column in columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for row in rows:
        lines.append(
            "| " + " | ".join(_cell(row.get(column)) for column in columns) + " |"
        )
    return "\n".join(lines)


def _score_table_or_empty(rows: Iterable[Dict[str, Any]]) -> str:
    valid = _valid_rows(rows)
    if not valid:
        return "No comparable data available."
    return _score_table(valid)


def _score_table(rows: Iterable[Dict[str, Any]]) -> str:
    lines = [
        "| Dimension | Weight | Scores | Rationale | Evidence ID |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| {dimension} | {weight} | {scores} | {reason} | {evidence_ids} |".format(
                dimension=_cell(row.get("dimension")),
                weight=_cell(row.get("weight")),
                scores=_cell(row.get("scores")),
                reason=_cell(row.get("reason")),
                evidence_ids=_cell(row.get("evidence_ids")),
            )
        )
    return "\n".join(lines)


def _swot_markdown(state: ReportState) -> str:
    sections = [
        ("Strengths", state.swot.strengths),
        ("Weaknesses", state.swot.weaknesses),
        ("Opportunities", state.swot.opportunities),
        ("Threats", state.swot.threats),
    ]
    lines: List[str] = []
    for title, items in sections:
        lines.append(f"### {title}")
        if not items:
            lines.append("- Insufficient evidence.")
            continue
        for item in items:
            lines.append(_swot_item_line(item))
    return "\n".join(lines)


def _swot_item_line(item: SWOTItem) -> str:
    return (
        f"- {item.point}: {item.why_it_matters} "
        f"Product implication: {item.pm_implication} "
        f"Confidence: {item.confidence:.2f} "
        f"evidence: {', '.join(item.evidence_ids)}"
    )


def _structured_payload(state: ReportState) -> Dict[str, Any]:
    return {
        "executive_summary": {"text": _executive_summary(state)},
        "evidence_cards": [card.to_dict() for card in state.evidence_cards],
        "pm_insights": [insight.to_dict() for insight in state.pm_insights],
        "competitor_profiles": state.competitor_profiles,
        "comparison_tables": state.comparison_tables,
        "swot": state.swot.to_dict(),
        "recommendations": [rec.to_dict() for rec in state.recommendations],
        "product_recommendations": [rec.to_dict() for rec in state.recommendations],
    }


def _cell(value: Any) -> str:
    """清理table单元格内容，避免 Markdown table被竖线破坏。"""

    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    text = clean_text(value, 220)
    return text.replace("|", "\\|")


def _clean_report(report: str) -> str:
    report = report.replace("```markdown", "").replace("```", "").strip()
    return report + "\n" if report else ""


def _has_invalid_empty_tables(report: str) -> bool:
    for table in _extract_markdown_tables(report):
        if _table_is_mostly_empty(table):
            return True
    return False


def _extract_markdown_tables(report: str) -> List[List[str]]:
    tables: List[List[str]] = []
    current: List[str] = []
    for raw_line in report.splitlines():
        line = raw_line.strip()
        if line.startswith("|") and line.endswith("|"):
            current.append(line)
            continue
        if current:
            if len(current) >= 3:
                tables.append(current)
            current = []
    if current and len(current) >= 3:
        tables.append(current)
    return tables


def _table_is_mostly_empty(lines: List[str]) -> bool:
    headers = [cell.strip() for cell in lines[0].strip("|").split("|")]
    data_rows = [
        line
        for line in lines[2:]
        if not re.fullmatch(r"\|\s*[-: ]+(?:\|\s*[-: ]+)*\|", line)
    ]
    if not data_rows:
        return True

    empty_rows = 0
    useful_rows = 0
    for row in data_rows:
        cells = [cell.strip() for cell in row.strip("|").split("|")]
        if _markdown_row_has_required_content(headers, cells):
            useful_rows += 1
        else:
            empty_rows += 1

    return useful_rows == 0 or empty_rows >= max(2, len(data_rows) // 2 + 1)


def _markdown_row_has_required_content(headers: List[str], cells: List[str]) -> bool:
    row = {
        header: cells[index] if index < len(cells) else ""
        for index, header in enumerate(headers)
    }
    if "dimension" in row and "scores" in row and "reason" in row:
        return bool(
            _meaningful_cell(row.get("dimension"))
            and (_meaningful_cell(row.get("scores")) or _meaningful_cell(row.get("reason")))
        )
    if "stage" in row and "user_goal" in row and "opportunity" in row:
        return bool(
            _meaningful_cell(row.get("stage"))
            and (
                _meaningful_cell(row.get("user_goal"))
                or _meaningful_cell(row.get("competitor_experience"))
                or _meaningful_cell(row.get("opportunity"))
            )
        )
    if "competitor" in row and "strategic_judgement" in row:
        return bool(
            _meaningful_cell(row.get("competitor"))
            and (
                _meaningful_cell(row.get("target_user"))
                or _meaningful_cell(row.get("core_scenario"))
                or _meaningful_cell(row.get("business_model"))
                or _meaningful_cell(row.get("strategic_judgement"))
            )
        )
    return any(
        _meaningful_cell(cell)
        for header, cell in row.items()
        if header != "evidence_ids"
    )


def _meaningful_cell(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    return text not in {"[]", "{}", "null", "None", "未找到明确evidence", "No explicit evidence found"}
