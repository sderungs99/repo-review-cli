"""The single, re-runnable CLI entry point (ADR-0005).

    python -m repo_review --manifest <path> --out <dir>

Runs the review and writes the canonical Findings File plus both reports
(pure projections of it) into the output directory.
"""

import argparse
import tempfile
from pathlib import Path

from repo_review.findings_file import write_findings
from repo_review.reports import render_stakeholder, render_technical
from repo_review.runner import run_review

FINDINGS_FILE = "findings.json"
TECHNICAL_REPORT = "technical-findings-report.md"
STAKEHOLDER_REPORT = "stakeholder-report.md"
DEFAULT_MANIFEST = Path("manifest.json")
DEFAULT_OUT = Path("reports")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="repo_review")
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST, type=Path,
                        help="Path to the SHA-pinned Manifest JSON "
                             f"(default: ./{DEFAULT_MANIFEST}).")
    parser.add_argument("--out", default=DEFAULT_OUT, type=Path,
                        help="Output directory for findings and reports "
                             f"(default: ./{DEFAULT_OUT}).")
    args = parser.parse_args(argv)

    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)

    # Clone into a throwaway working area: the checkouts are disposable, only
    # the findings and reports are durable. This keeps the output folder clean
    # and makes the command safely re-runnable.
    with tempfile.TemporaryDirectory(prefix="repo-review-checkouts-") as workdir:
        findings = run_review(args.manifest, Path(workdir))

    write_findings(findings, out / FINDINGS_FILE)
    (out / TECHNICAL_REPORT).write_text(render_technical(findings))
    (out / STAKEHOLDER_REPORT).write_text(render_stakeholder(findings))
    return 0
