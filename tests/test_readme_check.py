import pytest

from repo_review.checks import check_readme_presence

SUBSTANTIAL = (
    "This service handles card and SEPA payment capture for the checkout "
    "flow, with retry and idempotency guarantees documented below in detail.\n"
)


def test_missing_readme_emits_one_documentation_finding(tmp_path):
    findings = check_readme_presence("payments-service", tmp_path)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.repo == "payments-service"
    assert finding.check_id == "readme-presence"
    assert finding.category == "documentation"
    assert finding.severity == "High"


def test_substantial_readme_emits_no_finding(tmp_path):
    (tmp_path / "README.md").write_text(
        "# Payments Service\n\n"
        "Handles card and SEPA payment capture for the checkout flow. "
        "See docs/ for the integration guide and local setup instructions.\n"
    )

    findings = check_readme_presence("payments-service", tmp_path)

    assert findings == []


def test_stub_readme_emits_medium_finding(tmp_path):
    (tmp_path / "README.md").write_text("# Payments Service\n\nTODO\n")

    findings = check_readme_presence("payments-service", tmp_path)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.check_id == "readme-presence"
    assert finding.category == "documentation"
    assert finding.severity == "Medium"
    assert finding.location == "README.md"


def test_empty_readme_emits_medium_finding(tmp_path):
    (tmp_path / "README.md").write_text("   \n\n")

    findings = check_readme_presence("payments-service", tmp_path)

    assert len(findings) == 1
    assert findings[0].severity == "Medium"


@pytest.mark.parametrize(
    "filename", ["README", "README.md", "readme.md", "README.rst", "Readme.txt"]
)
def test_readme_recognized_regardless_of_case_or_extension(tmp_path, filename):
    (tmp_path / filename).write_text(SUBSTANTIAL)

    findings = check_readme_presence("payments-service", tmp_path)

    assert findings == []
