from repo_review.finding import Finding
from repo_review.reports import render_stakeholder, render_technical


def _finding(repo, category, severity, location="."):
    return Finding(
        repo=repo,
        check_id="readme-presence",
        category=category,
        severity=severity,
        evidence="evidence text",
        location=location,
    )


def _sample():
    return [
        _finding("auth-service", "documentation", "High"),
        _finding("payments-service", "documentation", "Medium", "README.md"),
        _finding("payments-service", "security", "High"),
    ]


def test_stakeholder_report_rolls_up_counts_by_category():
    report = render_stakeholder(_sample())

    assert "documentation: 2" in report
    assert "security: 1" in report


def test_stakeholder_report_rolls_up_counts_by_severity():
    report = render_stakeholder(_sample())

    assert "High: 2" in report
    assert "Medium: 1" in report


def test_technical_report_groups_findings_by_repo_and_category():
    report = render_technical(_sample())

    # Every Subject Repo is a section, with its categories beneath it.
    assert "auth-service" in report
    assert "payments-service" in report
    assert "documentation" in report
    assert "security" in report
    # Evidence and location are present so engineers can act on each finding.
    assert "evidence text" in report
    assert "README.md" in report


def test_technical_report_attributes_findings_to_the_right_repo():
    report = render_technical(
        [_finding("auth-service", "security", "Critical", "pom.xml")]
    )

    auth_section = report.split("auth-service", 1)[1]
    assert "security" in auth_section
    assert "Critical" in auth_section
    assert "pom.xml" in auth_section
