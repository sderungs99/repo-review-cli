from repo_review.checks import check_react_dangerous_html


def test_single_usage_emits_one_medium_security_finding(tmp_path):
    (tmp_path / "Article.jsx").write_text(
        "export function Article({ html }) {\n"
        "  return <div dangerouslySetInnerHTML={{ __html: html }} />;\n"
        "}\n"
    )

    findings = check_react_dangerous_html("web-frontend", tmp_path)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.repo == "web-frontend"
    assert finding.check_id == "react-dangerous-html"
    assert finding.category == "security"
    assert finding.severity == "Medium"
    assert "Article.jsx:2" in finding.evidence


def test_clean_source_tree_emits_no_finding(tmp_path):
    (tmp_path / "Article.tsx").write_text(
        "export const Article = ({ text }: Props) => <div>{text}</div>;\n"
    )

    assert check_react_dangerous_html("web-frontend", tmp_path) == []


def test_every_occurrence_is_surfaced_with_its_own_location(tmp_path):
    (tmp_path / "A.tsx").write_text(
        "const a = <div dangerouslySetInnerHTML={{ __html: x }} />;\n"
        "const b = <span dangerouslySetInnerHTML={{ __html: y }} />;\n"
    )

    findings = check_react_dangerous_html("web-frontend", tmp_path)

    assert len(findings) == 2
    assert [f.location for f in findings] == ["A.tsx", "A.tsx"]
    assert "A.tsx:1" in findings[0].evidence
    assert "A.tsx:2" in findings[1].evidence


def test_ignores_non_source_files_and_vendor_dirs(tmp_path):
    # A usage in the vendor's own source counts.
    (tmp_path / "App.jsx").write_text(
        "const x = <div dangerouslySetInnerHTML={{ __html: h }} />;\n"
    )
    # A mention in docs is not source.
    (tmp_path / "README.md").write_text("We avoid dangerouslySetInnerHTML here.\n")
    # The same token inside a vendored dependency is not the vendor's code.
    vendored = tmp_path / "node_modules" / "dep"
    vendored.mkdir(parents=True)
    (vendored / "index.js").write_text(
        "el.dangerouslySetInnerHTML = { __html: a };\n"
    )

    findings = check_react_dangerous_html("web-frontend", tmp_path)

    assert len(findings) == 1
    assert findings[0].location == "App.jsx"


def test_findings_are_identical_across_re_runs(tmp_path):
    for name in ("Zebra.jsx", "Alpha.jsx", "Mid.tsx"):
        (tmp_path / name).write_text(
            "const x = <div dangerouslySetInnerHTML={{ __html: h }} />;\n"
        )

    first = check_react_dangerous_html("web-frontend", tmp_path)
    second = check_react_dangerous_html("web-frontend", tmp_path)

    assert first == second
    # Findings are emitted in stable, path-sorted order.
    assert [f.location for f in first] == ["Alpha.jsx", "Mid.tsx", "Zebra.jsx"]
