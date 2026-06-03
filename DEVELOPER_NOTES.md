# Developer Notes

Practical notes for people working on the checks. For the domain language see
[`CONTEXT.md`](CONTEXT.md); for the decisions behind the tool see
[`docs/adr/`](docs/adr).

## Check-specific caveats

### `sql-string-concat`

This check flags SQL queries assembled by string concatenation (the classic
`"SELECT ... WHERE id = " + id` injection pattern). It is a deliberately
**precise** heuristic: it only fires when a SQL-statement string literal (a DML
verb — `SELECT` / `INSERT INTO` / `UPDATE` / `DELETE FROM` / `MERGE INTO`) sits
directly adjacent to a `+` concatenation on the same line.

That precision is a trade-off chosen for a handover audit (low false positives
over exhaustive recall). The known consequences:

- It will **miss** injection split across lines where the concatenated fragment
  carries no DML verb — e.g. a `q += "WHERE ..." + name` continuation, where the
  verb was on an earlier line.
- Concatenation inside a JPA/Hibernate query annotation (`@Query`,
  `@NamedQuery`, `@NamedNativeQuery`) is **deliberately not flagged**: a Java
  annotation argument must be a constant expression, so the `+` can only join
  compile-time constants — no runtime input can reach the string (real inputs
  bind via `:named`/`?n` parameters). The guard (`_QUERY_ANNOTATION`) is
  **single-line**: it skips a line carrying the annotation token. A query
  annotation wrapped so the DML verb lands on a continuation line that has no
  annotation token will still false-positive. Robust multi-line handling needs
  paren-depth tracking, which is itself unreliable because SQL literals contain
  parens (`VALUES (?, ?)`), so it was left out on purpose.

If you ever need to trade precision for recall here (catch more at the cost of
more false positives), that's the knob to turn — broaden the keyword set in
`_SQL_STATEMENT_LITERAL` to include clause keywords (`WHERE`, `VALUES`, `SET`,
`FROM`) and/or track query-building across lines, accepting the extra noise.

**It flags the shape, not proven exploitability — on purpose.** The signal is "a
SQL-statement literal concatenated with a non-literal operand," which is exactly
how a query is assembled at runtime in a risky call such as `em.createQuery(...)`,
`em.createNativeQuery(...)`, or `jdbcTemplate.query*(...)` — those take a runtime
`String`, so concatenated user input flows into the SQL. (The parameterised
forms — `:named`/`?` bind parameters with no `+` next to the literal — carry no
concatenation and stay quiet, correctly.) But the check does **not** prove the
concatenated operand is attacker-reachable: `createQuery("SELECT ... " +
TABLE_CONSTANT)` joining a `static final` constant is a true positive for
"string-built query" and a false positive for "vulnerability." For a handover
audit that bias is deliberate — every flagged line is a query worth a human
glance to confirm the operand isn't user-controlled. Do not "fix" this by trying
to distinguish a constant *identifier* from a variable; that needs type/data-flow
analysis the tool intentionally does not do (ADR-0002). Telling a *literal* from a
non-literal, by contrast, is decidable from the one line and **is** done — see
below.

#### False-positive filters

Three filters narrow the check to runtime sinks. Each trades a little recall for
precision; all three were chosen deliberately for the handover audit.

- **Literal-only concatenation is excluded** (`_CONCAT_WITH_VARIABLE`). A finding
  fires only when the `+` joins the SQL literal to a *non-literal* operand (a
  variable, call, or `(expr)`). A split constant such as
  `"SELECT * FROM t " + "WHERE id = ?"` has no variable operand, so no runtime
  input can enter — this is **provably safe** to skip and costs no real recall.
  A constant-style *identifier* (`+ TABLE_NAME`) is still a non-literal, so it
  stays flagged, consistent with "flags the shape" above.
- **Logging and exception lines are skipped** (`_LOG_OR_THROW`): a line that is a
  `log`/`logger` call, a `System.out`/`System.err` write, or a `throw` reports or
  prints SQL rather than handing it to the database, so it is not a sink. Low
  risk: an injection that *only* exists inside a log/throw argument is not a query
  execution.
- **Test trees are skipped** (`_is_test_signal`): concatenated SQL under
  `src/test/**` or in `*.test.*`/`*.spec.*` files is almost always building an
  *expected*-query string, not a runtime sink. Medium risk — if a production
  query-builder helper lives under a test path it would be missed.

Not applied (offered but declined): excluding `ALL_CAPS` constant operands. That
would reverse the "flags the shape" decision and could hide a real issue behind a
mis-named variable, so constant-looking identifiers remain flagged.
