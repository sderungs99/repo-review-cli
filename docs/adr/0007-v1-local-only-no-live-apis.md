# v1 runs purely on local checkouts — no live APIs

v1 makes zero live external API calls. It operates only on local repo checkouts (cloned at the manifest SHAs) and the config files within them. No network at analysis time means no drift and a fully deterministic run from (checkouts + tool version).

- **ADO** is reduced to repo acquisition (`git clone` + record SHAs); it is not a runtime dependency.
- **Sonar-integrity** is detected from config in the checkout (`sonar-project.properties`, the Sonar plugin config in `pom.xml`, the Sonar task in ADO pipeline YAML) — not from the Sonar server.

## Consequences

- No auth, credentials, or rate-limit handling in v1.
- Deeper Sonar "gaming" signals that genuinely require the server — disabled quality-profile rules, won't-fix/false-positive dispositions — and live Sonar issue ingestion are deferred to **phase 2**, alongside the LLM semantic layer and LLM-written stakeholder narrative.
