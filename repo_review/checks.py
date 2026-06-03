"""Self-computed checks that run over a Subject Repo's local checkout.

Checks are hardcoded (ADR-0004) and read only the source tree and config
(ADR-0002) — no build, no runtime, no network. Each check is a pure function
of (repo name, checkout path) returning zero or more Findings.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

from repo_review.finding import Finding, CRITICAL, HIGH, MEDIUM, LOW, INFO

README_CHECK_ID = "readme-presence"

TODO_CHECK_ID = "todo-markers"

LARGE_FILE_CHECK_ID = "large-file"

TESTS_PRESENT_CHECK_ID = "tests-present"

SONAR_EXCLUSIONS_CHECK_ID = "sonar-exclusions"

REACT_DANGEROUS_HTML_CHECK_ID = "react-dangerous-html"

SQL_STRING_CONCAT_CHECK_ID = "sql-string-concat"

SECRETS_CHECK_ID = "secret-scanning"

SNAPSHOT_PRERELEASE_DEPS_CHECK_ID = "snapshot-prerelease-deps"

DISABLED_TESTS_CHECK_ID = "disabled-tests"

ASSERTION_FREE_TESTS_CHECK_ID = "assertion-free-tests"

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


# (kind, compiled pattern, editorial severity). Each entry is a high-confidence
# structural signature for a committed secret; severity is editorial per the kind
# of credential exposed (ADR-0004). The full matched value is never reported —
# only the kind and the file:line locate it.
_SECRET_PATTERNS = [
    ("private key", re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----"), CRITICAL),
    ("AWS access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), HIGH),
    ("GitHub token", re.compile(r"\bgh[pousr]_[0-9A-Za-z]{36}\b"), HIGH),
    ("Slack token", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b"), HIGH),
]

# A config assignment whose key names a credential, capturing the assigned value.
# Matched case-insensitively on the keyword sitting immediately before the `=`/`:`
# separator, so apiKey / api_key / API_KEY all qualify but an unrelated key does
# not. Severity is Medium: the key proves intent but the value is unverifiable.
_CREDENTIAL_ASSIGNMENT = re.compile(
    r"(?i)(?:password|passwd|pwd|secret|api[_-]?key|apikey|"
    r"access[_-]?key|access[_-]?token|token)\s*[:=]\s*(.+)$"
)

# Values that are plainly not a committed secret: a known placeholder word or a
# `your_..._here`-style template. Interpolations (${...}, {{...}}, <...>) and
# too-short values are screened separately.
_PLACEHOLDER_VALUE = re.compile(
    r"(?i)^(?:change[-_]?me|password|secret|example|sample|test|dummy|"
    r"none|null|todo|tbd|x+|\*+|your[_-].*)$"
)

# Below this length a captured value carries too little signal to be a real
# credential, so it is not flagged (screens empties and trivial stubs).
_GENERIC_CREDENTIAL_MIN_LEN = 6


def check_secrets(repo_name: str, checkout_path: Path) -> list[Finding]:
    """Scan a Subject Repo's checkout for committed secrets (ADR-0007: local only)."""
    findings = []
    for source in _iter_text_files(checkout_path):
        relative = source.relative_to(checkout_path).as_posix()
        for lineno, line in enumerate(source.read_text(errors="replace").splitlines(), 1):
            matched = False
            for kind, pattern, severity in _SECRET_PATTERNS:
                if pattern.search(line):
                    findings.append(
                        _secret_finding(repo_name, kind, severity, relative, lineno))
                    matched = True
            # A high-confidence structural match supersedes the generic key=value
            # rule, so a line like `GITHUB_TOKEN=ghp_...` yields a single finding.
            if not matched and _is_committed_credential(line):
                findings.append(
                    _secret_finding(repo_name, "credential", MEDIUM, relative, lineno))
    return findings


def _secret_finding(repo_name, kind, severity, location, lineno):
    """A security Finding that locates a secret by kind and file:line, never value."""
    return Finding(
        repo=repo_name,
        check_id=SECRETS_CHECK_ID,
        category="security",
        severity=severity,
        evidence=f"Possible {kind} found at {location}:{lineno} (value redacted).",
        location=location,
    )


