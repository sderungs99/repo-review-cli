"""The check-runner harness: composes the whole review pipeline.

Load the Manifest -> acquire each Subject Repo at its pinned SHA -> run every
hardcoded check over the local checkout -> collect the Findings. The result is
deterministic given (checkouts + tool version): no network at analysis time
(ADR-0007). Writing the Findings File and rendering reports happen above this.
"""

from pathlib import Path

from repo_review.acquire import acquire_repo
from repo_review.checks import (
    check_large_files,
    check_readme_presence,
    check_tests_present,
    check_todo_markers,
)
from repo_review.finding import Finding
from repo_review.manifest import load_manifest


def run_review(manifest_path: Path, workdir: Path) -> list[Finding]:
    """Run every check across every Subject Repo in the Manifest."""
    findings: list[Finding] = []
    for entry in load_manifest(manifest_path):
        checkout = acquire_repo(entry, workdir)
        findings.extend(check_readme_presence(entry.name, checkout))
        findings.extend(check_todo_markers(entry.name, checkout))
        findings.extend(check_large_files(entry.name, checkout))
        findings.extend(check_tests_present(entry.name, checkout))
    return findings
