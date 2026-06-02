from repo_review.checks import check_sql_string_concat


def test_concatenated_query_emits_one_high_security_finding(tmp_path):
    (tmp_path / "UserDao.java").write_text(
        "class UserDao {\n"
        "  String find(String id) {\n"
        '    return "SELECT * FROM users WHERE id = " + id;\n'
        "  }\n"
        "}\n"
    )

    findings = check_sql_string_concat("payments-service", tmp_path)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.repo == "payments-service"
    assert finding.check_id == "sql-string-concat"
    assert finding.category == "security"
    assert finding.severity == "High"
    assert "UserDao.java:3" in finding.evidence


def test_parameterised_query_is_not_flagged(tmp_path):
    # The safe pattern: a placeholder and no concatenation of the query literal.
    (tmp_path / "UserDao.java").write_text(
        '    String sql = "SELECT * FROM users WHERE id = ?";\n'
    )

    assert check_sql_string_concat("payments-service", tmp_path) == []


def test_static_query_literal_without_concat_is_not_flagged(tmp_path):
    (tmp_path / "UserDao.java").write_text(
        '    String sql = "SELECT id, name FROM users";\n'
    )

    assert check_sql_string_concat("payments-service", tmp_path) == []


def test_concatenation_of_non_sql_string_is_not_flagged(tmp_path):
    # A `+` concatenation, but the literal is not a SQL statement.
    (tmp_path / "Greeter.java").write_text(
        '    String msg = "Hello, " + name + "!";\n'
    )

    assert check_sql_string_concat("payments-service", tmp_path) == []


def test_sql_keyword_as_substring_of_a_word_is_not_flagged(tmp_path):
    # "SELECTED" / "UPDATED" must not trip the verb match.
    (tmp_path / "Log.java").write_text(
        '    String m = "User SELECTED option " + choice;\n'
    )

    assert check_sql_string_concat("payments-service", tmp_path) == []


def test_each_concatenated_dml_verb_is_detected(tmp_path):
    (tmp_path / "Dao.java").write_text(
        '    q1 = "INSERT INTO t (a) VALUES (" + a + ")";\n'
        '    q2 = "DELETE FROM t WHERE id = " + id;\n'
        '    q3 = "UPDATE t SET a = " + a;\n'
    )

    findings = check_sql_string_concat("payments-service", tmp_path)

    assert len(findings) == 3
    assert all(f.severity == "High" for f in findings)


def test_ignores_vendored_dirs(tmp_path):
    (tmp_path / "Dao.java").write_text(
        '    String sql = "SELECT * FROM t WHERE id = " + id;\n'
    )
    vendored = tmp_path / "node_modules" / "dep"
    vendored.mkdir(parents=True)
    (vendored / "q.js").write_text(
        'const sql = "SELECT * FROM t WHERE id = " + id;\n'
    )

    findings = check_sql_string_concat("payments-service", tmp_path)

    assert len(findings) == 1
    assert findings[0].location == "Dao.java"


def test_findings_are_identical_across_re_runs(tmp_path):
    for name in ("Zebra.java", "Alpha.java", "Mid.java"):
        (tmp_path / name).write_text(
            '    String sql = "SELECT * FROM t WHERE id = " + id;\n'
        )

    first = check_sql_string_concat("payments-service", tmp_path)
    second = check_sql_string_concat("payments-service", tmp_path)

    assert first == second
    assert [f.location for f in first] == ["Alpha.java", "Mid.java", "Zebra.java"]
