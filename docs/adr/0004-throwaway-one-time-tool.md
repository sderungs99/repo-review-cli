# Throwaway, one-time tool — optimize for time-to-result

This tool is used once, to review the Target System before takeover, and discarded afterward. It is not a product, not reused across engagements, and has no maintenance horizon. We therefore optimize for time-to-result and clarity, and deliberately reject extensibility, configurability, and abstraction:

- Checks are **hardcoded**, not a declarative catalog or plugin system.
- No SARIF import/export, no generic adapter framework — just what this one review needs.
- Don't build for a second engagement; there won't be one.

## Consequences

- Code that looks "under-abstracted" is intentional — do not refactor it toward reuse.
- The tool is disposable, but its *output* is not: the SHA-pinned manifest (ADR-0001) and the emitted findings are archived as durable evidence for the takeover negotiation, since findings may need defending to the vendor later.
