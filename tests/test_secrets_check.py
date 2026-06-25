from repo_review.checks import check_secrets


def test_private_key_block_emits_one_critical_security_finding(tmp_path):
    (tmp_path / "deploy_key").write_text(
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEowIBAAKCAQEA1c3...redactedbodydoesnotmatter...\n"
        "-----END RSA PRIVATE KEY-----\n"
    )

    findings = check_secrets("payments-service", tmp_path)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.repo == "payments-service"
    assert finding.check_id == "secret-scanning"
    assert finding.category == "security"
    assert finding.severity == "Critical"
    # Evidence names the kind of secret and the file:line, not the key material.
    assert "private key" in finding.evidence.lower()
    assert "deploy_key:1" in finding.evidence


def test_clean_repo_emits_no_finding(tmp_path):
    (tmp_path / "App.java").write_text(
        "class App {\n"
        '    String region = "us-east-1";\n'
        "    int retries = 3;\n"
        "}\n"
    )
    (tmp_path / "config.properties").write_text("db.host=localhost\ndb.port=5432\n")

    assert check_secrets("payments-service", tmp_path) == []


def test_findings_are_identical_across_re_runs(tmp_path):
    (tmp_path / "zeta.properties").write_text("db.password=s3cr3t-Pa55word-Value\n")
    (tmp_path / "alpha.env").write_text("aws.key=AKIAIOSFODNN7EXAMPLE\n")
    (tmp_path / "mid.yml").write_text("token: ghp_0123456789abcdefABCDEF0123456789abcd\n")

    first = check_secrets("payments-service", tmp_path)
    second = check_secrets("payments-service", tmp_path)

    assert first == second
    assert len(first) == 3
    # Findings are emitted in stable, path-sorted order.
    assert [f.location for f in first] == ["alpha.env", "mid.yml", "zeta.properties"]


def test_secrets_in_vendored_dirs_and_binary_files_are_ignored(tmp_path):
    # A real committed secret in the vendor's own source is found.
    (tmp_path / ".env").write_text("aws.key=AKIAIOSFODNN7EXAMPLE\n")
    # The same shape inside a vendored dependency is not the vendor's secret.
    vendored = tmp_path / "node_modules" / "dep"
    vendored.mkdir(parents=True)
    (vendored / "config.js").write_text("const k = 'AKIAIOSFODNN7EXAMPLE';\n")
    # A binary blob that happens to contain matching bytes is noise, not a leak.
    (tmp_path / "logo.png").write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00AKIAIOSFODNN7EXAMPLE\x00\xff\xfe")

    findings = check_secrets("payments-service", tmp_path)

    assert len(findings) == 1
    assert findings[0].location == ".env"


def test_evidence_never_quotes_the_secret_value(tmp_path):
    aws_key = "AKIAIOSFODNN7EXAMPLE"
    gh_token = "ghp_0123456789abcdefABCDEF0123456789abcd"
    password = "s3cr3t-Pa55word-Value"
    (tmp_path / "leak.properties").write_text(
        f"aws.key={aws_key}\n"
        f"GITHUB_TOKEN={gh_token}\n"
        f"db.password={password}\n"
    )

    findings = check_secrets("payments-service", tmp_path)

    assert len(findings) == 3
    for finding in findings:
        assert aws_key not in finding.evidence
        assert gh_token not in finding.evidence
        assert password not in finding.evidence
        assert "redacted" in finding.evidence.lower()


def test_aws_access_key_id_emits_one_high_finding(tmp_path):
    (tmp_path / "config.properties").write_text(
        "db.host=localhost\n"
        "aws.accessKeyId=AKIAIOSFODNN7EXAMPLE\n"
    )

    findings = check_secrets("payments-service", tmp_path)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.severity == "High"
    assert finding.category == "security"
    assert "aws" in finding.evidence.lower()
    assert "config.properties:2" in finding.evidence


def test_github_token_emits_one_high_finding(tmp_path):
    (tmp_path / ".env").write_text(
        "GITHUB_TOKEN=ghp_0123456789abcdefABCDEF0123456789abcd\n"
    )

    findings = check_secrets("payments-service", tmp_path)

    assert len(findings) == 1
    assert findings[0].severity == "High"
    assert "github" in findings[0].evidence.lower()
    assert ".env:1" in findings[0].evidence


def test_slack_token_emits_one_high_finding(tmp_path):
    # An obviously-fake token (no real Slack structure) that still trips our
    # looser xox[baprs]- signature, so this fixture is not itself a live secret.
    (tmp_path / "settings.yml").write_text(
        "slack:\n  webhook_token: xoxb-EXAMPLE-FAKE-SLACK-TOKEN-NOTREAL\n"
    )

    findings = check_secrets("payments-service", tmp_path)

    assert len(findings) == 1
    assert findings[0].severity == "High"
    assert "slack" in findings[0].evidence.lower()


