"""The Finding: a single discrete issue surfaced by a check.

Findings are facts. The tool never emits an opinion that isn't backed by one.
Every check writes Findings in this exact shape; the canonical Findings File
and both reports are projections of it (ADR-0006).
"""

from dataclasses import dataclass

# The fixed 5-level severity scale (see CONTEXT.md glossary).
CRITICAL = "Critical"
HIGH = "High"
MEDIUM = "Medium"
LOW = "Low"
INFO = "Info"


@dataclass(frozen=True)
class Finding:
    repo: str
    check_id: str
    category: str
    severity: str
    evidence: str
    location: str
