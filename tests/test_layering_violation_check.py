from repo_review.checks import check_layering_violation


def test_controller_injecting_a_repository_emits_one_medium_finding(tmp_path):
    (tmp_path / "OrderController.java").write_text(
        "@RestController\n"
        "public class OrderController {\n"
        "    private final OrderRepository orders;\n"
        "    public OrderController(OrderRepository orders) { this.orders = orders; }\n"
        "}\n"
    )

    findings = check_layering_violation("payments-service", tmp_path)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.repo == "payments-service"
    assert finding.check_id == "layering-violation"
    assert finding.category == "architecture"
    assert finding.severity == "Medium"
    assert "OrderRepository" in finding.evidence
    assert finding.location == "OrderController.java"


def test_field_injected_repository_is_also_flagged(tmp_path):
    (tmp_path / "OrderController.java").write_text(
        "@Controller\n"
        "public class OrderController {\n"
        "    @Autowired\n"
        "    private OrderRepository orders;\n"
        "}\n"
    )

    findings = check_layering_violation("payments-service", tmp_path)

    assert len(findings) == 1


def test_controller_depending_only_on_a_service_is_not_flagged(tmp_path):
    (tmp_path / "OrderController.java").write_text(
        "@RestController\n"
        "public class OrderController {\n"
        "    private final OrderService service;\n"
        "}\n"
    )

    assert check_layering_violation("payments-service", tmp_path) == []


def test_non_controller_class_using_a_repository_is_not_flagged(tmp_path):
    # A service depending on a repository is the correct layering, not a finding.
    (tmp_path / "OrderService.java").write_text(
        "@Service\n"
        "public class OrderService {\n"
        "    private final OrderRepository orders;\n"
        "}\n"
    )

    assert check_layering_violation("payments-service", tmp_path) == []


def test_multiple_repositories_are_listed_once_per_controller(tmp_path):
    (tmp_path / "OrderController.java").write_text(
        "@RestController\n"
        "public class OrderController {\n"
        "    private final OrderRepository orders;\n"
        "    private final CustomerRepository customers;\n"
        "}\n"
    )

    findings = check_layering_violation("payments-service", tmp_path)

    assert len(findings) == 1
    assert "CustomerRepository" in findings[0].evidence
    assert "OrderRepository" in findings[0].evidence


def test_ignores_vendored_dirs(tmp_path):
    (tmp_path / "OrderController.java").write_text(
        "@RestController\nclass OrderController {\n  private final OrderRepository r;\n}\n"
    )
    vendored = tmp_path / "build" / "generated"
    vendored.mkdir(parents=True)
    (vendored / "Gen.java").write_text(
        "@RestController\nclass Gen {\n  private final FooRepository r;\n}\n"
    )

    findings = check_layering_violation("payments-service", tmp_path)

    assert len(findings) == 1
    assert findings[0].location == "OrderController.java"


def test_findings_are_identical_across_re_runs(tmp_path):
    for name in ("ZebraController.java", "AlphaController.java"):
        (tmp_path / name).write_text(
            "@RestController\nclass C {\n  private final OrderRepository r;\n}\n"
        )

    first = check_layering_violation("payments-service", tmp_path)
    second = check_layering_violation("payments-service", tmp_path)

    assert first == second
    assert [f.location for f in first] == ["AlphaController.java", "ZebraController.java"]