def test_generic_credential_assignment_emits_one_medium_finding(tmp_path):
    (tmp_path / "application.properties").write_text(
        "spring.datasource.password=s3cr3t-Pa55word-Value\n"
    )

    findings = check_secrets("payments-service", tmp_path)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.severity == "Medium"
    assert finding.category == "security"
    assert "credential" in finding.evidence.lower()
    assert "application.properties:1" in finding.evidence


def test_credential_keys_are_recognised_across_naming_styles(tmp_path):
    (tmp_path / "config.yml").write_text(
        'apiKey: "live-9f8e7d6c5b4a3210ffee"\n'         # camelCase key
        "db_secret = 'A7x-Q2m-Z9k-W4p-L1t'\n"           # snake_case key
        'access_token: "tok_8h7g6f5e4d3c2b1a0z9y"\n'    # underscores
    )

    findings = check_secrets("payments-service", tmp_path)

    assert len(findings) == 3
    assert all(f.severity == "Medium" for f in findings)


def test_credential_key_with_a_prose_value_is_not_flagged(tmp_path):
    # A real secret has no whitespace; a credential-named key followed by prose
    # (typically a comment or doc note) is not a committed credential.
    (tmp_path / "Service.java").write_text(
        "// token: see the vault for the real value\n"
        "String note = \"secret = ask the platform team\";\n"
    )

    assert check_secrets("payments-service", tmp_path) == []


def test_placeholder_credential_values_are_not_flagged(tmp_path):
    (tmp_path / "application.properties").write_text(
        "password=\n"                                # empty
        "db.password=changeme\n"                     # common placeholder
        "api.key=your_api_key_here\n"                # template placeholder
        "secret=${VAULT_SECRET}\n"                   # env interpolation
        "token={{ github_token }}\n"                 # template interpolation
        "auth.password=<password>\n"                 # angle-bracket placeholder
    )

    assert check_secrets("payments-service", tmp_path) == []


def test_bearer_token_emits_one_high_finding(tmp_path):
    (tmp_path / "App.java").write_text(
        'header.put("Authorization", "Bearer sk-proj-abc123token456");\n'
    )

    findings = check_secrets("payments-service", tmp_path)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.severity == "High"
    assert finding.category == "security"
    assert "bearer" in finding.evidence.lower()
    assert "App.java:1" in finding.evidence


def test_bearer_prose_and_templates_are_not_flagged(tmp_path):
    (tmp_path / "docs.md").write_text(
        "Use Bearer token for authentication.\n"       # documentation prose
        "Set the header to Bearer authentication.\n"  # documentation prose
        "Authorization: Bearer ${BEARER_TOKEN}\n"      # template variable
        'Authorization: Bearer {{ bearer }}\n'          # template variable
        "Authorization: Bearer <token>\n"               # angle-bracket placeholder
        "Bearer required for access\n"                  # documentation prose
    )

    assert check_secrets("payments-service", tmp_path) == []


def test_jwt_emits_one_high_finding(tmp_path):
    (tmp_path / "config.yml").write_text(
        'token: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abc123\n'
    )

    findings = check_secrets("payments-service", tmp_path)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.severity == "High"
    assert finding.category == "security"
    assert "jwt" in finding.evidence.lower()


def test_jwt_dedup_with_bearer_emits_single_jwt_finding(tmp_path):
    # A real JWT line matches both the JWT pattern and the Bearer pattern.
    # Only the higher-specificity JWT finding should be emitted.
    (tmp_path / "service.ts").write_text(
        'this.authService = new AuthService("Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0In0.sig");\n'
    )

    findings = check_secrets("payments-service", tmp_path)

    assert len(findings) == 1
    assert "jwt" in findings[0].evidence.lower()
    assert "bearer" not in findings[0].evidence.lower()


def test_auth_method_call_with_hardcoded_token_emits_high_finding(tmp_path):
    (tmp_path / "AuthService.java").write_text(
        'class AuthService {\n'
        '    void init() { setToken("sk-live-abc123xyz"); }\n'
        '}\n'
    )

    findings = check_secrets("payments-service", tmp_path)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.severity == "High"
    assert finding.category == "security"
    assert "hardcoded" in finding.evidence.lower() or "auth" in finding.evidence.lower()
    assert "AuthService.java" in finding.evidence


def test_all_five_auth_methods_are_detected(tmp_path):
    (tmp_path / "AuthModule.ts").write_text(
        'withToken(\'js-token-123\');\n'
        'withAuth("auth-value");\n'
        'authenticate("auth-pass");\n'
        'setApiKey("key-abc");\n'
    )

    findings = check_secrets("payments-service", tmp_path)

    assert len(findings) == 4
    assert all(f.severity == "High" and f.category == "security" for f in findings)


