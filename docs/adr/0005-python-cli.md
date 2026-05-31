# Python CLI

The tool is a Python command-line program. Given the throwaway, one-time nature (ADR-0004) and a workload that is mostly file-walking, grepping, line-counting, config parsing, and a few HTTP calls, the deciding factor is time-to-result — which favors the language the team is already fluent in. The team writes Python, not Go.

Go's advantages (single static binary, distribution, long-term reproducibility) pay off over a tool's long distributed life, which this tool does not have. Learning Go here was explicitly rejected: a one-time tool backing a commercial negotiation is the wrong place to absorb new-language ramp-up cost and inexperience bugs.

## Consequences

- Reproducibility comes from a pinned dependency lockfile plus the SHA-pinned manifest, not from a compiled binary.
- Keep the third-party surface small; prefer the stdlib (`pathlib`, `re`, `json`, `subprocess`, `xml`/`tomllib`, `httpx`).
