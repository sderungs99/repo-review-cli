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
over exhaustive recall). The known consequence:

- It will **miss** injection split across lines where the concatenated fragment
  carries no DML verb — e.g. a `q += "WHERE ..." + name` continuation, where the
  verb was on an earlier line.

If you ever need to trade precision for recall here (catch more at the cost of
more false positives), that's the knob to turn — broaden the keyword set in
`_SQL_STATEMENT_LITERAL` to include clause keywords (`WHERE`, `VALUES`, `SET`,
`FROM`) and/or track query-building across lines, accepting the extra noise.
