"""Evidence inspection functions for diversity and timeliness."""

import re
from urllib.parse import urlparse
from typing import Dict, List, Set

from ..adapters.report_adapter import ReportAnalysis
from ..config import IssueSeverity, IssueType, QualityIssue


def _http_domain(url: str) -> str:
    parsed = urlparse(url or "")
    if parsed.scheme not in ("http", "https"):
        return ""
    return parsed.netloc

# 要确保检查evidencesource多样性多样性
def check_evidence_diversity(analysis: ReportAnalysis) -> List[QualityIssue]:
    """Check evidence source diversity."""
    issues: List[QualityIssue] = []
    
    # 检查报告是否有evidence部分
    if len(analysis.evidence_list) < 3:
        return issues
    
    # 检查Eachevidence是否包含任何source类型
    source_types: Dict[str, int] = {}
    # 检查Eachevidence是否包含任何域名
    domains: Set[str] = set()
    http_url_count = 0
    
    # 检查Eachevidence是否包含任何source类型
    for evidence in analysis.evidence_list:
        source_type = evidence.source_type or "unknown"
        source_types[source_type] = source_types.get(source_type, 0) + 1
        # 检查Eachevidence是否包含任何域名
        domain = _http_domain(evidence.url)
        if domain:
            http_url_count += 1
            domains.add(domain)
    
    # 检查Eachevidence是否包含任何source类型和域名
    if len(source_types) <= 1:
        issues.append(QualityIssue(
            type=IssueType.LOW_QUALITY_EVIDENCE,
            severity=IssueSeverity.MINOR,
            description=f"evidencesource类型单一: {list(source_types.keys())}",
            suggestion="增加更多类型的source（官方文档、评测文章、user评论等）",
            explanation="多样化的source能提高Analyze的客观性",
            impact="单一source可能存在偏见，影响Analyze结论"
        ))
    
    if http_url_count >= 3 and len(domains) <= 2:
        issues.append(QualityIssue(
            type=IssueType.LOW_QUALITY_EVIDENCE,
            severity=IssueSeverity.MINOR,
            description=f"evidencesource域名过于集中: {len(domains)} 个域名",
            suggestion="增加更多不同域名的source",
            explanation="分散的域名source能降低信息source的相关性偏差",
            impact="集中的域名source可能导致信息片面"
        ))
    
    total_evidence = len(analysis.evidence_list)
    for source_type, count in source_types.items():
        if count / total_evidence > 0.7:
            issues.append(QualityIssue(
                type=IssueType.LOW_QUALITY_EVIDENCE,
                severity=IssueSeverity.MINOR,
                description=f"过度依赖 {source_type} 类型source ({count}/{total_evidence})",
                suggestion="平衡各类source的比例",
                explanation="均衡的source分布能提高Analyze的可靠性",
                impact="过度依赖单一source类型可能产生偏见"
            ))
    
    return issues

# 要确保检查evidence时效性时效性
def check_evidence_timeliness(analysis: ReportAnalysis) -> List[QualityIssue]:
    """Check evidence timeliness."""
    issues: List[QualityIssue] = []
    
    #看看有没有过时的消息
    outdated_count = 0
    # 检查Eachevidence是否包含任何发布日期
    undated_count = 0
    
    # 检查Eachevidence是否包含任何发布日期
    for evidence in analysis.evidence_list:
        publish_date = evidence.publish_date
        if not publish_date:
            undated_count += 1
            continue
        
        year_match = re.search(r"(\d{4})", publish_date)
        if year_match:
            year = int(year_match.group(1))
            if year < 2023:
                outdated_count += 1
    
    # 检查过时的消息数量
    if outdated_count > 0:
        issues.append(QualityIssue(
            type=IssueType.LOW_QUALITY_EVIDENCE,
            # 检查过时的消息数量是否超过2条
            # If超过2条，就认为是主要issue
            severity=IssueSeverity.MINOR if outdated_count <= 3 else IssueSeverity.MAJOR,
            description=f"存在 {outdated_count} 条可能过时的evidence",
            suggestion="更新或替换过时的evidencesource",
            explanation="科技产品信息变化较快，过时信息可能不准确",
            impact="过时信息可能导致Analyze结论偏离当前实际情况"
        ))
    
    # 检查缺少发布日期的消息evidence数量
    # If超过一半，就认为是主要issue
    if undated_count > len(analysis.evidence_list) * 0.5:
        issues.append(QualityIssue(
            type=IssueType.LOW_QUALITY_EVIDENCE,
            severity=IssueSeverity.MINOR,
            description=f"超过一半的evidence缺少发布日期",
            suggestion="尽量获取带有发布日期的source",
            explanation="发布日期是评估信息时效性的重要依据",
            impact="缺少日期信息无法评估信息的时效性"
        ))
    
    return issues
