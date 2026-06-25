"""Base inspection functions for report quality."""

from typing import List

from ..adapters.report_adapter import ReportAnalysis
from ..config import (
    IssueSeverity,
    IssueType,
    QualityIssue,
    is_navigation_url,
)

# 检查声明与evidence的链接完整性
def check_claim_evidence_linkage(analysis: ReportAnalysis) -> List[QualityIssue]:
    """Check claim-evidence linkage completeness."""
    issues: List[QualityIssue] = []
    
    # 收集All存在的evidence的ID
    evidence_ids = {e.source_id for e in analysis.evidence_list if e.source_id}
    
    # 检查Each声明是否有evidence支持
    for claim in analysis.claims:
        claim_id = claim.get("claim_id", "")
        evidence_ids_in_claim = claim.get("evidence_ids", [])
        
        # 检查声明是否有evidence支持
        if not evidence_ids_in_claim:
            issues.append(QualityIssue(
                type=IssueType.WEAK_EVIDENCE_SUPPORT,
                severity=IssueSeverity.MAJOR,
                description=f"声明 {claim_id} 缺少evidence支持",
                suggestion="为该声明添加相关evidencesource",
                explanation="Each声明都需要有evidence支持以保证可信度",
                impact="无evidence支持的声明会降低报告可信度",
                confidence=claim.get("confidence", 1.0)
            ))
        else:
            # 检查声明引用的evidence是否存在
            for ev_id in evidence_ids_in_claim:
                if ev_id not in evidence_ids:
                    issues.append(QualityIssue(
                        type=IssueType.MISSING_SOURCE,
                        severity=IssueSeverity.MINOR,
                        description=f"声明 {claim_id} 引用的evidence {ev_id} 不存在",
                        suggestion="验证evidenceID是否正确",
                        explanation="evidence引用应该指向有效的source",
                        impact="无效的evidence引用会影响可追溯性"
                    ))
    
    return issues


# 检查evidence的质量
def check_evidence_quality(analysis: ReportAnalysis) -> List[QualityIssue]:
    """Check evidence quality."""
    issues: List[QualityIssue] = []
    
    # 检查Eachevidence的质量
    for evidence in analysis.evidence_list:
        if not evidence.url or len(evidence.url) < 10:
            issues.append(QualityIssue(
                type=IssueType.LOW_QUALITY_EVIDENCE,
                severity=IssueSeverity.MINOR,
                description=f"evidence '{evidence.title[:30]}...' URL无效或过短",
                suggestion="确保Allevidence都有有效的sourceURL",
                explanation="有效的URL是验证信息真实性的重要依据",
                impact="无效URL会影响信息的可验证性"
            ))
        
        # 检查evidence是否为导航页面
        if is_navigation_url(evidence.url, evidence.title):
            issues.append(QualityIssue(
                type=IssueType.LOW_QUALITY_EVIDENCE,
                severity=IssueSeverity.MINOR,
                description=f"evidence '{evidence.title[:30]}...' 是导航页面",
                suggestion="替换为包含实际内容的页面链接",
                explanation="导航页面通常不包含有用的产品信息",
                impact="导航链接作为evidence会降低Analyze质量"
            ))
        
        # 检查evidence内容是否足够详细
        content_length = len(evidence.page_text) + len(evidence.snippet)
        if content_length < 100:
            issues.append(QualityIssue(
                type=IssueType.LOW_QUALITY_EVIDENCE,
                severity=IssueSeverity.MINOR,
                description=f"evidence '{evidence.title[:30]}...' 内容过短",
                suggestion="寻找包含更详细信息的source",
                explanation="充足的内容是Analyze的基础",
                impact="内容不足可能导致Analyze不全面"
            ))
        
        # 检查evidence置信度是否足够高
        if evidence.confidence < 0.6:
            issues.append(QualityIssue(
                type=IssueType.WEAK_EVIDENCE_SUPPORT,
                severity=IssueSeverity.MINOR,
                description=f"evidence '{evidence.title[:30]}...' 置信度较低 ({evidence.confidence:.2f})",
                suggestion="寻找更可靠的evidencesource",
                explanation="低置信度evidence会影响结论的可靠性",
                impact="过多低置信度evidence会降低报告可信度"
            ))
    
    return issues