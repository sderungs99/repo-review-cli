"""The canonical Findings File: the single source of truth (ADR-0006).

Every check writes into one JSON array of Findings. Both reports are pure
projections of this file, so they can never drift from the evidence.
"""

import json
from dataclasses import asdict
from pathlib import Path

from repo_review.finding import Finding


def _sort_key(f: Finding) -> tuple:
    return (f.repo, f.check_id, f.category, f.location, f.severity, f.evidence)


def to_json(findings: list[Finding]) -> str:
    """Serialize Findings to the canonical JSON text.

    Findings are sorted into a stable order so the file is byte-identical
    across runs regardless of the order checks happened to emit them in.
    """
    ordered = sorted(findings, key=_sort_key)
    return json.dumps([asdict(f) for f in ordered], indent=2) + "\n"


def write_findings(findings: list[Finding], path: Path) -> None:
    """Write the canonical Findings File to ``path``."""
    path.write_text(to_json(findings))