def _is_committed_credential(line: str) -> bool:
    """Does this line assign a real-looking value to a credential-named key?"""
    match = _CREDENTIAL_ASSIGNMENT.search(line)
    if not match:
        return False
    value = match.group(1).strip()
    if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
        value = value[1:-1].strip()
    if len(value) < _GENERIC_CREDENTIAL_MIN_LEN:
        return False
    # A real secret is a single opaque token; whitespace means prose (a comment
    # or doc note), not a committed credential.
    if any(c.isspace() for c in value):
        return False
    if "${" in value or "{{" in value or (value.startswith("<") and value.endswith(">")):
        return False
    return not _PLACEHOLDER_VALUE.match(value)


def _iter_text_files(checkout_path: Path):
    """Text files under the checkout, in stable sorted order, vendored dirs pruned.

    Binary files are skipped: bytes that happen to match a secret signature are
    noise, not a committed credential.
    """
    for path in sorted(checkout_path.rglob("*")):
        if not path.is_file():
            continue
        if _SKIP_DIRS.intersection(path.relative_to(checkout_path).parts):
            continue
        if _is_binary(path):
            continue
        yield path


# A NUL byte in the leading chunk is the conventional binary-file signal; text
# files (the only place a credential can be committed in readable form) have none.
_BINARY_SNIFF_BYTES = 8192


def _is_binary(path: Path) -> bool:
    """Heuristic: treat a file with a NUL byte in its first chunk as binary."""
    with path.open("rb") as handle:
        return b"\x00" in handle.read(_BINARY_SNIFF_BYTES)


# React's escape hatch that injects raw HTML into the DOM, bypassing JSX's
# automatic escaping. Every use is an XSS surface that must be manually audited,
# so each occurrence is surfaced individually by file:line. Editorial Medium per
# ADR-0004: a real risk, but one that may be deliberate and sanitised upstream.
_DANGEROUS_HTML = re.compile(r"\bdangerouslySetInnerHTML\b")


def check_react_dangerous_html(repo_name: str, checkout_path: Path) -> list[Finding]:
    """Flag dangerouslySetInnerHTML usage in a Subject Repo's front-end source."""
    findings = []
    for source in _iter_source_files(checkout_path):
        relative = source.relative_to(checkout_path).as_posix()
        for lineno, line in enumerate(source.read_text(errors="replace").splitlines(), 1):
            if _DANGEROUS_HTML.search(line):
                findings.append(Finding(
                    repo=repo_name,
                    check_id=REACT_DANGEROUS_HTML_CHECK_ID,
                    category="security",
                    severity=MEDIUM,
                    evidence=(
                        f"dangerouslySetInnerHTML at {relative}:{lineno} injects raw "
                        f"HTML, bypassing JSX escaping (XSS surface to audit)."
                    ),
                    location=relative,
                ))
    return findings


# A string literal containing a SQL DML statement. The verb (and its object, for
# INSERT/DELETE/MERGE) proves the literal is a query rather than incidental prose,
# which keeps the concatenation signal below precise. Word boundaries stop
# "SELECTED"/"UPDATED" from matching.
_SQL_STATEMENT_LITERAL = re.compile(
    r'"[^"]*\b(?:SELECT|INSERT\s+INTO|UPDATE|DELETE\s+FROM|MERGE\s+INTO)\b[^"]*"',
    re.IGNORECASE,
)

# String concatenation: a `+` directly adjacent to a string literal's quote.
# Paired with a SQL-statement literal on the same line, this is the classic
# injection-prone `"... WHERE id = " + var` construction. A parameterised query
# (`"... WHERE id = ?"` with no concatenation) carries no `+` and is not flagged.
_STRING_CONCAT = re.compile(r'"\s*\+|\+\s*"')


