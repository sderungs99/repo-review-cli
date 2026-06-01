# repo-review-cli

A **throwaway, one-time** tool that automates a pre-takeover code review of a
large vendor application (the **Target System**). It runs reproducible,
self-computed **Checks** across many **Subject Repos** and emits severity-tagged
**Findings**, rendered as both an engineering-facing evidence set and a
non-technical stakeholder summary.

The tool is disposable; the findings it produces are durable evidence. See
[`CONTEXT.md`](CONTEXT.md) for the domain language and [`docs/adr/`](docs/adr)
for the decisions behind it.

## How it works

The whole pipeline is one vertical path:

1. **Read the Manifest** — a checked-in JSON file listing every Subject Repo
   pinned to an exact commit SHA (ADR-0001). The frozen definition of *what was
   reviewed*.
2. **Acquire each repo** — `git clone` + checkout at the pinned SHA into a local
   working area. This is the only git interaction; v1 makes no live API calls
   (ADR-0007).
3. **Run the Checks** — each Check is a hardcoded analysis over the local
   checkout's source tree and config (ADR-0002, ADR-0004). v1 ships the
   README-presence check.
4. **Write the canonical Findings File** — one JSON, every Finding shaped
   `{repo, check_id, category, severity, evidence, location}` (ADR-0006). The
   single source of truth.
5. **Render both reports** as pure projections of that JSON — never generated
   independently:
   - **Technical Findings Report** — findings grouped by repo and category.
   - **Stakeholder Report** — a deterministic roll-up of counts by category and
     severity.

Running twice over the same Manifest produces byte-identical output: there is no
network at analysis time and findings are written in a canonical order.

## Usage

With a `manifest.json` in the current directory:

```bash
python -m repo_review
```

Or point at explicit paths:

```bash
python -m repo_review --manifest path/to/manifest.json --out path/to/dir
```

Defaults: `--manifest ./manifest.json`, `--out ./reports/`. Writes:

- `findings.json` — the canonical Findings File
- `technical-findings-report.md`
- `stakeholder-report.md`

### Manifest format

A JSON object with a `repos` array; each entry is a Subject Repo pinned to a SHA.
`source` may be any git URL or a local path. See
[`manifest.example.json`](manifest.example.json):

```json
{
  "repos": [
    { "name": "payments-service", "source": "/abs/path/or/git-url", "sha": "<40-char commit SHA>" },
    { "name": "auth-service", "source": "/abs/path/or/git-url", "sha": "<40-char commit SHA>" }
  ]
}
```

## Development

Requires Python 3.12+.

```bash
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
```
