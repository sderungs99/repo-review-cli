from repo_review.checks import check_suppression_density, SUPPRESSION_DENSE_THRESHOLD


def test_single_suppression_emits_one_low_code_hygiene_finding(tmp_path):
    (tmp_path / "Service.java").write_text(
        "@SuppressWarnings(\"unchecked\")\npublic void run() {}\n"
    )

    findings = check_suppression_density("payments-service", tmp_path)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.repo == "payments-service"
    assert finding.check_id == "suppression-density"
    assert finding.category == "code-hygiene"
    assert finding.severity == "Low"
    assert "1" in finding.evidence


def test_clean_source_tree_emits_no_finding(tmp_path):
    (tmp_path / "Service.java").write_text("public void run() {}\n")

    assert check_suppression_density("payments-service", tmp_path) == []


def test_counts_eslint_and_ts_and_java_directives_across_files(tmp_path):
    (tmp_path / "a.ts").write_text(
        "// eslint-disable-next-line no-console\n"
        "// @ts-ignore\nconst x = 1;\n"
    )
    (tmp_path / "B.java").write_text('@SuppressWarnings("rawtypes")\nvoid f() {}\n')

    findings = check_suppression_density("payments-service", tmp_path)

    assert len(findings) == 1
    assert "3" in findings[0].evidence


def test_dense_suppressions_escalate_to_medium(tmp_path):
    lines = "\n".join("// eslint-disable-line" for _ in range(SUPPRESSION_DENSE_THRESHOLD))
    (tmp_path / "a.ts").write_text(lines + "\n")

    findings = check_suppression_density("payments-service", tmp_path)

    assert len(findings) == 1
    assert findings[0].severity == "Medium"


def test_just_below_dense_threshold_stays_low(tmp_path):
    lines = "\n".join("// eslint-disable-line" for _ in range(SUPPRESSION_DENSE_THRESHOLD - 1))
    (tmp_path / "a.ts").write_text(lines + "\n")

    findings = check_suppression_density("payments-service", tmp_path)

    assert findings[0].severity == "Low"


def test_evidence_includes_sample_locations_and_ignores_vendor_dirs(tmp_path):
    (tmp_path / "a.ts").write_text("// @ts-nocheck\nconst x = 1;\n")
    vendored = tmp_path / "node_modules" / "dep"
    vendored.mkdir(parents=True)
    (vendored / "index.js").write_text("/* eslint-disable */\n")

    findings = check_suppression_density("payments-service", tmp_path)

    assert len(findings) == 1
    assert "a.ts:1" in findings[0].evidence


def test_findings_are_identical_across_re_runs(tmp_path):
    for name in ("Zebra.ts", "Alpha.ts"):
        (tmp_path / name).write_text("// @ts-ignore\nconst x = 1;\n")

    first = check_suppression_density("payments-service", tmp_path)
    second = check_suppression_density("payments-service", tmp_path)

    assert first == second
    assert "Alpha.ts:1, Zebra.ts:1" in first[0].evidence
