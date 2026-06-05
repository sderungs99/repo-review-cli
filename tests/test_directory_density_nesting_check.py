"""Tests for directory file density and excessive package nesting checks."""

from repo_review.checks import (
    is_project,
    check_directory_file_density,
    check_excessive_package_nesting,
    DIRECTORY_FILE_DENSITY_CHECK_ID,
    EXCESSIVE_PACKAGE_NESTING_CHECK_ID,
    DIRECTORY_FILE_DENSITY_THRESHOLD,
    EXCESSIVE_PACKAGE_NESTING_THRESHOLD,
)


# ── is_project ──────────────────────────────────────────────────────────────


def test_is_project_detects_java_project_with_pom_xml(tmp_path):
    (tmp_path / "pom.xml").write_text("<project/>")

    assert is_project(tmp_path) is True


def test_is_project_detects_java_project_with_gradle(tmp_path):
    (tmp_path / "build.gradle").write_text("")

    assert is_project(tmp_path) is True


def test_is_project_detects_js_ts_project(tmp_path):
    (tmp_path / "package.json").write_text("{}")

    assert is_project(tmp_path) is True


def test_is_project_returns_false_for_unknown_project(tmp_path):
    (tmp_path / "Cargo.toml").write_text("[package]\nname = \"foo\"")

    assert is_project(tmp_path) is False


def test_is_project_returns_false_for_empty_directory(tmp_path):
    assert is_project(tmp_path) is False


# ── Thresholds are module-level constants ───────────────────────────────────


def test_density_threshold_is_ten():
    assert DIRECTORY_FILE_DENSITY_THRESHOLD == 10


def test_nesting_threshold_is_four():
    assert EXCESSIVE_PACKAGE_NESTING_THRESHOLD == 4


# ── check_directory_file_density ────────────────────────────────────────────


def test_density_check_skips_non_java_non_js_ts_projects(tmp_path):
    (tmp_path / "Cargo.toml").write_text("")

    findings = check_directory_file_density("rust-app", tmp_path)

    assert findings == []


def test_density_check_flags_directory_with_too_many_source_files(tmp_path):
    # Create a Java project with a crowded directory.
    (tmp_path / "pom.xml").write_text("<project/>")
    src_root = tmp_path / "src" / "main" / "java"
    controller = src_root / "com" / "acme" / "order" / "controller"
    controller.mkdir(parents=True)

    # 11 files: one over the threshold.
    for i in range(11):
        (controller / f"OrderController{i}.java").write_text(f"class OrderController{i} {{}}")

    findings = check_directory_file_density("orders-service", tmp_path)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.repo == "orders-service"
    assert finding.check_id == DIRECTORY_FILE_DENSITY_CHECK_ID
    assert finding.category == "code-hygiene"
    assert finding.severity == "Medium"
    assert "controller" in finding.evidence
    assert "11" in finding.evidence
    assert "10" in finding.evidence


def test_density_check_passes_for_directory_at_threshold(tmp_path):
    (tmp_path / "pom.xml").write_text("<project/>")
    src_root = tmp_path / "src" / "main" / "java"
    d = src_root / "com" / "acme" / "order"
    d.mkdir(parents=True)

    # Exactly 10: at threshold, not flagged.
    for i in range(10):
        (d / f"Order{i}.java").write_text(f"class Order{i} {{}}")

    findings = check_directory_file_density("orders-service", tmp_path)

    assert findings == []


def test_density_check_uses_source_root_for_java(tmp_path):
    (tmp_path / "pom.xml").write_text("<project/>")

    # Put files in the *wrong* directory — should not count.
    wrong = tmp_path / "wrong" / "controller"
    wrong.mkdir(parents=True)
    for i in range(11):
        (wrong / f"X{i}.java").write_text(f"class X{i} {{}}")

    # Correct source root with only 2 files.
    src_root = tmp_path / "src" / "main" / "java"
    right = src_root / "com" / "acme"
    right.mkdir(parents=True)
    for i in range(2):
        (right / f"Y{i}.java").write_text(f"class Y{i} {{}}")

    findings = check_directory_file_density("orders-service", tmp_path)

    assert findings == []


def test_density_check_uses_src_for_js_ts_projects(tmp_path):
    (tmp_path / "package.json").write_text("{}")
    src = tmp_path / "src"
    crowded = src / "components"
    crowded.mkdir(parents=True)

    for i in range(11):
        (crowded / f"Comp{i}.tsx").write_text(f"export function Comp{i} {{}}")

    findings = check_directory_file_density("frontend-app", tmp_path)

    assert len(findings) == 1
    assert "components" in findings[0].evidence