def check_sql_string_concat(repo_name: str, checkout_path: Path) -> list[Finding]:
    """Flag SQL queries assembled by string concatenation (injection risk)."""
    findings = []
    for source in _iter_source_files(checkout_path):
        relative = source.relative_to(checkout_path).as_posix()
        for lineno, line in enumerate(source.read_text(errors="replace").splitlines(), 1):
            if _SQL_STATEMENT_LITERAL.search(line) and _STRING_CONCAT.search(line):
                findings.append(Finding(
                    repo=repo_name,
                    check_id=SQL_STRING_CONCAT_CHECK_ID,
                    category="security",
                    severity=HIGH,
                    evidence=(
                        f"SQL query built by string concatenation at "
                        f"{relative}:{lineno} (SQL-injection risk; use a "
                        f"parameterised query)."
                    ),
                    location=relative,
                ))
    return findings


# A directive that switches tests off or narrows the run, so the suite no longer
# exercises what it appears to: JUnit's @Disabled/@Ignore, Jest/Jasmine's
# x-prefixed blocks, and the `.skip`/`.only` modifiers. A committed `.only`
# silently skips the rest of the suite, so it belongs here too.
_DISABLED_TEST = re.compile(
    r"@Disabled\b|@Ignore\b"
    r"|\bxit\b|\bxdescribe\b|\bxtest\b"
    r"|\b(?:it|describe|test)\.(?:skip|only)\b"
)


def check_disabled_tests(repo_name: str, checkout_path: Path) -> list[Finding]:
    """Flag tests that are committed in a disabled, skipped, or focused state."""
    findings = []
    for source in _iter_test_files(checkout_path):
        relative = source.relative_to(checkout_path).as_posix()
        for lineno, line in enumerate(source.read_text(errors="replace").splitlines(), 1):
            match = _DISABLED_TEST.search(line)
            if match:
                findings.append(Finding(
                    repo=repo_name,
                    check_id=DISABLED_TESTS_CHECK_ID,
                    category="testing",
                    severity=MEDIUM,
                    evidence=(
                        f"Disabled/skipped/focused test directive '{match.group(0)}' "
                        f"at {relative}:{lineno}; part of the suite is not exercised."
                    ),
                    location=relative,
                ))
    return findings


# A test case: a JUnit @Test method or a Jest/Jasmine it()/test() block. Disabled
# forms (`xit`, `@Disabled`) are deliberately not matched here — a file whose only
# cases are disabled is the disabled-tests check's concern, not this one.
_TEST_CASE = re.compile(r"@Test\b|\b(?:it|test)\s*\(")

# Any sign a test actually verifies something: a Jest/Chai `expect(`, a JUnit/
# AssertJ `assert…`, a Mockito `verify(`, or a Chai `should`. Read loosely on
# purpose — the goal is to clear files that assert *somehow*, not to grade how.
_ASSERTION = re.compile(r"\bexpect\s*\(|\bassert|\bverify\s*\(|\bshould\b", re.IGNORECASE)


def check_assertion_free_tests(repo_name: str, checkout_path: Path) -> list[Finding]:
    """Flag test files that define test cases but contain no assertions (heuristic)."""
    findings = []
    for source in _iter_test_files(checkout_path):
        text = source.read_text(errors="replace")
        if not _TEST_CASE.search(text) or _ASSERTION.search(text):
            continue
        relative = source.relative_to(checkout_path).as_posix()
        findings.append(Finding(
            repo=repo_name,
            check_id=ASSERTION_FREE_TESTS_CHECK_ID,
            category="testing",
            severity=LOW,
            evidence=(
                f"Test file {relative} defines test case(s) but contains no "
                f"assertion (expect/assert/verify); it may not verify behaviour."
            ),
            location=relative,
        ))
    return findings


def _iter_test_files(checkout_path: Path):
    """Source files that match an ecosystem test-tree convention, in stable order."""
    for source in _iter_source_files(checkout_path):
        if _is_test_signal(source.relative_to(checkout_path).parts):
            yield source


# A single dependency as declared in a manifest.
@dataclass(frozen=True)
class _DeclaredDep:
    coordinate: str  # "group:artifact" (Maven) or package name (npm)
    version: str     # raw version string as declared; may be "" or a ${property}


