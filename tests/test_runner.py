from repo_review.findings_file import to_json
from repo_review.runner import run_review

SUBSTANTIAL = (
    "This service handles card and SEPA payment capture for the checkout "
    "flow, with retry and idempotency guarantees documented in detail here.\n"
)

# A minimal test-tree signal, so the tests-present check stays silent and these
# tests stay focused on the single check each is exercising.
HAS_TESTS = {"App.test.js": "it('renders', () => {});\n"}


def test_runs_readme_check_across_every_subject_repo(make_git_repo, write_manifest, tmp_path):
    good, good_sha = make_git_repo("payments-service", SUBSTANTIAL, extra_files=HAS_TESTS)
    bare, bare_sha = make_git_repo("auth-service", None, extra_files=HAS_TESTS)
    manifest = write_manifest(
        [("payments-service", good, good_sha), ("auth-service", bare, bare_sha)]
    )

    findings = run_review(manifest, tmp_path / "work1")

    # Only the repo with no README produces a finding.
    assert len(findings) == 1
    assert findings[0].repo == "auth-service"
    assert findings[0].category == "documentation"


def test_two_runs_over_the_same_manifest_are_byte_identical(make_git_repo, write_manifest, tmp_path):
    good, good_sha = make_git_repo("payments-service", SUBSTANTIAL)
    bare, bare_sha = make_git_repo("auth-service", None)
    manifest = write_manifest(
        [("payments-service", good, good_sha), ("auth-service", bare, bare_sha)]
    )

    first = to_json(run_review(manifest, tmp_path / "work1"))
    second = to_json(run_review(manifest, tmp_path / "work2"))

    assert first == second


def test_runs_todo_marker_check_across_every_subject_repo(make_git_repo, write_manifest, tmp_path):
    path, sha = make_git_repo(
        "payments-service",
        SUBSTANTIAL,
        extra_files={"Service.java": "class Service {\n    // TODO: handle retries\n}\n", **HAS_TESTS},
    )
    manifest = write_manifest([("payments-service", path, sha)])

    findings = run_review(manifest, tmp_path / "work1")

    # README is substantial, so the only finding is the TODO marker.
    assert len(findings) == 1
    assert findings[0].check_id == "todo-markers"
    assert findings[0].category == "code-hygiene"


def test_runs_large_file_check_across_every_subject_repo(make_git_repo, write_manifest, tmp_path):
    huge = "\n".join("x" for _ in range(1001)) + "\n"
    path, sha = make_git_repo(
        "payments-service", SUBSTANTIAL, extra_files={"Big.java": huge, **HAS_TESTS}
    )
    manifest = write_manifest([("payments-service", path, sha)])

    findings = run_review(manifest, tmp_path / "work1")

    # README is substantial, so the only finding is the oversized file.
    assert len(findings) == 1
    assert findings[0].check_id == "large-file"
    assert findings[0].location == "Big.java"


def test_runs_tests_present_check_across_every_subject_repo(make_git_repo, write_manifest, tmp_path):
    # Substantial README, no source markers, but no test tree either.
    path, sha = make_git_repo(
        "payments-service",
        SUBSTANTIAL,
        extra_files={"Service.java": "class Service {}\n"},
    )
    manifest = write_manifest([("payments-service", path, sha)])

    findings = run_review(manifest, tmp_path / "work1")

    assert len(findings) == 1
    assert findings[0].check_id == "tests-present"
    assert findings[0].category == "testing"


def test_runs_sonar_exclusions_check_across_every_subject_repo(make_git_repo, write_manifest, tmp_path):
    path, sha = make_git_repo(
        "payments-service",
        SUBSTANTIAL,
        extra_files={
            "sonar-project.properties": "sonar.exclusions=src/generated/**\n",
            **HAS_TESTS,
        },
    )
    manifest = write_manifest([("payments-service", path, sha)])

    findings = run_review(manifest, tmp_path / "work1")

    # README is substantial and tests are present, so the only finding is the
    # Sonar exclusion — and it survives the round-trip into the Findings File.
    assert len(findings) == 1
    assert findings[0].check_id == "sonar-exclusions"
    assert findings[0].category == "sonar-integrity"
    assert '"sonar-integrity"' in to_json(findings)


def test_runs_secret_scanning_check_across_every_subject_repo(make_git_repo, write_manifest, tmp_path):
    path, sha = make_git_repo(
        "payments-service",
        SUBSTANTIAL,
        extra_files={
            ".env": "GITHUB_TOKEN=ghp_0123456789abcdefABCDEF0123456789abcd\n",
            **HAS_TESTS,
        },
    )
    manifest = write_manifest([("payments-service", path, sha)])

    findings = run_review(manifest, tmp_path / "work1")

    # README is substantial and tests are present, so the only finding is the
    # committed secret — and it survives the round-trip into the Findings File.
    assert len(findings) == 1
    assert findings[0].check_id == "secret-scanning"
    assert findings[0].category == "security"
    assert '"security"' in to_json(findings)