def test_density_check_ignores_vendor_dirs(tmp_path):
    (tmp_path / "pom.xml").write_text("<project/>")
    src_root = tmp_path / "src" / "main" / "java"

    # Crowded real directory.
    real = src_root / "com" / "acme"
    real.mkdir(parents=True)
    for i in range(11):
        (real / f"Real{i}.java").write_text(f"class Real{i} {{}}")

    # Crowded vendor dir — must not count.
    node_modules = tmp_path / "node_modules" / "ui"
    node_modules.mkdir(parents=True)
    for i in range(20):
        (node_modules / f"dep{i}.js").write_text(f"module.exports = {{}}")

    target = tmp_path / "target" / "generated"
    target.mkdir(parents=True)
    for i in range(20):
        (target / f"Gen{i}.java").write_text(f"// generated {i}")

    findings = check_directory_file_density("orders-service", tmp_path)

    assert len(findings) == 1
    assert "src/main/java/com/acme" in findings[0].evidence


# ── check_excessive_package_nesting ─────────────────────────────────────────


def test_nesting_check_skips_unknown_projects(tmp_path):
    (tmp_path / "Gemfile.lock").write_text("")

    findings = check_excessive_package_nesting("ruby-app", tmp_path)

    assert findings == []


def test_nesting_check_flags_depth_exceeding_threshold(tmp_path):
    (tmp_path / "pom.xml").write_text("<project/>")
    src_root = tmp_path / "src" / "main" / "java"

    # Path: com/acme/order/controller/v2/service/impl/UserService.java
    # Actual root is ``com`` (first child of src/main/java with files).
    # Depth from actual root: 7 (acme/order/controller/v2/service/impl/UserService.java).
    deep = src_root / "com" / "acme" / "order" / "controller" / "v2" / "service" / "impl"
    deep.mkdir(parents=True)
    (deep / "UserService.java").write_text("class UserService {}")

    findings = check_excessive_package_nesting("users-service", tmp_path)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.repo == "users-service"
    assert finding.check_id == EXCESSIVE_PACKAGE_NESTING_CHECK_ID
    assert finding.category == "code-hygiene"
    assert finding.severity == "Medium"
    assert "UserService.java" in finding.evidence
    assert "7" in finding.evidence
    assert "4" in finding.evidence


def test_nesting_check_passes_at_threshold(tmp_path):
    (tmp_path / "pom.xml").write_text("<project/>")
    src_root = tmp_path / "src" / "main" / "java"

    # Depth from actual root ``a``: 4 parts (b/c/d/Service.java).
    # At threshold, not flagged (must exceed).
    d = src_root / "a" / "b" / "c" / "d"
    d.mkdir(parents=True)
    (d / "Service.java").write_text("class Service {}")

    findings = check_excessive_package_nesting("svc", tmp_path)

    assert findings == []


def test_nesting_check_passes_just_below_threshold(tmp_path):
    (tmp_path / "pom.xml").write_text("<project/>")
    src_root = tmp_path / "src" / "main" / "java"

    # Depth from actual root ``a``: 3 parts (b/c/Service.java).
    d = src_root / "a" / "b" / "c"
    d.mkdir(parents=True)
    (d / "Service.java").write_text("class Service {}")

    findings = check_excessive_package_nesting("svc", tmp_path)

    assert findings == []


def test_nesting_check_only_reports_deepest_path(tmp_path):
    (tmp_path / "pom.xml").write_text("<project/>")
    src_root = tmp_path / "src" / "main" / "java"

    # Actual root is ``a`` (first child with files).
    # Shallow file depth from ``a``: 3 (below threshold).
    # Deep file depth from ``a``: 6 (above threshold).
    shallow = src_root / "a" / "b" / "c"
    shallow.mkdir(parents=True)
    (shallow / "Shallow.java").write_text("class Shallow {}")

    deep = src_root / "a" / "b" / "c" / "d" / "e" / "deep"
    deep.mkdir(parents=True)
    (deep / "Deep.java").write_text("class Deep {}")

    findings = check_excessive_package_nesting("svc", tmp_path)

    assert len(findings) == 1
    assert "Deep.java" in findings[0].evidence
    assert "Shallow.java" not in findings[0].evidence


def test_nesting_check_handles_multiple_src_dirs_monorepo(tmp_path):
    (tmp_path / "package.json").write_text("{}")

    # First src: shallow. Actual root ``a``, depth 1.
    src1 = tmp_path / "frontend" / "src"
    (src1 / "a").mkdir(parents=True)
    (src1 / "a" / "b.tsx").write_text("export const A = 1")

    # Second src: deep. Actual root ``main``, depth from main:
    # java/com/acme/order/svc/OrderService.java = 6.
    src2 = tmp_path / "backend" / "src"
    deep = src2 / "main" / "java" / "com" / "acme" / "order" / "svc"
    deep.mkdir(parents=True)
    (deep / "OrderService.java").write_text("class OrderService {}")

    findings = check_excessive_package_nesting("monorepo", tmp_path)

    assert len(findings) == 1
    assert "OrderService.java" in findings[0].evidence


