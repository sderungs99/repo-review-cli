from repo_review.checks import check_unused_dependencies


def _package_json(dependencies: dict, **other_blocks) -> str:
    import json

    return json.dumps({"dependencies": dependencies, **other_blocks})


def test_declared_but_unimported_dependency_is_flagged(tmp_path):
    (tmp_path / "package.json").write_text(_package_json({"left-pad": "^1.3.0"}))
    (tmp_path / "index.js").write_text("const x = 1;\n")

    findings = check_unused_dependencies("web-frontend", tmp_path)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.repo == "web-frontend"
    assert finding.check_id == "unused-dependency"
    assert finding.category == "dependencies"
    assert finding.severity == "Low"
    assert "left-pad" in finding.evidence
    assert finding.location == "package.json"


def test_imported_dependency_is_not_flagged(tmp_path):
    (tmp_path / "package.json").write_text(_package_json({"lodash": "^4.17.21"}))
    (tmp_path / "index.js").write_text("import _ from 'lodash';\n")

    assert check_unused_dependencies("web-frontend", tmp_path) == []


def test_all_import_forms_count_as_usage(tmp_path):
    (tmp_path / "package.json").write_text(
        _package_json(
            {
                "react": "^18.0.0",          # default import: import X from 'react'
                "side-effect": "^1.0.0",      # bare: import 'side-effect'
                "lazy-pkg": "^1.0.0",         # dynamic: import('lazy-pkg')
                "used-cjs": "^1.0.0",         # require('used-cjs')
                "reexported": "^1.0.0",       # export { x } from 'reexported'
            }
        )
    )
    (tmp_path / "index.ts").write_text(
        "import React from 'react';\n"
        "import 'side-effect';\n"
        "const a = import('lazy-pkg');\n"
        "const b = require('used-cjs');\n"
        "export { thing } from 'reexported';\n"
    )

    assert check_unused_dependencies("web-frontend", tmp_path) == []


def test_subpath_and_scoped_imports_resolve_to_the_package(tmp_path):
    (tmp_path / "package.json").write_text(
        _package_json({"lodash": "^4.17.21", "@scope/pkg": "^1.0.0"})
    )
    (tmp_path / "index.ts").write_text(
        "import fp from 'lodash/fp';\n"
        "import sub from '@scope/pkg/sub/deep';\n"
    )

    assert check_unused_dependencies("web-frontend", tmp_path) == []


def test_dev_dependencies_are_not_checked(tmp_path):
    # eslint is build tooling, legitimately never imported in source.
    (tmp_path / "package.json").write_text(
        _package_json({}, devDependencies={"eslint": "^8.0.0"})
    )
    (tmp_path / "index.js").write_text("const x = 1;\n")

    assert check_unused_dependencies("web-frontend", tmp_path) == []


def test_types_packages_are_skipped(tmp_path):
    # @types/* is consumed by the TS compiler, never imported directly.
    (tmp_path / "package.json").write_text(_package_json({"@types/node": "^20.0.0"}))
    (tmp_path / "index.ts").write_text("const x = 1;\n")

    assert check_unused_dependencies("web-frontend", tmp_path) == []


def test_relative_imports_do_not_count_as_a_package(tmp_path):
    (tmp_path / "package.json").write_text(_package_json({"left-pad": "^1.3.0"}))
    # A local import that happens to share a name component must not clear the dep.
    (tmp_path / "index.js").write_text("import x from './left-pad';\n")

    findings = check_unused_dependencies("web-frontend", tmp_path)

    assert len(findings) == 1
    assert "left-pad" in findings[0].evidence


def test_usage_anywhere_in_the_subtree_clears_the_dependency(tmp_path):
    (tmp_path / "package.json").write_text(_package_json({"lodash": "^4.17.21"}))
    nested = tmp_path / "src" / "components"
    nested.mkdir(parents=True)
    (nested / "Widget.tsx").write_text("import _ from 'lodash';\n")

    assert check_unused_dependencies("web-frontend", tmp_path) == []


def test_vendored_node_modules_are_pruned(tmp_path):
    (tmp_path / "package.json").write_text(_package_json({"left-pad": "^1.3.0"}))
    (tmp_path / "index.js").write_text("const x = 1;\n")
    # A vendored package.json and source must not be scanned or reported.
    vendored = tmp_path / "node_modules" / "other"
    vendored.mkdir(parents=True)
    (vendored / "package.json").write_text(_package_json({"unused-inner": "^1.0.0"}))
    (vendored / "index.js").write_text("import 'left-pad';\n")

    findings = check_unused_dependencies("web-frontend", tmp_path)

    # Only the top-level package.json is checked, and the vendored import of
    # left-pad does not count as usage.
    assert len(findings) == 1
    assert findings[0].location == "package.json"
    assert "left-pad" in findings[0].evidence


def test_maven_pom_is_out_of_scope(tmp_path):
    pom = (
        '<project xmlns="http://maven.apache.org/POM/4.0.0">\n'
        "  <dependencies>\n    <dependency>\n"
        "      <groupId>com.google.guava</groupId>\n"
        "      <artifactId>guava</artifactId>\n"
        "      <version>32.0.0</version>\n"
        "    </dependency>\n  </dependencies>\n</project>\n"
    )
    (tmp_path / "pom.xml").write_text(pom)

    assert check_unused_dependencies("payments-service", tmp_path) == []


def test_findings_are_identical_across_re_runs(tmp_path):
    (tmp_path / "package.json").write_text(
        _package_json({"zeta": "^1.0.0", "alpha": "^1.0.0"})
    )
    (tmp_path / "index.js").write_text("const x = 1;\n")

    first = check_unused_dependencies("web-frontend", tmp_path)
    second = check_unused_dependencies("web-frontend", tmp_path)

    assert first == second
    # Declaration order is preserved deterministically.
    assert "zeta" in first[0].evidence
    assert "alpha" in first[1].evidence
