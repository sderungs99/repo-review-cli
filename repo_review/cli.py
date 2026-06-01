"""The single, re-runnable CLI entry point (ADR-0005).

    python -m repo_review --manifest <path> --out <dir>

Runs the review and writes the canonical Findings File plus both reports
(pure projections of it) into the output directory.
"""

import argparse
import shutil
from pathlib import Path

from repo_review.findings_file import write_findings
from repo_review.reports import render_stakeholder, render_technical
from repo_review.runner import run_review

FINDINGS_FILE = "findings.json"
TECHNICAL_REPORT = "technical-findings-report.md"
STAKEHOLDER_REPORT = "stakeholder-report.md"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="repo_review")
    parser.add_argument("--manifest", required=True, type=Path,
                        help="Path to the SHA-pinned Manifest JSON.")
    parser.add_argument("--out", required=True, type=Path,
                        help="Output directory for findings and reports.")
    args = parser.parse_args(argv)

    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)

    # Clean checkout area so the command is safely re-runnable into the same out.
    workdir = out / "_checkouts"
    if workdir.exists():
        shutil.rmtree(workdir)

    findings = run_review(args.manifest, workdir)

    write_findings(findings, out / FINDINGS_FILE)
    (out / TECHNICAL_REPORT).write_text(render_technical(findings))
    (out / STAKEHOLDER_REPORT).write_text(render_stakeholder(findings))
    return 0
