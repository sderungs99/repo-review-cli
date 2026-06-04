# SHA-pinned manifest as the review input

A review must be reproducible and auditable months later, because it feeds a commercial takeover negotiation. We therefore take input from a checked-in **Manifest** that lists every Subject Repo pinned to an exact commit SHA, and operate on local checkouts at those SHAs — rather than auto-discovering repos from a VCS org (which drifts on every push). The manifest is the frozen, citable definition of *what was reviewed*.

## Consequences

- Cross-repo consistency checks operate over a known, fixed set.
- Updating the review means deliberately bumping SHAs in the manifest — drift is never silent.

## Amendment: SHA is optional

The `sha` field is optional. When omitted, the repo is acquired at the latest commit on its default branch instead of a pinned commit. This trades the reproducibility guarantee above for convenience (e.g. a quick review against current `HEAD`). An unpinned entry is *not* reproducible — two runs may review different code, and there is no citable record of what was reviewed. Pin a SHA for any review that must be auditable later.
