from repo_review.checks import check_todo_markers


def test_single_todo_in_source_emits_one_code_hygiene_finding(tmp_path):
    (tmp_path / "Service.java").write_text(
        "class Service {\n    // TODO: handle retries\n}\n"
    )

    findings = check_todo_markers("payments-service", tmp_path)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.repo == "payments-service"
    assert finding.check_id == "todo-markers"
    assert finding.category == "code-hygiene"
    assert finding.severity == "Info"
    assert "1" in finding.evidence


def test_clean_source_tree_emits_no_finding(tmp_path):
    (tmp_path / "Service.java").write_text(
        "class Service {\n    int retries = 3;\n}\n"
    )

    findings = check_todo_markers("payments-service", tmp_path)

    assert findings == []


def test_counts_every_marker_kind_across_files_case_insensitively(tmp_path):
    (tmp_path / "A.java").write_text(
        "// TODO: one\n"
        "/* FIXME: two */\n"
        "    // hack: lowercase still counts\n"
    )
    (tmp_path / "B.ts").write_text(
        "const x = 1; // FixMe: mixed case\n"
    )

    findings = check_todo_markers("payments-service", tmp_path)

    assert len(findings) == 1
    assert "4" in findings[0].evidence


def test_large_marker_pile_is_low_severity(tmp_path):
    (tmp_path / "A.java").write_text("\n".join("// TODO" for _ in range(50)) + "\n")

    findings = check_todo_markers("payments-service", tmp_path)

    assert len(findings) == 1
    assert findings[0].severity == "Low"


def test_just_below_threshold_stays_info(tmp_path):
    (tmp_path / "A.java").write_text("\n".join("// TODO" for _ in range(49)) + "\n")

    findings = check_todo_markers("payments-service", tmp_path)

    assert findings[0].severity == "Info"


def test_evidence_includes_sample_file_line_locations(tmp_path):
    (tmp_path / "A.java").write_text("class A {}\n// TODO: line two\n")

    findings = check_todo_markers("payments-service", tmp_path)

    assert "A.java:2" in findings[0].evidence


def test_sample_locations_are_capped(tmp_path):
    # Twelve markers on lines 1..12; only the first five locations are sampled.
    (tmp_path / "A.java").write_text("\n".join("// TODO" for _ in range(12)) + "\n")

    findings = check_todo_markers("payments-service", tmp_path)

    evidence = findings[0].evidence
    assert "A.java:5" in evidence
    assert "A.java:6" not in evidence
    assert "12" in evidence  # the full count is still reported


def test_ignores_non_source_files_and_vendor_dirs(tmp_path):
    # A marker in real source counts.
    (tmp_path / "A.java").write_text("// TODO: real\n")
    # Markers in non-source files do not.
    (tmp_path / "README.md").write_text("<!-- TODO: docs marker -->\n")
    # Markers in vendored dependencies do not, even in allowlisted extensions.
    vendored = tmp_path / "node_modules" / "dep"
    vendored.mkdir(parents=True)
    (vendored / "index.js").write_text("// TODO: not our code\n")
    built = tmp_path / "target"
    built.mkdir()
    (built / "Generated.java").write_text("// TODO: generated\n")

    findings = check_todo_markers("payments-service", tmp_path)

    assert len(findings) == 1
    assert "1 TODO" in findings[0].evidence
    assert "A.java:1" in findings[0].evidence


def test_marker_only_counts_inside_a_comment(tmp_path):
    (tmp_path / "A.ts").write_text(
        'const label = "TODO list feature";\n'  # line 1: string literal, not a marker
        "// TODO: this one is a real marker\n"   # line 2: a real comment marker
    )

    findings = check_todo_markers("payments-service", tmp_path)

    assert len(findings) == 1
    assert "1 TODO" in findings[0].evidence
    assert "A.ts:2" in findings[0].evidence


def test_findings_are_identical_across_re_runs(tmp_path):
    for name in ("Zebra.java", "Alpha.java", "Mid.ts"):
        (tmp_path / name).write_text("// TODO: marker\n")

    first = check_todo_markers("payments-service", tmp_path)
    second = check_todo_markers("payments-service", tmp_path)

    assert first == second
    # Sample locations are quoted in stable, path-sorted order.
    assert "Alpha.java:1, Mid.ts:1, Zebra.java:1" in first[0].evidence
