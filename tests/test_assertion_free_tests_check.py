from repo_review.checks import check_assertion_free_tests


def test_test_file_with_no_assertion_emits_one_low_testing_finding(tmp_path):
    (tmp_path / "checkout.test.ts").write_text(
        "it('renders the cart', () => {\n"
        "  render(<Cart />);\n"          # exercises code but asserts nothing
        "});\n"
    )

    findings = check_assertion_free_tests("web-frontend", tmp_path)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.repo == "web-frontend"
    assert finding.check_id == "assertion-free-tests"
    assert finding.category == "testing"
    assert finding.severity == "Low"
    assert finding.location == "checkout.test.ts"


def test_jest_expect_assertion_clears_the_file(tmp_path):
    (tmp_path / "checkout.test.ts").write_text(
        "it('adds tax', () => { expect(tax(100)).toBe(20); });\n"
    )

    assert check_assertion_free_tests("web-frontend", tmp_path) == []


def test_junit_assertion_clears_the_file(tmp_path):
    test_dir = tmp_path / "src" / "test" / "java"
    test_dir.mkdir(parents=True)
    (test_dir / "OrderTest.java").write_text(
        "class OrderTest {\n"
        "    @Test\n"
        "    void capturesPayment() { assertEquals(20, tax(100)); }\n"
        "}\n"
    )

    assert check_assertion_free_tests("payments-service", tmp_path) == []


def test_junit_test_without_assertion_is_flagged(tmp_path):
    test_dir = tmp_path / "src" / "test" / "java"
    test_dir.mkdir(parents=True)
    (test_dir / "OrderTest.java").write_text(
        "class OrderTest {\n"
        "    @Test\n"
        "    void capturesPayment() { service.capture(order); }\n"
        "}\n"
    )

    findings = check_assertion_free_tests("payments-service", tmp_path)

    assert len(findings) == 1
    assert findings[0].location == "src/test/java/OrderTest.java"


def test_mockito_verify_counts_as_an_assertion(tmp_path):
    test_dir = tmp_path / "src" / "test" / "java"
    test_dir.mkdir(parents=True)
    (test_dir / "OrderTest.java").write_text(
        "class OrderTest {\n"
        "    @Test\n"
        "    void capturesPayment() { service.capture(order); verify(gateway).charge(); }\n"
        "}\n"
    )

    assert check_assertion_free_tests("payments-service", tmp_path) == []


def test_non_test_files_are_not_considered(tmp_path):
    # Production source with no assertions is not a test file.
    (tmp_path / "Cart.tsx").write_text("export const Cart = () => <div/>;\n")

    assert check_assertion_free_tests("web-frontend", tmp_path) == []


def test_findings_are_identical_across_re_runs(tmp_path):
    (tmp_path / "a.test.js").write_text("it('one', () => { doThing(); });\n")
    (tmp_path / "b.test.js").write_text("it('two', () => { doThing(); });\n")

    first = check_assertion_free_tests("web-frontend", tmp_path)
    second = check_assertion_free_tests("web-frontend", tmp_path)

    assert first == second
    assert [f.location for f in first] == ["a.test.js", "b.test.js"]
