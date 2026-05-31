# Findings JSON is canonical; reports are pure projections

Every check writes into one canonical findings JSON file. Both the Technical Findings Report and the Stakeholder Report are rendered *from* that file and never generated independently. This guarantees the non-technical stakeholder view can never drift away from the underlying evidence.

In v1 both reports are generated **deterministically** (Markdown templates; the stakeholder report is a templated roll-up of counts by category/severity, top risks, worst repos — not prose). An LLM-written narrative summary is explicitly a **phase-2** feature layered on the same JSON; keeping it out of v1 preserves the deliverable's reproducibility (no model nondeterminism).

## Consequences

- Findings carry both a `severity` (5-level) and a first-class `category`; roll-ups are by both.
- Adding a new rendering means adding a projection, never a new source of truth.
