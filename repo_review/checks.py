"""Self-computed checks that run over a Subject Repo's local checkout.

Checks are hardcoded (ADR-0004) and read only the source tree and config
(ADR-0002) — no build, no runtime, no network. Each check is a pure function
of (repo name, checkout path) returning zero or more Findings.
"""

import re
from pathlib import Path

from repo_review.finding import Finding, HIGH, MEDIUM, LOW, INFO

README_CHECK_ID = "readme-presence"

TODO_CHECK_ID = "todo-markers"

# Markers matched only inside a comment (//, /* */, or a *-continuation line),
# regardless of what follows them — "// TODO", "//TODO:", "* FIXME(JIRA-1)".
_TODO_MARKER = re.compile(
    r"(?://|/\*|^\s*\*).*?\b(?:TODO|FIXME|HACK)\b", re.IGNORECASE
)

# Source extensions of the Subject Repo portfolio: Java back ends and the
# React / React Native front ends. No Python, no Kotlin (not in the codebase).
_SOURCE_SUFFIXES = {".java", ".js", ".jsx", ".ts", ".tsx"}

# Directories that hold vendored dependencies or build output, not the vendor's
# own source — markers in here are noise and must not be counted.
_SKIP_DIRS = {".git", "node_modules", "target", "build", "dist"}

# A larger pile of unresolved markers is treated as Low rather than Info — the
# volume is itself the corroboration signal against vendor Sonar data (ADR-0003).
TODO_LOW_SEVERITY_THRESHOLD = 50

# How many file:line locations to quote in the evidence as a representative
# sample — enough to corroborate, not the whole haystack.
TODO_SAMPLE_LIMIT = 5


def check_todo_markers(repo_name: str, checkout_path: Path) -> list[Finding]:
    """Count TODO/FIXME/HACK markers across a Subject Repo's source files."""
    locations = []
    for source in _iter_source_files(checkout_path):
        relative = source.relative_to(checkout_path).as_posix()
        for lineno, line in enumerate(source.read_text(errors="replace").splitlines(), 1):
            if _TODO_MARKER.search(line):
                locations.append(f"{relative}:{lineno}")

    count = len(locations)
    if count == 0:
        return []

    sample = ", ".join(locations[:TODO_SAMPLE_LIMIT])
    severity = LOW if count >= TODO_LOW_SEVERITY_THRESHOLD else INFO
    return [Finding(
        repo=repo_name,
        check_id=TODO_CHECK_ID,
        category="code-hygiene",
        severity=severity,
        evidence=(
            f"Found {count} TODO/FIXME/HACK marker(s) across source files. "
            f"Sample locations: {sample}."
        ),
        location=".",
    )]


def _iter_source_files(checkout_path: Path):
    """Allowlisted source files under the checkout, in stable sorted order.

    Vendored-dependency and build-output directories are pruned so their
    markers never count toward the vendor's own source.
    """
    for path in sorted(checkout_path.rglob("*")):
        if not (path.is_file() and path.suffix in _SOURCE_SUFFIXES):
            continue
        if _SKIP_DIRS.intersection(path.relative_to(checkout_path).parts):
            continue
        yield path

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
