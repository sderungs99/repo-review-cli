from repo_review.checks import check_large_files


def test_file_over_threshold_emits_one_code_hygiene_finding(tmp_path):
    # 1001 lines: one past the 1000-LOC threshold.
    (tmp_path / "Big.java").write_text("\n".join("x" for _ in range(1001)) + "\n")

    findings = check_large_files("payments-service", tmp_path)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.repo == "payments-service"
    assert finding.check_id == "large-file"
    assert finding.category == "code-hygiene"
    assert finding.severity == "Low"
    assert finding.location == "Big.java"
    assert "Big.java" in finding.evidence
    assert "1001" in finding.evidence


def test_file_at_exactly_threshold_is_not_flagged(tmp_path):
    # 1000 lines: the threshold must be exceeded, not merely met.
    (tmp_path / "Edge.java").write_text("\n".join("x" for _ in range(1000)) + "\n")

    findings = check_large_files("payments-service", tmp_path)

    assert findings == []


def test_each_oversized_file_is_its_own_finding(tmp_path):
    (tmp_path / "Big.java").write_text("\n".join("x" for _ in range(1001)) + "\n")
    (tmp_path / "Huge.ts").write_text("\n".join("x" for _ in range(1500)) + "\n")
    (tmp_path / "Small.java").write_text("class Small {}\n")

    findings = check_large_files("payments-service", tmp_path)

    assert len(findings) == 2
    assert {f.location for f in findings} == {"Big.java", "Huge.ts"}


def test_file_at_or_over_twice_threshold_is_medium(tmp_path):
    # 2000 lines: a far stronger maintainability signal than a marginal overage.
    (tmp_path / "Monster.java").write_text("\n".join("x" for _ in range(2000)) + "\n")

    findings = check_large_files("payments-service", tmp_path)

    assert len(findings) == 1
    assert findings[0].severity == "Medium"


def test_just_below_twice_threshold_stays_low(tmp_path):
    # 1999 lines: over the threshold but one short of the Medium escalation.
    (tmp_path / "Big.java").write_text("\n".join("x" for _ in range(1999)) + "\n")

    findings = check_large_files("payments-service", tmp_path)

    assert findings[0].severity == "Low"


def test_ignores_non_source_files_and_vendor_dirs(tmp_path):
    huge = "\n".join("x" for _ in range(1500)) + "\n"
    # A large real source file counts.
    (tmp_path / "Big.java").write_text(huge)
    # A large non-source file does not.
    (tmp_path / "GENERATED.md").write_text(huge)
    # A large vendored dependency does not, even in an allowlisted extension.
    vendored = tmp_path / "node_modules" / "dep"
    vendored.mkdir(parents=True)
    (vendored / "bundle.js").write_text(huge)
    # Build output does not either.
    built = tmp_path / "target"
    built.mkdir()
    (built / "Generated.java").write_text(huge)

    findings = check_large_files("payments-service", tmp_path)

    assert len(findings) == 1
    assert findings[0].location == "Big.java"


def test_findings_are_identical_and_path_sorted_across_re_runs(tmp_path):
    huge = "\n".join("x" for _ in range(1001)) + "\n"
    for name in ("Zebra.java", "Alpha.java", "Mid.ts"):
        (tmp_path / name).write_text(huge)

    first = check_large_files("payments-service", tmp_path)
    second = check_large_files("payments-service", tmp_path)

    assert first == second
    assert [f.location for f in first] == ["Alpha.java", "Mid.ts", "Zebra.java"]
