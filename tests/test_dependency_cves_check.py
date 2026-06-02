import json

from repo_review.advisories import Advisory, AdvisoryDataset
from repo_review.checks import check_dependency_cves


def _dataset(*advisories, version="2026-05-01"):
    return AdvisoryDataset(version=version, advisories=tuple(advisories))


LODASH_CVE = Advisory(
    ecosystem="npm",
    package="lodash",
    affected=("4.17.20",),
    cve="CVE-2021-23337",
    cvss=7.2,
)

JACKSON_CVE = Advisory(
    ecosystem="maven",
    package="com.fasterxml.jackson.core:jackson-databind",
    affected=("2.9.10.1",),
    cve="CVE-2020-9546",
    cvss=9.8,
)


def _pom(dependencies):
    """A pom.xml declaring the given (groupId, artifactId, version) deps."""
    deps = "".join(
        f"    <dependency><groupId>{g}</groupId>"
        f"<artifactId>{a}</artifactId><version>{v}</version></dependency>\n"
        for g, a, v in dependencies
    )
    return (
        '<project xmlns="http://maven.apache.org/POM/4.0.0">\n'
        "  <dependencies>\n"
        f"{deps}"
        "  </dependencies>\n"
        "</project>\n"
    )


def _package_lock(packages):
    """An npm 7+ package-lock.json with the given {name: version} resolved deps."""
    return json.dumps({
        "lockfileVersion": 3,
        "packages": {
            f"node_modules/{name}": {"version": version}
            for name, version in packages.items()
        },
    })


def test_vulnerable_npm_dependency_in_lockfile_emits_one_dependencies_finding(tmp_path):
    (tmp_path / "package-lock.json").write_text(_package_lock({"lodash": "4.17.20"}))

    findings = check_dependency_cves("payments-service", tmp_path, _dataset(LODASH_CVE))

    assert len(findings) == 1
    finding = findings[0]
    assert finding.repo == "payments-service"
    assert finding.check_id == "dependency-cves"
    assert finding.category == "dependencies"
    # CVSS 7.2 maps to High on the 5-level scale.
    assert finding.severity == "High"
    # Evidence locates the package, its version, the CVE, and the dataset snapshot.
    assert "lodash" in finding.evidence
    assert "4.17.20" in finding.evidence
    assert "CVE-2021-23337" in finding.evidence
    assert "2026-05-01" in finding.evidence


def test_patched_version_not_in_affected_set_emits_no_finding(tmp_path):
    # lodash 4.17.21 is the fix; only 4.17.20 is affected.
    (tmp_path / "package-lock.json").write_text(_package_lock({"lodash": "4.17.21"}))

    assert check_dependency_cves("payments-service", tmp_path, _dataset(LODASH_CVE)) == []


def test_severity_is_mapped_from_the_cvss_score(tmp_path):
    (tmp_path / "package-lock.json").write_text(_package_lock({
        "crit": "1.0.0",
        "high": "1.0.0",
        "med": "1.0.0",
        "low": "1.0.0",
    }))
    dataset = _dataset(
        Advisory("npm", "crit", ("1.0.0",), "CVE-CRIT", 9.8),
        Advisory("npm", "high", ("1.0.0",), "CVE-HIGH", 7.0),
        Advisory("npm", "med", ("1.0.0",), "CVE-MED", 5.5),
        Advisory("npm", "low", ("1.0.0",), "CVE-LOW", 2.1),
    )

    findings = check_dependency_cves("payments-service", tmp_path, dataset)

    by_package = {f.evidence.split()[0]: f.severity for f in findings}
    assert by_package == {
        "crit": "Critical",
        "high": "High",
        "med": "Medium",
        "low": "Low",
    }


def test_vulnerable_maven_dependency_in_pom_is_matched_on_group_and_artifact(tmp_path):
    (tmp_path / "pom.xml").write_text(_pom([
        ("com.fasterxml.jackson.core", "jackson-databind", "2.9.10.1"),
    ]))

    findings = check_dependency_cves("payments-service", tmp_path, _dataset(JACKSON_CVE))

    assert len(findings) == 1
    finding = findings[0]
    assert finding.category == "dependencies"
    assert finding.severity == "Critical"
    assert "com.fasterxml.jackson.core:jackson-databind" in finding.evidence
    assert "2.9.10.1" in finding.evidence
    assert "CVE-2020-9546" in finding.evidence


