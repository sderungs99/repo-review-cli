# repo-review-cli

A **throwaway, one-time** tool (see ADR-0004) that automates a pre-takeover code review of a large vendor application. It runs reproducible, self-computed checks across many repositories and emits severity-tagged findings, rendered both as an engineering-facing evidence set and a non-technical stakeholder summary. The tool is disposable; the findings it produces are durable evidence.

## Language

**Target System**:
The vendor application being evaluated for takeover — the full portfolio of repositories taken together (100+ Java/Spring Boot back-end services, one React web front-end, one React Native mobile front-end).
_Avoid_: the app, the codebase (ambiguous — could mean one repo)

**Finding**:
A single discrete issue surfaced by a check, carrying a severity and enough evidence to locate and act on it. Findings are facts; the tool never emits an opinion that isn't backed by a finding.
_Avoid_: issue, problem, result

**Subject Repo**:
A single repository under review — the unit of analysis. Checks run per Subject Repo and findings are attributed to it.
_Avoid_: project, module, service (a service may span more than one repo)

**Manifest**:
The checked-in input file listing every Subject Repo pinned to an exact commit SHA. The frozen definition of *what was reviewed*; the source of the review's reproducibility.
_Avoid_: config, repo list

**Cross-Repo Consistency Check**:
A check that only has meaning across Subject Repos rather than within one (e.g. whether all services share a common framework version). Distinct from the per-repo checks that produce most findings.
_Avoid_: global check, system check

**Check**:
A single automated analysis that runs against a Subject Repo (or across repos) and emits zero or more findings. In v1 every check is **self-computed** over a repo's source tree and config — no build, no runtime (see ADR-0002, ADR-0003).
_Avoid_: test, scan, rule

**Self-Computed Check**:
A check the tool runs itself over the source tree or repo config (file presence, grep patterns, LOC counts, config inspection). The core of the product. Contrast with findings *imported* from Sonar.
_Avoid_: native check, internal check

**Sonar-Integrity Check**:
A check whose purpose is to audit whether the vendor's Sonar data can be trusted at all. In v1 this means detecting **exclusions from config** in the checkout (`sonar-project.properties`, `pom.xml`, pipeline YAML); detecting disabled rules and bulk "won't fix" dispositions needs the live Sonar server and is deferred to phase 2 (ADR-0007).
_Avoid_: anti-gaming check, meta-check

**Severity**:
The ranking attached to a finding, on a fixed 5-level scale: **Critical / High / Medium / Low / Info**. Its origin is heterogeneous — *editorial* (baked into each hardcoded hygiene check), *mapped from CVSS* (dependency CVEs), or *mapped from Sonar's scale* (imported findings).

**Category**:
The dimension a finding belongs to (e.g. `security`, `dependencies`, `code-hygiene`, `documentation`, `testing`, `sonar-integrity`). A first-class field; findings roll up by category *and* severity, because for a takeover the category carries as much signal as the severity.
_Avoid_: type, kind, dimension (pick one: category)

**Findings File**:
The single canonical machine-readable JSON file every check writes into (`{repo, check_id, category, severity, evidence, location}`). The source of truth; both reports are pure projections of it (see ADR-0006).
_Avoid_: results file, output

**Technical Findings Report**:
The engineering-facing rendering of the findings set — the raw, complete evidence, intended for the user and their engineering team.
_Avoid_: the report (ambiguous), JSON output

**Stakeholder Report**:
The non-technical rolled-up narrative, derived strictly from the same findings set as the Technical Findings Report — never produced independently.
_Avoid_: exec summary, the report (ambiguous)