def test_nesting_check_ignores_vendor_dirs(tmp_path):
    (tmp_path / "pom.xml").write_text("<project/>")
    src_root = tmp_path / "src" / "main" / "java"

    # Shallow real code.
    (src_root / "com").mkdir(parents=True)
    (src_root / "com" / "Acme.java").write_text("class Acme {}")

    # Deep vendor dir — must not count.
    node_modules = tmp_path / "node_modules" / "a" / "b" / "c" / "d" / "e" / "f"
    node_modules.mkdir(parents=True)
    (node_modules / "deep.js").write_text("const x = 1")

    target = tmp_path / "target" / "a" / "b" / "c" / "d" / "e" / "f"
    target.mkdir(parents=True)
    (target / "Deep.java").write_text("// generated")

    findings = check_excessive_package_nesting("svc", tmp_path)

    assert findings == []


# ── Multi-module Java support ───────────────────────────────────────────────


def test_density_check_finds_all_src_main_java_in_multi_module(tmp_path):
    """Density checks across multiple src/main/java in a multi-module Maven project."""
    (tmp_path / "pom.xml").write_text("<project/>")

    # module-a: 11 files in one directory.
    mod_a = tmp_path / "module-a" / "src" / "main" / "java"
    crowded_a = mod_a / "com" / "acme" / "service"
    crowded_a.mkdir(parents=True)
    for i in range(11):
        (crowded_a / f"Service{i}.java").write_text(f"class Service{i} {{}}")

    # module-b: only 3 files everywhere.
    mod_b = tmp_path / "module-b" / "src" / "main" / "java"
    mod_b.mkdir(parents=True)
    for i in range(3):
        (mod_b / f"Thing{i}.java").write_text(f"class Thing{i} {{}}")

    findings = check_directory_file_density("multi-project", tmp_path)

    assert len(findings) == 1
    assert "service" in findings[0].evidence


def test_nesting_check_measures_across_multiple_module_roots(tmp_path):
    """Nesting depth is measured independently from each module's src/main/java."""
    (tmp_path / "pom.xml").write_text("<project/>")

    # module-a: shallow (flat).
    mod_a = tmp_path / "module-a" / "src" / "main" / "java"
    mod_a.mkdir(parents=True)
    (mod_a / "Flat.java").write_text("class Flat {}")

    # module-b: deep (5 levels from actual root ``com``).
    mod_b = tmp_path / "module-b" / "src" / "main" / "java"
    deep = mod_b / "com" / "acme" / "order" / "svc" / "impl"
    deep.mkdir(parents=True)
    (deep / "DeepService.java").write_text("class DeepService {}")

    findings = check_excessive_package_nesting("multi-project", tmp_path)

    assert len(findings) == 1
    assert "DeepService.java" in findings[0].evidence


def test_density_and_nesting_scan_src_test_java_too(tmp_path):
    """src/test/java is also scanned as a source root."""
    (tmp_path / "pom.xml").write_text("<project/>")
    test_root = tmp_path / "src" / "test" / "java"

    crowded = test_root / "com" / "acme"
    crowded.mkdir(parents=True)
    for i in range(11):
        (crowded / f"Test{i}.java").write_text(f"class Test{i} {{}}")

    findings = check_directory_file_density("app", tmp_path)

    assert len(findings) == 1

    findings2 = check_excessive_package_nesting("app", tmp_path)
    # depth from src/test/java/com/Test.java = 1 (below threshold)
    assert findings2 == []


def test_nesting_check_skips_single_child_organizational_tree(tmp_path):
    """Organisational prefix trees are skipped; branching point is the actual root.

    Real-world pattern: jp/co/smbc/gcms/channel/entitlement/...
    where entitlement has multiple subdirectories (model + entity).
    """
    (tmp_path / "pom.xml").write_text("<project/>")
    src_root = tmp_path / "src" / "main" / "java"

    deep = src_root / "jp" / "co" / "smbc" / "gcms" / "channel" / "entitlement"
    (deep / "model" / "inner").mkdir(parents=True)
    (deep / "entity" / "composite" / "nested" / "deeper").mkdir(parents=True)
    (deep / "entity" / "composite" / "nested" / "deeper" / "AccountUserEntitlementKey.java").write_text(
        "class AccountUserEntitlementKey {}"
    )

    findings = check_excessive_package_nesting("gcms", tmp_path)

    assert len(findings) == 1
    # Actual root is ``entitlement`` (first directory with 2+ subdirs).
    # Depth from ``entitlement``: entity/composite/nested/deeper/AccountUserEntitlementKey.java = 5
    assert "5" in findings[0].evidence
    assert "AccountUserEntitlementKey.java" in findings[0].evidence
