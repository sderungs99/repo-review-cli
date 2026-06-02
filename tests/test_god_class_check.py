from repo_review.checks import check_god_class, GOD_CLASS_DEPENDENCY_THRESHOLD


def _class_with_final_deps(n: int) -> str:
    fields = "\n".join(f"    private final Dep{i} dep{i};" for i in range(n))
    return "public class OrderService {\n" + fields + "\n}\n"


def test_class_over_the_dependency_threshold_emits_one_medium_finding(tmp_path):
    (tmp_path / "OrderService.java").write_text(
        _class_with_final_deps(GOD_CLASS_DEPENDENCY_THRESHOLD)
    )

    findings = check_god_class("payments-service", tmp_path)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.repo == "payments-service"
    assert finding.check_id == "god-class"
    assert finding.category == "architecture"
    assert finding.severity == "Medium"
    assert str(GOD_CLASS_DEPENDENCY_THRESHOLD) in finding.evidence
    assert finding.location == "OrderService.java"


def test_class_just_below_threshold_is_not_flagged(tmp_path):
    (tmp_path / "OrderService.java").write_text(
        _class_with_final_deps(GOD_CLASS_DEPENDENCY_THRESHOLD - 1)
    )

    assert check_god_class("payments-service", tmp_path) == []


def test_field_injection_dependencies_are_counted(tmp_path):
    autowired = "\n".join(
        f"    @Autowired\n    private Dep{i} dep{i};"
        for i in range(GOD_CLASS_DEPENDENCY_THRESHOLD)
    )
    (tmp_path / "OrderController.java").write_text(
        "public class OrderController {\n" + autowired + "\n}\n"
    )

    findings = check_god_class("payments-service", tmp_path)

    assert len(findings) == 1


def test_primitive_final_constants_are_not_counted_as_dependencies(tmp_path):
    # `private final int X` / String constants start lower-case after final or are
    # primitives; they are configuration constants, not injected collaborators.
    constants = "\n".join(
        f"    private final int CONST_{i} = {i};" for i in range(GOD_CLASS_DEPENDENCY_THRESHOLD)
    )
    (tmp_path / "Config.java").write_text(
        "public class Config {\n" + constants + "\n}\n"
    )

    assert check_god_class("payments-service", tmp_path) == []


def test_ignores_vendored_dirs(tmp_path):
    (tmp_path / "OrderService.java").write_text(
        _class_with_final_deps(GOD_CLASS_DEPENDENCY_THRESHOLD)
    )
    vendored = tmp_path / "target" / "generated"
    vendored.mkdir(parents=True)
    (vendored / "Gen.java").write_text(_class_with_final_deps(GOD_CLASS_DEPENDENCY_THRESHOLD))

    findings = check_god_class("payments-service", tmp_path)

    assert len(findings) == 1
    assert findings[0].location == "OrderService.java"


def test_findings_are_identical_across_re_runs(tmp_path):
    for name in ("Zebra.java", "Alpha.java"):
        (tmp_path / name).write_text(_class_with_final_deps(GOD_CLASS_DEPENDENCY_THRESHOLD))

    first = check_god_class("payments-service", tmp_path)
    second = check_god_class("payments-service", tmp_path)

    assert first == second
    assert [f.location for f in first] == ["Alpha.java", "Zebra.java"]
