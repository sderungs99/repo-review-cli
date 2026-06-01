import json

from repo_review.cli import main

SUBSTANTIAL = (
    "This service handles card and SEPA payment capture for the checkout "
    "flow, with retry and idempotency guarantees documented in detail here.\n"
)


def test_single_command_writes_findings_file_and_both_reports(
    make_git_repo, write_manifest, tmp_path
):
    good, good_sha = make_git_repo("payments-service", SUBSTANTIAL)
    bare, bare_sha = make_git_repo("auth-service", None)
    manifest = write_manifest(
        [("payments-service", good, good_sha), ("auth-service", bare, bare_sha)]
    )
    out = tmp_path / "out"

    exit_code = main(["--manifest", str(manifest), "--out", str(out)])

    assert exit_code == 0
    findings = json.loads((out / "findings.json").read_text())
    assert [f["repo"] for f in findings] == ["auth-service"]
    technical = (out / "technical-findings-report.md").read_text()
    stakeholder = (out / "stakeholder-report.md").read_text()
    assert "auth-service" in technical
    assert "documentation: 1" in stakeholder


def test_writes_to_reports_dir_by_default_without_out(
    make_git_repo, write_manifest, tmp_path, monkeypatch
):
    bare, bare_sha = make_git_repo("auth-service", None)
    manifest = write_manifest([("auth-service", bare, bare_sha)])
    monkeypatch.chdir(tmp_path)

    exit_code = main(["--manifest", str(manifest)])

    assert exit_code == 0
    assert (tmp_path / "reports" / "findings.json").exists()
    assert (tmp_path / "reports" / "technical-findings-report.md").exists()
    assert (tmp_path / "reports" / "stakeholder-report.md").exists()


def test_output_dir_contains_only_deliverables(make_git_repo, write_manifest, tmp_path):
    bare, bare_sha = make_git_repo("auth-service", None)
    manifest = write_manifest([("auth-service", bare, bare_sha)])
    out = tmp_path / "reports"

    main(["--manifest", str(manifest), "--out", str(out)])

    # No clone working area leaks into the deliverable folder.
    assert sorted(p.name for p in out.iterdir()) == [
        "findings.json",
        "stakeholder-report.md",
        "technical-findings-report.md",
    ]


def test_cli_is_rerunnable_and_deterministic(make_git_repo, write_manifest, tmp_path):
    bare, bare_sha = make_git_repo("auth-service", None)
    manifest = write_manifest([("auth-service", bare, bare_sha)])
    out = tmp_path / "out"

    main(["--manifest", str(manifest), "--out", str(out)])
    first = (out / "findings.json").read_text()
    main(["--manifest", str(manifest), "--out", str(out)])
    second = (out / "findings.json").read_text()

    assert first == second
