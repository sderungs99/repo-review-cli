"""Self-computed checks that run over a Subject Repo's local checkout.

Checks are hardcoded (ADR-0004) and read only the source tree and config
(ADR-0002) — no build, no runtime, no network. Each check is a pure function
of (repo name, checkout path) returning zero or more Findings.
"""

import re
from pathlib import Path
from xml.etree import ElementTree

from repo_review.finding import Finding, HIGH, MEDIUM, LOW, INFO

README_CHECK_ID = "readme-presence"

TODO_CHECK_ID = "todo-markers"

LARGE_FILE_CHECK_ID = "large-file"

TESTS_PRESENT_CHECK_ID = "tests-present"

SONAR_EXCLUSIONS_CHECK_ID = "sonar-exclusions"

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


# A source file longer than this is flagged as a maintainability signal. Pure
# physical-line count (blanks and comments included); the threshold is calibrated
# for that. Hardcoded per ADR-0004.
LARGE_FILE_LOC_THRESHOLD = 1000

# A file at or beyond twice the threshold is a far stronger maintainability
# signal, so it is escalated from Low to Medium.
LARGE_FILE_MEDIUM_LOC_THRESHOLD = 2 * LARGE_FILE_LOC_THRESHOLD


def check_large_files(repo_name: str, checkout_path: Path) -> list[Finding]:
    """Flag Subject Repo source files whose LOC exceeds the threshold."""
    findings = []
    for source in _iter_source_files(checkout_path):
        loc = len(source.read_text(errors="replace").splitlines())
        if loc <= LARGE_FILE_LOC_THRESHOLD:
            continue
        relative = source.relative_to(checkout_path).as_posix()
        severity = MEDIUM if loc >= LARGE_FILE_MEDIUM_LOC_THRESHOLD else LOW
        findings.append(Finding(
            repo=repo_name,
            check_id=LARGE_FILE_CHECK_ID,
            category="code-hygiene",
            severity=severity,
            evidence=(
                f"{relative} is {loc} LOC, over the "
                f"{LARGE_FILE_LOC_THRESHOLD}-LOC threshold."
            ),
            location=relative,
        ))
    return findings


def check_tests_present(repo_name: str, checkout_path: Path) -> list[Finding]:
    """Does the Subject Repo contain a test suite at all? (presence only)."""
    if _has_test_tree(checkout_path):
        return []
    return [Finding(
        repo=repo_name,
        check_id=TESTS_PRESENT_CHECK_ID,
        category="testing",
        severity=HIGH,
        evidence=(
            "Looked for an ecosystem test tree (Java/Maven src/test/**, "
            "React/React Native *.test.* / *.spec.* files or a __tests__/ "
            "directory); found none."
        ),
        location=".",
    )]


def _has_test_tree(checkout_path: Path) -> bool:
    """Any ecosystem's test-tree signal present in the repo's own source?"""
    for path in checkout_path.rglob("*"):
        relative_parts = path.relative_to(checkout_path).parts
        if _SKIP_DIRS.intersection(relative_parts):
            continue
        if _is_test_signal(relative_parts):
            return True
    return False


def _is_test_signal(relative_parts: tuple[str, ...]) -> bool:
    """Does this repo-relative path match an ecosystem test-tree convention?"""
    # Java / Maven: a src/test/** tree.
    for i in range(len(relative_parts) - 1):
        if relative_parts[i] == "src" and relative_parts[i + 1] == "test":
            return True
    # React / React Native: a __tests__/ directory anywhere.
    if "__tests__" in relative_parts:
        return True
    # React / React Native: a *.test.* / *.spec.* file.
    name = relative_parts[-1]
    return ".test." in name or ".spec." in name


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

# The Sonar exclusion keys we detect, mapped to a severity that reflects how
# much each one hides from analysis. `sonar.exclusions` removes files from ALL
# analysis (the strongest concealment); coverage/cpd/test exclusions narrow only
# one dimension. Hardcoded editorial severities per ADR-0004.
_SONAR_EXCLUSION_SEVERITY = {
    "sonar.exclusions": HIGH,
    "sonar.coverage.exclusions": MEDIUM,
    "sonar.cpd.exclusions": LOW,
    "sonar.test.exclusions": LOW,
}


