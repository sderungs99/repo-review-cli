from repo_review.findings_file import to_json
from repo_review.runner import run_review

SUBSTANTIAL = (
    "This service handles card and SEPA payment capture for the checkout "
    "flow, with retry and idempotency guarantees documented in detail here.\n"
)


def test_runs_readme_check_across_every_subject_repo(make_git_repo, write_manifest, tmp_path):
    good, good_sha = make_git_repo("payments-service", SUBSTANTIAL)
    bare, bare_sha = make_git_repo("auth-service", None)
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
