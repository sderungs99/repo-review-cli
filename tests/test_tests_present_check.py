from repo_review.checks import check_tests_present


def test_java_repo_without_test_tree_emits_one_high_testing_finding(tmp_path):
    # A Maven layout with production sources but no src/test tree.
    main = tmp_path / "src" / "main" / "java"
    main.mkdir(parents=True)
    (main / "Service.java").write_text("class Service {}\n")

    findings = check_tests_present("payments-service", tmp_path)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.repo == "payments-service"
    assert finding.check_id == "tests-present"
    assert finding.category == "testing"
    assert finding.severity == "High"


def test_java_repo_with_maven_test_tree_emits_no_finding(tmp_path):
    test_dir = tmp_path / "src" / "test" / "java"
    test_dir.mkdir(parents=True)
    (test_dir / "ServiceTest.java").write_text("class ServiceTest {}\n")

    findings = check_tests_present("payments-service", tmp_path)

    assert findings == []


def test_react_repo_with_test_or_spec_files_emits_no_finding(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "Button.test.tsx").write_text("it('renders', () => {});\n")
    (src / "api.spec.js").write_text("it('calls', () => {});\n")

    findings = check_tests_present("web-frontend", tmp_path)

    assert findings == []


def test_react_native_repo_with_tests_directory_emits_no_finding(tmp_path):
    tests_dir = tmp_path / "app" / "__tests__"
    tests_dir.mkdir(parents=True)
    (tests_dir / "App.js").write_text("it('mounts', () => {});\n")

    findings = check_tests_present("mobile-frontend", tmp_path)

    assert findings == []


def test_tests_only_inside_vendored_dependencies_do_not_count(tmp_path):
    # The repo's own source is untested; the only test files live in a
    # vendored dependency, which is not the vendor's own code.
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "index.js").write_text("export default 1;\n")
    vendored = tmp_path / "node_modules" / "left-pad" / "__tests__"
    vendored.mkdir(parents=True)
    (vendored / "lib.test.js").write_text("it('pads', () => {});\n")

    findings = check_tests_present("web-frontend", tmp_path)

    assert len(findings) == 1
    assert findings[0].severity == "High"


def test_evidence_states_what_was_looked_for_and_what_was_found(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "App.java").write_text("class App {}\n")

    evidence = check_tests_present("payments-service", tmp_path)[0].evidence

    # What was looked for: each ecosystem's test-tree convention.
    assert "src/test" in evidence
    assert ".test." in evidence
    assert ".spec." in evidence
    assert "__tests__" in evidence
    # What was found: nothing.
    assert "none" in evidence.lower()


def test_findings_are_identical_across_re_runs(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "App.java").write_text("class App {}\n")

    first = check_tests_present("payments-service", tmp_path)
    second = check_tests_present("payments-service", tmp_path)

    assert first == second
