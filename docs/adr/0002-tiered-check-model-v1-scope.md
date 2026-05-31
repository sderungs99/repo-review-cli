# v1 scope: static source + config analysis only

v1 checks read only a Subject Repo's **source tree and config** — no build, no test run, no runtime. Build and runtime verification are explicitly out of scope because the takeover contract obligates the vendor to deploy the Target System in *our* UAT environment; "does it build and run in our world" is therefore contractually theirs to demonstrate, not this tool's to check.

This supersedes an earlier three-tier model (Tier 1 source-only / Tier 2 buildability / Tier 3 build-artifact-consuming). Buildability and build-artifact checks are dropped, not merely deferred, on the strength of the UAT clause.

## Consequences

- No build environment, private-registry credentials, or container build images are needed — a large source of complexity and non-reproducibility disappears.
- "Tests exist" is a structural source check (does a test tree exist?); "tests pass" / coverage remain out of scope (UAT and the vendor's CI cover them).
- If the UAT clause weakens, clean-room buildability would be the first thing to reconsider.
