# Self-owned checks are the core; Sonar is supplementary

The product is a battery of small, **self-computed** deterministic checks over each repo's source tree and config (README presence, TODOs, file size, test presence, dependency/secret/license scanning, etc.). The vendor's SonarQube is a *supplementary corroboration input*, never the source of truth.

Rationale: relying on Sonar means trusting the vendor's rule profile, exclusions, and "won't fix" dispositions — the vendor grading their own homework. We therefore default to computing a check ourselves and reach for Sonar only when a check is both expensive to reproduce *and* trustworthy. We additionally run dedicated **Sonar-integrity checks** (detecting exclusions, disabled rules, bulk dispositions) whose whole purpose is to audit whether the Sonar data can be trusted.

## Consequences

- Disagreement between a self-computed result and Sonar (e.g. "Sonar reports 0 TODOs, we found 200") is itself a finding — evidence a rule was disabled.
- The tool's workload is mostly file-walking, grepping, counting, and config parsing plus a few API calls — not orchestrating heavyweight JVM analyzers. This keeps the runtime light and informs the implementation-language choice.