def check_sonar_exclusions(repo_name: str, checkout_path: Path) -> list[Finding]:
    """Flag Sonar exclusion settings configured in the Subject Repo's checkout.

    Exclusions tell Sonar to ignore parts of the codebase, so the vendor's own
    quality metrics never saw that code (ADR-0003). Read purely from config
    files in the checkout, never the Sonar server (ADR-0007).
    """
    findings = []
    properties = checkout_path / "sonar-project.properties"
    if properties.is_file():
        location = properties.relative_to(checkout_path).as_posix()
        directives = _parse_properties(properties).items()
        findings.extend(_findings_for(repo_name, location, directives))

    pom = checkout_path / "pom.xml"
    if pom.is_file():
        location = pom.relative_to(checkout_path).as_posix()
        directives = _parse_pom_exclusions(pom).items()
        findings.extend(_findings_for(repo_name, location, directives))

    for yaml in _iter_pipeline_files(checkout_path):
        location = yaml.relative_to(checkout_path).as_posix()
        directives = _parse_pipeline_exclusions(yaml).items()
        findings.extend(_findings_for(repo_name, location, directives))

    return findings


def _findings_for(repo_name, location, directives):
    """A finding per (key, patterns) directive whose key is an exclusion key."""
    return [
        _exclusion_finding(repo_name, location, key, value)
        for key, value in directives
        if key in _SONAR_EXCLUSION_SEVERITY
    ]


def _exclusion_finding(repo_name, location, key, patterns):
    """One finding for a single (config file, exclusion key) directive."""
    return Finding(
        repo=repo_name,
        check_id=SONAR_EXCLUSIONS_CHECK_ID,
        category="sonar-integrity",
        severity=_SONAR_EXCLUSION_SEVERITY[key],
        evidence=f"Sonar {key} excludes {patterns} from analysis.",
        location=location,
    )


def _parse_pom_exclusions(path: Path) -> dict[str, str]:
    """Sonar exclusion keys configured as Maven properties in a pom.xml.

    Maven drives Sonar through `<properties>`, e.g. `<sonar.exclusions>`. POMs
    carry the Maven namespace, so elements are matched on their local tag name.
    """
    try:
        root = ElementTree.parse(path).getroot()
    except ElementTree.ParseError:
        return {}
    result = {}
    for element in root.iter():
        local = element.tag.rpartition("}")[2]
        if local in _SONAR_EXCLUSION_SEVERITY and element.text:
            result[local] = element.text.strip()
    return result


# An ADO pipeline step invoking a SonarQube/SonarCloud task. Exclusion lines are
# only honoured as Sonar directives when the file actually wires up such a task,
# so a stray `sonar.exclusions=` in an unrelated script line is not mistaken.
_SONAR_TASK = re.compile(r"task:\s*Sonar(?:Qube|Cloud)\w*", re.IGNORECASE)

# A `sonar.<...>exclusions=<patterns>` assignment, as it appears inside an ADO
# task's `extraProperties` block (or a `-Dsonar...exclusions=` command line).
_PIPELINE_EXCLUSION = re.compile(r"(sonar\.[\w.]*exclusions)\s*=\s*(\S.*?)\s*$")


def _iter_pipeline_files(checkout_path: Path):
    """YAML files under the checkout, in stable order, vendored dirs pruned."""
    for path in sorted(checkout_path.rglob("*")):
        if not (path.is_file() and path.suffix in {".yml", ".yaml"}):
            continue
        if _SKIP_DIRS.intersection(path.relative_to(checkout_path).parts):
            continue
        yield path


def _parse_pipeline_exclusions(path: Path) -> dict[str, str]:
    """Sonar exclusion assignments in a pipeline YAML that wires a Sonar task."""
    text = path.read_text(errors="replace")
    if not _SONAR_TASK.search(text):
        return {}
    result = {}
    for line in text.splitlines():
        match = _PIPELINE_EXCLUSION.search(line)
        if match and match.group(1) in _SONAR_EXCLUSION_SEVERITY:
            result[match.group(1)] = match.group(2)
    return result


def _parse_properties(path: Path) -> dict[str, str]:
    """Parse a .properties file into key -> value (last write wins)."""
    result = {}
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "!")) or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


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
