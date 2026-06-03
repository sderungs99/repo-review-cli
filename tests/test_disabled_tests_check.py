from repo_review.checks import check_disabled_tests


def test_junit_disabled_annotation_emits_one_medium_testing_finding(tmp_path):
    test_dir = tmp_path / "src" / "test" / "java"
    test_dir.mkdir(parents=True)
    (test_dir / "OrderTest.java").write_text(
        "class OrderTest {\n"
        "    @Disabled(\"flaky\")\n"
        "    @Test\n"
        "    void capturesPayment() {}\n"
        "}\n"
    )

    findings = check_disabled_tests("payments-service", tmp_path)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.repo == "payments-service"
    assert finding.check_id == "disabled-tests"
    assert finding.category == "testing"
    assert finding.severity == "Medium"
    assert "@Disabled" in finding.evidence
    assert "src/test/java/OrderTest.java:2" in finding.evidence


def test_jest_skip_and_x_prefixed_and_only_are_flagged(tmp_path):
    (tmp_path / "checkout.test.ts").write_text(
        "describe('checkout', () => {\n"
        "  xit('adds tax', () => {});\n"
        "  it.skip('applies discount', () => {});\n"
        "  it.only('captures', () => {});\n"
        "});\n"
    )

    findings = check_disabled_tests("web-frontend", tmp_path)

    assert len(findings) == 3
    assert all(f.severity == "Medium" for f in findings)


def test_active_tests_are_not_flagged(tmp_path):
    (tmp_path / "checkout.test.ts").write_text(
        "it('adds tax', () => { expect(tax(100)).toBe(20); });\n"
    )

    assert check_disabled_tests("web-frontend", tmp_path) == []


def test_directives_outside_test_files_are_ignored(tmp_path):
    # The same tokens in non-test source are not the test suite's concern.
    (tmp_path / "App.tsx").write_text("const xit = 1;\n// @Disabled note\n")

    assert check_disabled_tests("web-frontend", tmp_path) == []


def test_xit_substring_of_a_word_is_not_matched(tmp_path):
    (tmp_path / "thing.spec.js").write_text(
        "it('exits cleanly', () => { expect(exit()).toBe(0); });\n"
    )

    assert check_disabled_tests("web-frontend", tmp_path) == []


def test_findings_are_identical_across_re_runs(tmp_path):
    (tmp_path / "a.test.js").write_text("xit('one', () => {});\n")
    (tmp_path / "b.test.js").write_text("xit('two', () => {});\n")

    first = check_disabled_tests("web-frontend", tmp_path)
    second = check_disabled_tests("web-frontend", tmp_path)

    assert first == second
    assert [f.location for f in first] == ["a.test.js", "b.test.js"]
