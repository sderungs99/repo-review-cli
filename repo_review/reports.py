"""Both reports, rendered as pure projections of the Findings (ADR-0006).

Neither report is ever produced independently of the canonical Findings File,
so the non-technical view can never drift from the evidence. In v1 both are
deterministic Markdown templates — no prose, no LLM (deferred to phase 2).
"""

from collections import Counter

from repo_review.finding import Finding, CRITICAL, HIGH, MEDIUM, LOW, INFO

SEVERITY_ORDER = [CRITICAL, HIGH, MEDIUM, LOW, INFO]


def render_stakeholder(findings: list[Finding]) -> str:
    """The non-technical rolled-up narrative: counts by category and severity."""
    by_category = Counter(f.category for f in findings)
    by_severity = Counter(f.severity for f in findings)

    lines = ["# Stakeholder Report", "", f"Total findings: {len(findings)}", ""]

    lines.append("## Findings by category")
    for category in sorted(by_category):
        lines.append(f"- {category}: {by_category[category]}")
    lines.append("")

    lines.append("## Findings by severity")
    for severity in SEVERITY_ORDER:
        if by_severity[severity]:
            lines.append(f"- {severity}: {by_severity[severity]}")
    lines.append("")

    return "\n".join(lines)


def render_technical(findings: list[Finding]) -> str:
    """The engineering-facing evidence set, grouped by repo and category."""
    lines = ["# Technical Findings Report", ""]

    for repo in sorted({f.repo for f in findings}):
        lines.append(f"## {repo}")
        repo_findings = [f for f in findings if f.repo == repo]
        for category in sorted({f.category for f in repo_findings}):
            lines.append(f"### {category}")
            for f in repo_findings:
                if f.category != category:
                    continue
                lines.append(
                    f"- [{f.severity}] {f.check_id} — {f.evidence} ({f.location})"
                )
        lines.append("")

    return "\n".join(lines)
