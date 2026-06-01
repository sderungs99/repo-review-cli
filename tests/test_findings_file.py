import json

from repo_review.finding import Finding
from repo_review.findings_file import to_json, write_findings


def _finding(**overrides):
    base = dict(
        repo="payments-service",
        check_id="readme-presence",
        category="documentation",
        severity="High",
        evidence="No README file found in the repository root.",
        location=".",
    )
    base.update(overrides)
    return Finding(**base)


def test_each_finding_serializes_to_exactly_the_schema_fields():
    payload = json.loads(to_json([_finding()]))

    assert isinstance(payload, list)
    assert len(payload) == 1
    assert set(payload[0].keys()) == {
        "repo",
        "check_id",
        "category",
        "severity",
        "evidence",
        "location",
    }
    assert payload[0]["repo"] == "payments-service"
    assert payload[0]["severity"] == "High"


def test_findings_file_is_canonically_ordered_regardless_of_input_order():
    a = _finding(repo="auth-service")
    b = _finding(repo="payments-service", location="README.md")
    c = _finding(repo="payments-service", location=".")

    one = to_json([a, b, c])
    another = to_json([c, b, a])

    assert one == another


def test_write_findings_round_trips_through_disk(tmp_path):
    path = tmp_path / "findings.json"

    write_findings([_finding()], path)

    assert json.loads(path.read_text())[0]["check_id"] == "readme-presence"