def test_vulnerable_dependency_declared_in_package_json_without_lockfile(tmp_path):
    # No lockfile present; the declared exact pin is the only version signal.
    (tmp_path / "package.json").write_text(json.dumps({
        "dependencies": {"lodash": "4.17.20"},
    }))

    findings = check_dependency_cves("payments-service", tmp_path, _dataset(LODASH_CVE))

    assert len(findings) == 1
    assert "lodash" in findings[0].evidence
    assert "CVE-2021-23337" in findings[0].evidence


def test_package_json_range_specifier_is_not_treated_as_an_exact_version(tmp_path):
    # "^4.17.20" is a range, not a pin; without a lockfile we can't resolve it,
    # so it must not exact-match (ADR-0002: no build/resolution).
    (tmp_path / "package.json").write_text(json.dumps({
        "dependencies": {"lodash": "^4.17.20"},
    }))

    assert check_dependency_cves("payments-service", tmp_path, _dataset(LODASH_CVE)) == []


def test_lockfile_is_preferred_and_catches_a_transitive_dependency(tmp_path):
    # package.json declares only a safe direct dep; the lockfile reveals the
    # vulnerable lodash pulled in transitively at a resolved version.
    (tmp_path / "package.json").write_text(json.dumps({
        "dependencies": {"express": "4.18.2"},
    }))
    (tmp_path / "package-lock.json").write_text(_package_lock({
        "express": "4.18.2",
        "lodash": "4.17.20",
    }))

    findings = check_dependency_cves("payments-service", tmp_path, _dataset(LODASH_CVE))

    assert len(findings) == 1
    assert "lodash" in findings[0].evidence
    assert "4.17.20" in findings[0].evidence


def test_multiple_cves_and_packages_each_produce_a_finding(tmp_path):
    (tmp_path / "package-lock.json").write_text(_package_lock({
        "lodash": "4.17.20",
        "minimist": "1.2.5",
    }))
    dataset = _dataset(
        LODASH_CVE,
        # A second, distinct CVE affecting the same lodash version.
        Advisory("npm", "lodash", ("4.17.20",), "CVE-2020-8203", 7.4),
        Advisory("npm", "minimist", ("1.2.5",), "CVE-2021-44906", 9.8),
    )

    findings = check_dependency_cves("payments-service", tmp_path, dataset)

    cves = {c for f in findings for c in ("CVE-2021-23337", "CVE-2020-8203", "CVE-2021-44906") if c in f.evidence}
    assert len(findings) == 3
    assert cves == {"CVE-2021-23337", "CVE-2020-8203", "CVE-2021-44906"}


def test_dependency_files_inside_node_modules_are_ignored(tmp_path):
    # A vendored package ships its own pom.xml / package-lock.json; those are
    # the dependency's manifests, not the Subject Repo's own (see _SKIP_DIRS).
    vendored = tmp_path / "node_modules" / "some-dep"
    vendored.mkdir(parents=True)
    (vendored / "package-lock.json").write_text(_package_lock({"lodash": "4.17.20"}))
    (vendored / "pom.xml").write_text(_pom([
        ("com.fasterxml.jackson.core", "jackson-databind", "2.9.10.1"),
    ]))

    findings = check_dependency_cves(
        "payments-service", tmp_path, _dataset(LODASH_CVE, JACKSON_CVE)
    )

    assert findings == []


def test_repo_with_no_dependency_manifests_emits_no_finding(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "App.java").write_text("class App {}\n")

    assert check_dependency_cves("payments-service", tmp_path, _dataset(LODASH_CVE)) == []


def test_findings_are_identical_across_re_runs(tmp_path):
    (tmp_path / "package-lock.json").write_text(_package_lock({
        "lodash": "4.17.20", "minimist": "1.2.5",
    }))
    (tmp_path / "pom.xml").write_text(_pom([
        ("com.fasterxml.jackson.core", "jackson-databind", "2.9.10.1"),
    ]))
    dataset = _dataset(
        LODASH_CVE,
        JACKSON_CVE,
        Advisory("npm", "minimist", ("1.2.5",), "CVE-2021-44906", 9.8),
    )

    first = check_dependency_cves("payments-service", tmp_path, dataset)
    second = check_dependency_cves("payments-service", tmp_path, dataset)

    assert first == second
    assert len(first) == 3


def test_malformed_dependency_file_is_skipped_not_fatal(tmp_path):
    # A corrupt/partial manifest in one repo must not crash the whole review;
    # it is treated as yielding no dependencies (cf. the pom ParseError guard).
    (tmp_path / "package-lock.json").write_text("{ this is not valid json")

    assert check_dependency_cves("payments-service", tmp_path, _dataset(LODASH_CVE)) == []