def check_snapshot_prerelease_deps(repo_name: str, checkout_path: Path) -> list[Finding]:
    """Flag dependencies pinned to a SNAPSHOT or pre-release (alpha/beta/RC) version."""
    findings = []
    for location, deps in _iter_declared_dependencies(checkout_path):
        for dep in deps:
            if _is_prerelease_version(dep.version):
                findings.append(Finding(
                    repo=repo_name,
                    check_id=SNAPSHOT_PRERELEASE_DEPS_CHECK_ID,
                    category="dependencies",
                    severity=MEDIUM,
                    evidence=(
                        f"Dependency {dep.coordinate} pins a SNAPSHOT/pre-release "
                        f"version ({dep.version}); not a reproducible production build."
                    ),
                    location=location,
                ))
    return findings


# A SNAPSHOT or pre-release qualifier (alpha/beta/RC, optionally numbered) on a
# version: `1.2.3-SNAPSHOT`, `2.0.0-beta`, `1.5.0.RC2`. A plain `1.2.3` (or a
# `${property}` reference) is a release pin and is not matched.
_PRERELEASE_VERSION = re.compile(r"(?i)[-.](?:snapshot|alpha|beta|rc)\d*\b")


def _is_prerelease_version(version: str) -> bool:
    """Is this version string a SNAPSHOT or alpha/beta/RC pre-release?"""
    return bool(_PRERELEASE_VERSION.search(version))


def _iter_declared_dependencies(checkout_path: Path):
    """Per dependency manifest under the checkout, its (location, declared deps).

    Maven `pom.xml` and npm `package.json` only; in stable path-sorted order with
    vendored/build dirs pruned. Read purely from the manifest, never resolved or
    fetched (ADR-0007).
    """
    for path in sorted(checkout_path.rglob("*")):
        if not path.is_file():
            continue
        if _SKIP_DIRS.intersection(path.relative_to(checkout_path).parts):
            continue
        location = path.relative_to(checkout_path).as_posix()
        if path.name == "pom.xml":
            yield location, _parse_pom_dependencies(path)
        elif path.name == "package.json":
            yield location, _parse_package_json(path)


def _parse_pom_dependencies(path: Path) -> list[_DeclaredDep]:
    """Dependencies declared in a pom.xml (anywhere a `<dependency>` appears).

    POMs carry the Maven namespace, so elements are matched on their local tag
    name.
    """
    try:
        root = ElementTree.parse(path).getroot()
    except ElementTree.ParseError:
        return []
    deps = []
    for element in root.iter():
        if _local_name(element.tag) != "dependency":
            continue
        group = artifact = version = ""
        for child in element:
            local = _local_name(child.tag)
            text = (child.text or "").strip()
            if local == "groupId":
                group = text
            elif local == "artifactId":
                artifact = text
            elif local == "version":
                version = text
        if not artifact:
            continue
        coordinate = f"{group}:{artifact}" if group else artifact
        deps.append(_DeclaredDep(coordinate=coordinate, version=version))
    return deps


# The npm manifest sections that declare dependencies, in a stable order.
_NPM_DEPENDENCY_BLOCKS = (
    "dependencies",
    "devDependencies",
    "peerDependencies",
    "optionalDependencies",
)


def _parse_package_json(path: Path) -> list[_DeclaredDep]:
    """Dependencies declared across a package.json's dependency sections."""
    try:
        data = json.loads(path.read_text(errors="replace"))
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    deps = []
    for block in _NPM_DEPENDENCY_BLOCKS:
        section = data.get(block)
        if not isinstance(section, dict):
            continue
        for name, version in section.items():
            if not isinstance(version, str):
                continue
            deps.append(_DeclaredDep(coordinate=name, version=version.strip()))
    return deps


def _local_name(tag: str) -> str:
    """The local name of a possibly namespaced XML tag (`{ns}foo` -> `foo`)."""
    return tag.rpartition("}")[2]