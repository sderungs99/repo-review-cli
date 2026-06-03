from repo_review.checks import check_snapshot_prerelease_deps

POM_HEAD = '<project xmlns="http://maven.apache.org/POM/4.0.0">\n'


def _pom(*dependencies: str) -> str:
    inner = "\n".join(dependencies)
    return (
        POM_HEAD
        + "  <dependencies>\n"
        + inner
        + "\n  </dependencies>\n</project>\n"
    )


def _dep(group: str, artifact: str, version: str) -> str:
    return (
        "    <dependency>\n"
        f"      <groupId>{group}</groupId>\n"
        f"      <artifactId>{artifact}</artifactId>\n"
        f"      <version>{version}</version>\n"
        "    </dependency>"
    )


def test_maven_snapshot_dependency_emits_one_medium_finding(tmp_path):
    (tmp_path / "pom.xml").write_text(_dep_pom("com.acme", "billing", "1.4.0-SNAPSHOT"))

    findings = check_snapshot_prerelease_deps("payments-service", tmp_path)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.repo == "payments-service"
    assert finding.check_id == "snapshot-prerelease-deps"
    assert finding.category == "dependencies"
    assert finding.severity == "Medium"
    assert "com.acme:billing" in finding.evidence
    assert finding.location == "pom.xml"


def _dep_pom(group: str, artifact: str, version: str) -> str:
    return _pom(_dep(group, artifact, version))


def test_release_pins_are_not_flagged(tmp_path):
    (tmp_path / "pom.xml").write_text(
        _pom(
            _dep("com.acme", "billing", "1.4.0"),
            _dep("org.springframework", "spring-core", "6.1.2"),
        )
    )

    assert check_snapshot_prerelease_deps("payments-service", tmp_path) == []


def test_alpha_beta_rc_qualifiers_are_each_flagged(tmp_path):
    (tmp_path / "pom.xml").write_text(
        _pom(
            _dep("g", "a-alpha", "2.0.0-alpha"),
            _dep("g", "b-beta", "3.1.0-beta.2"),
            _dep("g", "c-rc", "1.5.0.RC2"),
        )
    )

    findings = check_snapshot_prerelease_deps("payments-service", tmp_path)

    assert len(findings) == 3
    assert all(f.severity == "Medium" for f in findings)


def test_npm_prerelease_dependency_is_flagged(tmp_path):
    (tmp_path / "package.json").write_text(
        '{\n  "dependencies": {\n    "left-pad": "1.3.0-beta.1",\n'
        '    "react": "18.2.0"\n  }\n}\n'
    )

    findings = check_snapshot_prerelease_deps("web-frontend", tmp_path)

    assert len(findings) == 1
    assert findings[0].location == "package.json"
    assert "left-pad" in findings[0].evidence


def test_ignores_vendored_dirs(tmp_path):
    (tmp_path / "pom.xml").write_text(_dep_pom("com.acme", "billing", "1.0.0-SNAPSHOT"))
    vendored = tmp_path / "node_modules" / "dep"
    vendored.mkdir(parents=True)
    (vendored / "package.json").write_text(
        '{\n  "dependencies": {\n    "x": "0.0.1-alpha"\n  }\n}\n'
    )

    findings = check_snapshot_prerelease_deps("payments-service", tmp_path)

    assert len(findings) == 1
    assert findings[0].location == "pom.xml"


def test_findings_are_identical_across_re_runs(tmp_path):
    (tmp_path / "pom.xml").write_text(
        _pom(
            _dep("g", "z", "1.0.0-SNAPSHOT"),
            _dep("g", "a", "2.0.0-beta"),
        )
    )

    first = check_snapshot_prerelease_deps("payments-service", tmp_path)
    second = check_snapshot_prerelease_deps("payments-service", tmp_path)

    assert first == second
    # Declaration order is preserved deterministically.
    assert "g:z" in first[0].evidence
    assert "g:a" in first[1].evidence
