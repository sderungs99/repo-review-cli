"""Self-computed checks that run over a Subject Repo's local checkout.

Checks are hardcoded (ADR-0004) and read only the source tree and config
(ADR-0002) — no build, no runtime, no network. Each check is a pure function
of (repo name, checkout path) returning zero or more Findings.
"""

from pathlib import Path

from repo_review.finding import Finding, HIGH, MEDIUM

README_CHECK_ID = "readme-presence"

# A README with fewer real words than this is treated as a stub, not real
# documentation (e.g. a bare title plus "TODO").
README_STUB_WORD_THRESHOLD = 10


def check_readme_presence(repo_name: str, checkout_path: Path) -> list[Finding]:
    """Does the Subject Repo have a README with non-trivial content?"""
    def documentation_finding(severity, evidence, location):
        return Finding(
            repo=repo_name,
            check_id=README_CHECK_ID,
            category="documentation",
            severity=severity,
            evidence=evidence,
            location=location,
        )

    readme = _find_readme(checkout_path)
    if readme is None:
        return [documentation_finding(
            HIGH, "No README file found in the repository root.", ".")]

    word_count = len(readme.read_text(errors="replace").split())
    if word_count < README_STUB_WORD_THRESHOLD:
        return [documentation_finding(
            MEDIUM,
            f"README is a stub: {word_count} words, below the "
            f"{README_STUB_WORD_THRESHOLD}-word threshold for real documentation.",
            readme.name,
        )]
    return []


def _find_readme(checkout_path: Path) -> Path | None:
    """The README at the repo root, if one exists."""
    for child in checkout_path.iterdir():
        if child.is_file() and child.stem.lower() == "readme":
            return child
    return None
