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

LAYERING_VIOLATION_CHECK_ID = "layering-violation"

GOD_CLASS_CHECK_ID = "god-class"

SUPPRESSION_DENSITY_CHECK_ID = "suppression-density"

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


# Helper: build the Bearer token pattern with proper quoting.
# Screens out documentation language, template syntax, and short values.
def _compile_bearer_pattern():
    kw = (r"token|authentication|required|reset|scope|scheme|type|header|usage|format")
    tmpl = r"\$\{|\{\{|<.*>"
    # Unquoted token: starts with alnum, at least 8 chars total.
    # Real bearer tokens are long opaque strings; short words like
    # "access", "value", or "my" are prose, not credentials.
    token = r"[a-zA-Z0-9]\S{7,}"
    dquoted = '"' + r"[^\"]{2,}" + '"'  # double-quoted
    squoted = "'" + r"[^']{2,}" + "'"  # single-quoted
    return re.compile(
        r"(?i)Bearer\s+(?!" + kw + r")"
        r"(?!.*(?:" + tmpl + r"))"
        r"(" + token + r"|" + dquoted + r"|" + squoted + r")"
    )

# (kind, compiled pattern, editorial severity). Each entry is a high-confidence
# structural signature for a committed secret; severity is editorial per the kind
# of credential exposed (ADR-0004). The full matched value is never reported —
# only the kind and the file:line locate it.
_SECRET_PATTERNS = [
    # JWT: high-confidence structural m`atch for embedded JSON Web Tokens.
    # JWTs start with eyJ (base64 of {"), have header.payload format.
    # Placed before bearer pattern so JWT finding wins during dedup.
    ("jwt", re.compile(r"(?i)Bearer eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)?"), HIGH),
    ("private key", re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----"), CRITICAL),
    ("AWS access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), HIGH),
    ("GitHub token", re.compile(r"\bgh[pousr]_[0-9A-Za-z]{36}\b"), HIGH),
    ("Slack token", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b"), HIGH),
    ("bearer token", _compile_bearer_pattern(), HIGH),
]

# A config assignment whose key names a credential, capturing the assigned value.
# Matched case-insensitively on the keyword sitting immediately before the `=`/`:`
# separator, so apiKey / api_key / API_KEY all qualify but an unrelated key does
# not. Severity is Medium: the key proves intent but the value is unverifiable.
_CREDENTIAL_ASSIGNMENT = re.compile(
    r"(?i)(?<![a-zA-Z])(?:password|passwd|pwd|secret|api[_-]?key|apikey|"
    r"access[_-]?key|access[_-]?token|token)\s*[:=]\s*(.+)$"
)

# Values that are plainly not a committed secret: a known placeholder word or a
# `your_..._here`-style template. Interpolations (${...}, {{...}}, <...>) and
# too-short values are screened separately.
_PLACEHOLDER_VALUE = re.compile(
    r"(?i)^(?:change[-_]?me|password|secret|example|sample|test|dummy|"
    r"none|null|todo|tbd|x+|\*+|your[_-].*"
    r"|string|number|boolean|void|any|never|unknown|bigint|symbol"
    r")$"
)

# Below this length a captured value carries too little signal to be a real
# credential, so it is not flagged (screens empties and trivial stubs).
_GENERIC_CREDENTIAL_MIN_LEN = 6

# Values that are plainly code references, not committed secrets. A real
# credential is a literal value (string, number, etc.); method calls, field
# accesses, and statement-terminated expressions are references, not secrets.
_CODE_REFERENCE_RE = re.compile(
    r"(?i)"                          # case-insensitive
    r".*\(.*\)"                      # contains parens → method/constructor call
    r"|\S+\.\S+"                     # dot notation → object access
    r"|;"                            # semicolon → statement terminator (Java/TS/C)
    r"|\b(null|undefined|None)\b"     # language null values (whole-word)
)

# TypeScript/JS type annotations that look like single-word values.
# Matches keywords (string, Buffer), generics (Array<T>), and unions
# (string | null). These are type declarations, not committed credentials.
_TYPE_ANNOTATION_RE = re.compile(
    r"(?i)"
    r"^(?:"
    r"string|number|boolean|void|null|undefined|never|any|unknown|bigint|symbol|"
    r"Buffer|Object|Array|Map|Set|Promise|Record|Partial|Readonly|"
    r"Required|Iterator|AsyncIterator|Function|RegExp|Date|Error|"
    r"SetTimeoutCallback|NodeJS|GlobalThis"
    r")"
    r"(?:\s*<[^>]+>)?"                          # optional generics
    r"(?:\s*\|[^|]+)*$"                          # optional union parts
)

# Alias for the calling convention — we use .search() so embedded patterns
# (like a trailing semicolon) are detected regardless of position.
def _is_code_reference(value: str) -> bool:
    return bool(_CODE_REFERENCE_RE.search(value))


# Auth-related method names whose calls with hardcoded string arguments signal
# deliberate misuse of credentials. Single-line regex — no cross-line variable
# tracking (that would require AST-level analysis, out of scope for a throwaway).
_AUTH_METHOD_RE = re.compile(
    r"\b(?:setToken|withToken|withAuth|authenticate|setApiKey)\s*\(\s*(?:['\"][^'\"]*['\"]\s*)\)"
)


def _detect_function_call_secrets(
    repo_name: str, checkout_path: Path
) -> list[Finding]:
    """Detect auth-related method calls with hardcoded credential values.

    Scans for calls like setToken("abc") or withAuth('xyz') in Java/JS/TS source.
    Each occurrence is a separate finding at file:line.
    """
    findings = []
    for source in _iter_text_files(checkout_path):
        relative = source.relative_to(checkout_path).as_posix()
        for lineno, line in enumerate(source.read_text(errors="replace").splitlines(), 1):
            if _AUTH_METHOD_RE.search(line):
                findings.append(
                    Finding(
                        repo=repo_name,
                        check_id=SECRETS_CHECK_ID,
                        category="security",
                        severity=HIGH,
                        evidence=f"Possible hardcoded auth credential in method call at {relative}:{lineno}.",
                        location=relative,
                    ))
    return findings


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
                    break  # highest-priority structural match wins (e.g. JWT over Bearer)
            # A high-confidence structural match supersedes the generic key=value
            # rule, so a line like `GITHUB_TOKEN=ghp_...` yields a single finding.
            if not matched and _is_committed_credential(line):
                findings.append(
                    _secret_finding(repo_name, "credential", MEDIUM, relative, lineno))
    # Function-call detection catches auth-method calls with hardcoded values.
    # Runs after the per-line pass; results merged into findings.
    findings.extend(_detect_function_call_secrets(repo_name, checkout_path))
    # Stable sort by location then line number (embedded in evidence for fn-call findings).
    return sorted(findings, key=lambda f: (f.location, _lineno_from_finding(f)))


def _lineno_from_finding(f: Finding) -> int:
    """Extract line number from a finding's evidence for sorting."""
    import re as _re
    # Structural: '...at file:42 (value redacted).'
    m = _re.search(r"at\s+\S+?(\d+)\s*\(value redacted", f.evidence)
    if m:
        return int(m.group(1))
    # Function-call: '...at file:17.'
    m = _re.search(r"at\s+\S+?(\d+)\.$", f.evidence)
    if m:
        return int(m.group(1))
    return 0


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
    # Strip trailing semicolons — they are statement terminators in Java/TS/C,
    # not part of the value. Handles both quoted ("val"; → "val") and
    # unquoted (string; → string) cases.
    value = value.rstrip("; ").rstrip()
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
    if _is_code_reference(value):
        return False
    if _TYPE_ANNOTATION_RE.match(value):
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

# A SQL literal concatenated with a non-literal operand: a variable, method call,
# or parenthesised expression (`"...sql..." + id`, `table + "...sql..."`). This is
# the injection-prone construction. Concatenation of string literals only
# (`"..." + "..."`, a split constant) cannot carry runtime input, so it does not
# match; a parameterised query (`"... = ?"`) carries no `+` and does not match.
_CONCAT_WITH_VARIABLE = re.compile(r'"\s*\+\s*[^"\s]|[^"\s]\s*\+\s*"')

# A query-defining JPA/Hibernate annotation. Concatenation inside its argument is
# never an injection risk: a Java annotation argument must be a constant
# expression, so the `+` can only join compile-time constants — runtime input
# cannot reach the string, and real inputs bind through :named/?n parameters.
_QUERY_ANNOTATION = re.compile(r"@(?:Query|NamedQuery|NamedNativeQuery)\b")

# A line that prints or reports SQL rather than executes it: a logger call, a
# System.out/err write, or a thrown exception's message. A query string built in
# one of these is not handed to the database, so it is not an injection sink.
_LOG_OR_THROW = re.compile(
    r"\b(?:log|logger|logging)\s*\.|\bSystem\.(?:out|err)\b|\bthrow\b",
    re.IGNORECASE,
)


def check_sql_string_concat(repo_name: str, checkout_path: Path) -> list[Finding]:
    """Flag SQL queries assembled by string concatenation (injection risk)."""
    findings = []
    for source in _iter_source_files(checkout_path):
        # Test code builds expected-query strings, not runtime sinks (selected
        # FP filter — see DEVELOPER_NOTES.md).
        if _is_test_signal(source.relative_to(checkout_path).parts):
            continue
        relative = source.relative_to(checkout_path).as_posix()
        for lineno, line in enumerate(source.read_text(errors="replace").splitlines(), 1):
            if _QUERY_ANNOTATION.search(line) or _LOG_OR_THROW.search(line):
                continue
            if _SQL_STATEMENT_LITERAL.search(line) and _CONCAT_WITH_VARIABLE.search(line):
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


# A Spring web layer: a class annotated @Controller or @RestController. Such a
# class is meant to delegate to a service, not reach into persistence itself.
_CONTROLLER_ANNOTATION = re.compile(r"@(?:Rest)?Controller\b")

# A dependency on a repository type, recognised by Spring's `*Repository` naming
# convention used as the type of a field or constructor parameter
# (`OrderRepository orders`). The capture is the repository type name.
_REPOSITORY_DEPENDENCY = re.compile(r"\b([A-Z]\w*Repository)\s+[a-z_]\w*")


def check_layering_violation(repo_name: str, checkout_path: Path) -> list[Finding]:
    """Flag Spring controllers that depend directly on a repository (skip the service layer)."""
    findings = []
    for source in _iter_java_files(checkout_path):
        text = source.read_text(errors="replace")
        if not _CONTROLLER_ANNOTATION.search(text):
            continue
        repositories = sorted({m.group(1) for m in _REPOSITORY_DEPENDENCY.finditer(text)})
        if not repositories:
            continue
        relative = source.relative_to(checkout_path).as_posix()
        findings.append(Finding(
            repo=repo_name,
            check_id=LAYERING_VIOLATION_CHECK_ID,
            category="architecture",
            severity=MEDIUM,
            evidence=(
                f"Controller {relative} depends directly on repository type(s) "
                f"{', '.join(repositories)}, bypassing the service layer."
            ),
            location=relative,
        ))
    return findings


# An injected collaborator: a field annotated @Autowired (field injection) or a
# `private/protected final ReferenceType name;` field (constructor injection). A
# high count of these is the over-injection signal of a god class. Primitive-typed
# final fields (constants) start lower-case after `final` and are not matched.
_INJECTED_DEPENDENCY = re.compile(
    r"@Autowired\b"
    r"|\b(?:private|protected)\s+final\s+[A-Z]\w*(?:<[^>]*>)?\s+\w+\s*;"
)

# At or above this many injected dependencies, a class is carrying too many
# collaborators (high fan-in) to hold a single responsibility. Hardcoded
# editorial threshold per ADR-0004.
GOD_CLASS_DEPENDENCY_THRESHOLD = 10


def check_god_class(repo_name: str, checkout_path: Path) -> list[Finding]:
    """Flag classes with an excessive number of injected dependencies (high fan-in)."""
    findings = []
    for source in _iter_java_files(checkout_path):
        text = source.read_text(errors="replace")
        count = len(_INJECTED_DEPENDENCY.findall(text))
        if count < GOD_CLASS_DEPENDENCY_THRESHOLD:
            continue
        relative = source.relative_to(checkout_path).as_posix()
        findings.append(Finding(
            repo=repo_name,
            check_id=GOD_CLASS_CHECK_ID,
            category="architecture",
            severity=MEDIUM,
            evidence=(
                f"{relative} injects {count} dependencies (threshold "
                f"{GOD_CLASS_DEPENDENCY_THRESHOLD}); high fan-in suggests a god "
                f"class with too many responsibilities."
            ),
            location=relative,
        ))
    return findings


# A suppression directive that silences a static-analysis or compiler warning:
# ESLint disables, TypeScript ignore/expect-error/nocheck pragmas, and Java's
# @SuppressWarnings. Each is a deliberately hidden warning to account for.
_SUPPRESSION_DIRECTIVE = re.compile(
    r"eslint-disable\b|@ts-(?:ignore|expect-error|nocheck)\b|@SuppressWarnings\b"
)

# At or above this many suppressions, silencing warnings is a pervasive habit
# rather than the odd justified exception, so the finding escalates to Medium.
SUPPRESSION_DENSE_THRESHOLD = 25

# How many file:line locations to quote as a representative sample.
SUPPRESSION_SAMPLE_LIMIT = 5


def check_suppression_density(repo_name: str, checkout_path: Path) -> list[Finding]:
    """Count warning-suppression directives across a Subject Repo's source files."""
    locations = []
    for source in _iter_source_files(checkout_path):
        relative = source.relative_to(checkout_path).as_posix()
        for lineno, line in enumerate(source.read_text(errors="replace").splitlines(), 1):
            if _SUPPRESSION_DIRECTIVE.search(line):
                locations.append(f"{relative}:{lineno}")

    count = len(locations)
    if count == 0:
        return []

    sample = ", ".join(locations[:SUPPRESSION_SAMPLE_LIMIT])
    severity = MEDIUM if count >= SUPPRESSION_DENSE_THRESHOLD else LOW
    return [Finding(
        repo=repo_name,
        check_id=SUPPRESSION_DENSITY_CHECK_ID,
        category="code-hygiene",
        severity=severity,
        evidence=(
            f"Found {count} warning-suppression directive(s) (eslint-disable / "
            f"@ts-ignore / @SuppressWarnings) across source files. "
            f"Sample locations: {sample}."
        ),
        location=".",
    )]


def _iter_java_files(checkout_path: Path):
    """Java source files under the checkout, in stable order, vendored dirs pruned."""
    for source in _iter_source_files(checkout_path):
        if source.suffix == ".java":
            yield source

# ── Project detection ───────────────────────────────────────────────────────

# Manifest files that identify a Subject Repo as Java or JavaScript/TypeScript.
_PROJECT_KIND_FILES = ("pom.xml", "build.gradle", "package.json")


def is_project(path: Path) -> bool:
    """Does the checkout contain a Java or JS/TS project manifest?"""
    return any((path / f).is_file() for f in _PROJECT_KIND_FILES)


# ── Directory file density check ────────────────────────────────────────────

DIRECTORY_FILE_DENSITY_CHECK_ID = "directory-file-density"

# Directories with more source files than this are flagged as a density concern.
DIRECTORY_FILE_DENSITY_THRESHOLD = 10

# Source-root directories to scan, depending on project kind.
_JAVA_SOURCE_ROOT = "src/main/java"
_JAVASCRIPT_SOURCE_ROOT = "src"


def check_directory_file_density(
    repo_name: str, checkout_path: Path
) -> list[Finding]:
    """Flag directories that contain more source files than the threshold."""
    if not is_project(checkout_path):
        return []

    findings: list[Finding] = []
    source_roots = _source_roots_for(checkout_path)

    for root_dir in source_roots:
        if not root_dir.is_dir():
            continue
        for dir_path in _iter_all_directories(root_dir):
            count = sum(
                1
                for f in dir_path.iterdir()
                if f.is_file() and f.suffix in _SOURCE_SUFFIXES
            )
            if count > DIRECTORY_FILE_DENSITY_THRESHOLD:
                relative = dir_path.relative_to(checkout_path).as_posix()
                findings.append(Finding(
                    repo=repo_name,
                    check_id=DIRECTORY_FILE_DENSITY_CHECK_ID,
                    category="code-hygiene",
                    severity=MEDIUM,
                    evidence=(
                        f"{relative} ({count} files, limit "
                        f"{DIRECTORY_FILE_DENSITY_THRESHOLD})."
                    ),
                    location=".",
                ))

    return findings


def _source_roots_for(checkout_path: Path) -> list[Path]:
    """Return the source-root directories to scan.

    Java projects scan **all** ``src/main/java`` and ``src/test/java``
    directories under the checkout (to handle multi-module Maven/Gradle
    projects).  JS/TS projects scan all ``src`` directories (to handle
    monorepos).
    """
    if (checkout_path / "pom.xml").is_file() or \
       (checkout_path / "build.gradle").is_file():
        roots: set[Path] = set()
        roots.update(checkout_path.rglob("src/main/java"))
        roots.update(checkout_path.rglob("src/test/java"))
        return sorted(roots, key=lambda p: len(p.parts))
    if (checkout_path / "package.json").is_file():
        return sorted(
            checkout_path.rglob(_JAVASCRIPT_SOURCE_ROOT),
            key=lambda p: len(p.parts),
        )
    return []


def _iter_all_directories(start: Path):
    """Yield every directory under ``start`` in depth-first order, pruning vendor dirs."""
    yield start
    for child in sorted(start.iterdir()):
        if child.is_dir() and child.name not in _SKIP_DIRS:
            yield from _iter_all_directories(child)


# ── Excessive package nesting check ─────────────────────────────────────────

EXCESSIVE_PACKAGE_NESTING_CHECK_ID = "excessive-package-nesting"

# Package nesting deeper than this from the Actual Root is flagged.
EXCESSIVE_PACKAGE_NESTING_THRESHOLD = 4


def check_excessive_package_nesting(
    repo_name: str, checkout_path: Path
) -> list[Finding]:
    """Flag if source files exceed the nesting depth threshold from the Actual Root."""
    if not is_project(checkout_path):
        return []

    source_roots = _source_roots_for(checkout_path)
    if not source_roots:
        return []

    max_depth = -1
    deepest_path: Path | None = None

    # Measure depth from the actual root of each source root (important for
    # monorepos). The actual root is the shallowest non-empty directory.
    for root in source_roots:
        actual_root = _find_actual_root(root)
        if actual_root is None:
            continue
        for source in _iter_source_files(actual_root):
            depth = len(source.relative_to(actual_root).parts)
            if depth > max_depth:
                max_depth = depth
                deepest_path = source

    if max_depth > EXCESSIVE_PACKAGE_NESTING_THRESHOLD and deepest_path is not None:
        relative = deepest_path.relative_to(checkout_path).as_posix()
        return [Finding(
            repo=repo_name,
            check_id=EXCESSIVE_PACKAGE_NESTING_CHECK_ID,
            category="code-hygiene",
            severity=MEDIUM,
            evidence=(
                f"deepest {max_depth} levels at {relative} "
                f"(threshold {EXCESSIVE_PACKAGE_NESTING_THRESHOLD})."
            ),
            location=".",
        )]

    return []


def _find_actual_root(start: Path) -> Path | None:
    """The first meaningful directory *under* ``start``.

    Searches in two passes (top-down, BFS):

    1. **Branching root** — first directory with more than one subdirectory
       (the real package root, e.g. ``entitlement`` has ``model`` + ``entity``).
    2. **Flat fallback** — first directory with source files (for flat projects
       that have no package hierarchy).

    Returns the first branching root found, or the flat fallback, or ``None``.
    """
    if not start.is_dir():
        return None

    def _has_source_files(dir_path: Path) -> bool:
        return any(
            f.is_file() and f.suffix in _SOURCE_SUFFIXES
            for f in _iter_source_files(dir_path)
        )

    def _bfs_find(visit_fn) -> Path | None:
        """BFS, returning the first directory that satisfies ``visit_fn``."""
        queue = sorted(
            (c for c in start.iterdir() if c.is_dir() and c.name not in _SKIP_DIRS),
            key=lambda p: p.name,
        )
        visited: set[Path] = set(queue)

        while queue:
            next_queue: list[Path] = []
            for candidate in queue:
                if visit_fn(candidate):
                    return candidate
                for child in sorted(candidate.iterdir(), key=lambda p: p.name):
                    if child.is_dir() and child.name not in _SKIP_DIRS and child not in visited:
                        visited.add(child)
                        next_queue.append(child)
            queue = next_queue
        return None

    # Pass 1: find the first branching directory (>1 subdirectory).
    branching = _bfs_find(
        lambda c: len([
            ch for ch in c.iterdir()
            if ch.is_dir() and ch.name not in _SKIP_DIRS
        ]) > 1
    )
    if branching is not None:
        return branching

    # Pass 2: flat fallback — first directory with source files.
    return _bfs_find(_has_source_files)


# ── Unused dependency check (npm / React) ───────────────────────────────────

UNUSED_DEPENDENCY_CHECK_ID = "unused-dependency"

# A module specifier in an import/require/re-export: the quoted string after a
# `from` clause (`import x from 'pkg'`, `export … from 'pkg'`), a side-effect
# `import 'pkg'`, a dynamic `import('pkg')`, or a `require('pkg')`. Captures the
# specifier itself, e.g. 'lodash', '@scope/pkg/sub', './local'. `\(?` covers the
# parenthesised require/dynamic-import forms; the `from`/side-effect forms have none.
_IMPORT_SPECIFIER = re.compile(
    r"""\b(?:from|import|require)\b\s*\(?\s*['"]([^'"\n]+)['"]"""
)


def check_unused_dependencies(repo_name: str, checkout_path: Path) -> list[Finding]:
    """Flag npm runtime dependencies that are never imported in the source.

    Scope is the React/JS ecosystem only — an npm package name maps directly to
    its import specifier, so "declared but never imported" is a high-confidence
    signal. Only the runtime ``dependencies`` block is checked (devDependencies
    are build/test tooling that is legitimately not imported), and ``@types/*``
    packages are skipped because TypeScript consumes them without an import.

    Maven is deliberately out of scope: a groupId/artifactId does not map to a
    Java import package, so unused-dependency detection there needs bytecode
    analysis, which the source-only model forbids (ADR-0007).
    """
    findings = []
    for path in sorted(checkout_path.rglob("package.json")):
        if _SKIP_DIRS.intersection(path.relative_to(checkout_path).parts):
            continue
        dependencies = _runtime_dependencies(path)
        if not dependencies:
            continue
        imported = _imported_packages(path.parent)
        location = path.relative_to(checkout_path).as_posix()
        for name in dependencies:
            if name.startswith("@types/") or name in imported:
                continue
            findings.append(Finding(
                repo=repo_name,
                check_id=UNUSED_DEPENDENCY_CHECK_ID,
                category="dependencies",
                severity=LOW,
                evidence=(
                    f"Dependency '{name}' is declared in {location} but never "
                    f"imported in the source (no import/require found); it may be "
                    f"redundant. Verify it is not pulled in via build config or "
                    f"as a runtime polyfill."
                ),
                location=location,
            ))
    return findings


def _runtime_dependencies(path: Path) -> list[str]:
    """Package names in a package.json's runtime ``dependencies`` block, in order."""
    try:
        data = json.loads(path.read_text(errors="replace"))
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    section = data.get("dependencies")
    if not isinstance(section, dict):
        return []
    return [name for name, version in section.items() if isinstance(version, str)]


def _imported_packages(root: Path) -> set[str]:
    """Every npm package imported anywhere in the source tree under ``root``.

    Scanning the whole subtree (tests included) is deliberately lenient: an
    import found anywhere clears the dependency, so the check only flags a
    package with no import at all — it never reports a used one.
    """
    packages = set()
    for source in _iter_source_files(root):
        text = source.read_text(errors="replace")
        for match in _IMPORT_SPECIFIER.finditer(text):
            package = _imported_package(match.group(1))
            if package is not None:
                packages.add(package)
    return packages


def _imported_package(specifier: str) -> str | None:
    """The package name a module specifier resolves to, or ``None`` if it is local.

    `lodash/fp` -> `lodash`; `@scope/pkg/sub` -> `@scope/pkg`; a relative or
    absolute path (`./x`, `/x`) is not a package and yields ``None``.
    """
    if not specifier or specifier[0] in "./":
        return None
    parts = specifier.split("/")
    if specifier.startswith("@"):
        return "/".join(parts[:2]) if len(parts) >= 2 else None
    return parts[0]