def test_camelcase_variable_with_token_substring_is_not_flagged(tmp_path):
    """Variable names containing credential keywords as substrings (camelCase)
    should not trigger the generic credential assignment pattern.
    
    But a variable whose name IS a credential keyword (e.g. accessToken, sessionToken)
    SHOULD still be flagged — those ARE conventionally credential-named."""
    (tmp_path / "Auth.java").write_text(
        'class Auth {\n'
        '    String existingAccessToken = redisTemplate.opsForValue().get(userRefId);\n'
        '    String sessionToken = jwtUtils.generateToken(userRefId);\n'
        '    String mapToken = config.getString("token");\n'
        '    String hideSecret = vault.lookup("secret");\n'
        '}\n'
    )
    # accessToken = "..." WOULD match (keyword at start of identifier)
    # But these embedded cases should not
    assert len(check_secrets("payments-service", tmp_path)) == 0


def test_type_annotation_values_are_not_flagged(tmp_path):
    """TypeScript/JS type declarations (e.g. password: string) should not be
    flagged as hardcoded credentials."""
    (tmp_path / "Types.ts").write_text(
        'interface Config {\n'
        '    password: string;\n'
        '    token: string | undefined;\n'
        '    apiKey: Buffer;\n'
        '    callback: Promise<void>;\n'
        '    value: Array<Map<string, number>>;\n'
        '}\n'
    )

    assert check_secrets("payments-service", tmp_path) == []


def test_credential_keyword_at_start_of_identifier_still_matches(tmp_path):
    """Variable names that ARE credential keywords (not compound identifiers)
    should still be flagged."""
    (tmp_path / "Config.java").write_text(
        'class Config {\n'
        '    String accessToken = "sk-live-abc123";\n'
        '}\n'
    )
    findings = check_secrets("payments-service", tmp_path)
    assert len(findings) == 1


def test_non_target_methods_are_not_flagged(tmp_path):
    (tmp_path / "Config.java").write_text(
        'class Config {\n'
        '    void init() {\n'
        '        setConfig("value");\n'
        '        getToken("something");\n'
        '        authenticateUser("user");\n'
        '        withCredentials("cred");\n'
        '    }\n'
        '}\n'
    )

    # Only setToken/withToken/withAuth/authenticate/setApiKey are targeted.
    # authenticateUser() contains authenticate but has a suffix, so it should NOT match
    # (word boundary \b prevents it).
    findings = check_secrets("payments-service", tmp_path)

    assert len(findings) == 0


def test_variable_references_are_not_flagged(tmp_path):
    (tmp_path / "Auth.java").write_text(
        'class Auth {\n'
        '    void init() {\n'
        '        setToken(userToken);\n'
        '        withToken(getToken());\n'
        '    }\n'
        '}\n'
    )

    assert check_secrets("payments-service", tmp_path) == []


def test_integration_all_new_patterns_together(tmp_path):
    """Verify all new patterns work together in a realistic multi-file repo."""
    # Bearer token in .env
    (tmp_path / ".env").write_text(
        'AUTHORIZATION=Bearer sk-proj-abc123token456\n'
        'TEMPLATE_BEARER=Bearer ${TOKEN}\n'  # should NOT match
    )
    # JWT in JS
    (tmp_path / "api.ts").write_text(
        'const token = "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.sig";\n'
        'const header = {Authorization: "Bearer token"};'  # should NOT match (prose)
    )
    # Function call in Java
    (tmp_path / "Service.java").write_text(
        'class Service {\n'
        '    void init() { authenticate("hardcoded-auth-123"); }\n'
        '}\n'
    )
    # Clean file
    (tmp_path / "Clean.java").write_text('class Clean {}\n')

    findings = check_secrets("payments-service", tmp_path)

    # Should find: Bearer in .env, JWT in api.ts, authenticate() in Service.java
    assert len(findings) == 3
    locations = [f.location for f in findings]
    assert ".env" in locations
    assert "api.ts" in locations
    assert "Service.java" in locations
    # Evidence should not leak any token values
    evidence = "".join(f.evidence for f in findings)
    assert "sk-proj-abc123token456" not in evidence
    assert "eyJhbGciOiJIUzI1NiJ9" not in evidence
    assert "hardcoded-auth-123" not in evidence


def test_findings_sorted_by_location(tmp_path):
    """Verify findings from multiple checks are sorted by location."""
    (tmp_path / "zeta.java").write_text(
        'class Z { void init() { setToken("tok-1"); } }\n'
    )
    (tmp_path / "alpha.env").write_text(
        'key=Bearer abc-token\n'
    )
    (tmp_path / "beta.ts").write_text(
        'x = "Bearer eyJhbGciOiJIUzI1NiJ9.eyJ0ZXN0IjoiMSJ9.sig";\n'
    )

    findings = check_secrets("payments-service", tmp_path)

    # alpha.env (Bearer) should come first, then beta.ts (JWT), then zeta.java (fn call)
    assert len(findings) == 3
    assert findings[0].location == "alpha.env"
    assert findings[1].location == "beta.ts"
    assert findings[2].location == "zeta.java"
