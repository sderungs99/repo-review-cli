from repo_review.checks import check_sonar_exclusions


def _by_key(findings):
    """Map a finding to its exclusion key via the evidence text, for assertions."""
    return {
        key: f
        for f in findings
        for key in (
            "sonar.exclusions",
            "sonar.coverage.exclusions",
            "sonar.cpd.exclusions",
            "sonar.test.exclusions",
        )
        if f"Sonar {key} " in f.evidence
    }


def test_main_exclusion_in_properties_file_emits_one_high_sonar_integrity_finding(tmp_path):
    (tmp_path / "sonar-project.properties").write_text(
        "sonar.projectKey=payments\n"
        "sonar.exclusions=src/generated/**,**/legacy/**\n"
    )

    findings = check_sonar_exclusions("payments-service", tmp_path)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.repo == "payments-service"
    assert finding.check_id == "sonar-exclusions"
    assert finding.category == "sonar-integrity"
    assert finding.severity == "High"
    assert finding.location == "sonar-project.properties"
    # The excluded patterns are quoted as evidence.
    assert "src/generated/**" in finding.evidence
    assert "**/legacy/**" in finding.evidence


def test_severity_is_graduated_by_how_much_each_exclusion_key_hides(tmp_path):
    (tmp_path / "sonar-project.properties").write_text(
        "sonar.exclusions=**/a/**\n"
        "sonar.coverage.exclusions=**/b/**\n"
        "sonar.cpd.exclusions=**/c/**\n"
        "sonar.test.exclusions=**/d/**\n"
    )

    findings = check_sonar_exclusions("payments-service", tmp_path)

    by_key = _by_key(findings)
    assert len(findings) == 4
    assert by_key["sonar.exclusions"].severity == "High"
    assert by_key["sonar.coverage.exclusions"].severity == "Medium"
    assert by_key["sonar.cpd.exclusions"].severity == "Low"
    assert by_key["sonar.test.exclusions"].severity == "Low"


def test_repo_with_no_sonar_config_emits_no_finding(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "App.java").write_text("class App {}\n")

    assert check_sonar_exclusions("payments-service", tmp_path) == []


def test_sonar_exclusion_property_in_pom_xml_emits_finding(tmp_path):
    # Maven configures Sonar through project properties, under the POM namespace.
    (tmp_path / "pom.xml").write_text(
        '<project xmlns="http://maven.apache.org/POM/4.0.0">\n'
        "  <properties>\n"
        "    <sonar.exclusions>**/generated/**,**/dto/**</sonar.exclusions>\n"
        "    <sonar.coverage.exclusions>**/config/**</sonar.coverage.exclusions>\n"
        "  </properties>\n"
        "</project>\n"
    )

    findings = check_sonar_exclusions("payments-service", tmp_path)

    by_key = _by_key(findings)
    assert len(findings) == 2
    assert by_key["sonar.exclusions"].severity == "High"
    assert by_key["sonar.exclusions"].location == "pom.xml"
    assert "**/generated/**" in by_key["sonar.exclusions"].evidence
    assert by_key["sonar.coverage.exclusions"].severity == "Medium"


def test_sonar_exclusions_in_ado_pipeline_yaml_emit_findings(tmp_path):
    (tmp_path / "azure-pipelines.yml").write_text(
        "steps:\n"
        "  - task: SonarQubePrepare@5\n"
        "    inputs:\n"
        "      extraProperties: |\n"
        "        sonar.exclusions=**/*.generated.java\n"
        "        sonar.coverage.exclusions=**/dto/**\n"
    )

    findings = check_sonar_exclusions("payments-service", tmp_path)

    by_key = _by_key(findings)
    assert len(findings) == 2
    assert by_key["sonar.exclusions"].severity == "High"
    assert by_key["sonar.exclusions"].location == "azure-pipelines.yml"
    assert "**/*.generated.java" in by_key["sonar.exclusions"].evidence
    assert by_key["sonar.coverage.exclusions"].severity == "Medium"


def test_pipeline_yaml_without_a_sonar_task_is_ignored(tmp_path):
    # A property-looking line that is not gated by a SonarQube task must not
    # be mistaken for a Sonar exclusion directive.
    (tmp_path / "azure-pipelines.yml").write_text(
        "steps:\n"
        "  - script: echo sonar.exclusions=**/everything/**\n"
    )

    assert check_sonar_exclusions("payments-service", tmp_path) == []


def test_properties_file_without_any_exclusion_key_emits_no_finding(tmp_path):
    # Sonar is configured, but the vendor has excluded nothing — clean.
    (tmp_path / "sonar-project.properties").write_text(
        "sonar.projectKey=payments\nsonar.sources=src\n"
    )

    assert check_sonar_exclusions("payments-service", tmp_path) == []


def test_sonar_config_inside_a_vendored_dependency_is_ignored(tmp_path):
    # A dependency ships its own Sonar pipeline; it is not the vendor's config.
    vendored = tmp_path / "node_modules" / "some-dep"
    vendored.mkdir(parents=True)
    (vendored / "azure-pipelines.yml").write_text(
        "steps:\n"
        "  - task: SonarQubePrepare@5\n"
        "    inputs:\n"
        "      extraProperties: |\n"
        "        sonar.exclusions=**/everything/**\n"
    )

    assert check_sonar_exclusions("payments-service", tmp_path) == []


def test_findings_are_identical_across_re_runs(tmp_path):
    (tmp_path / "sonar-project.properties").write_text(
        "sonar.exclusions=**/a/**\nsonar.test.exclusions=**/b/**\n"
    )
    (tmp_path / "pom.xml").write_text(
        '<project xmlns="http://maven.apache.org/POM/4.0.0">\n'
        "  <properties><sonar.coverage.exclusions>**/c/**</sonar.coverage.exclusions></properties>\n"
        "</project>\n"
    )

    first = check_sonar_exclusions("payments-service", tmp_path)
    second = check_sonar_exclusions("payments-service", tmp_path)

    assert first == second
    assert len(first) == 3
