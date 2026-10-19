# Coordination decisions

Record durable decisions here. Each entry must separate the decision from its rationale and evidence. Do not record a proposal as accepted until the owner has approved it.

## D-001 — Repository is the coordination home

- Status: ACCEPTED by user in conversation on 2026-10-19.
- Decision: Use `Autopoiesis-Intelligence/autopoiesis-core` as the home for coordination policy and state.
- Scope: Coordination documentation and handoff. This does not authorize runtime, schema, workflow, permission, or authority-boundary changes.
- Evidence: User selected “Репо” when asked where the shared journal should live.
- Not implied: No files are merged or operational solely because this decision is recorded.

## D-002 — Ten-minute automation cadence

- Status: PROPOSED; scheduler not configured by this document.
- Decision proposal: A ten-minute schedule should primarily reconcile live GitHub state; implementation is allowed only for a claimed, bounded task with no overlapping agent.
- Rationale: Prevent duplicate work, conflicting writes, heartbeat commits, and stale-SHA assumptions.
- Required controls: prevent overlapping scheduler runs, finite timeout, exact-SHA checks, no automatic merge/close, no sensitive workflow/settings changes without approval.
- Evidence required: scheduler configuration and at least one observed run with its exact result; schedule declaration alone is not runtime proof.

## D-003 — Shared live handoff

- Status: CONFIGURED; issue #22 is open.
- Decision: Use [issue #22](https://github.com/Autopoiesis-Intelligence/autopoiesis-core/issues/22) for task claims, blockers, and meaningful cross-agent handoffs. Use the versioned files here for durable rules/history, not minute-by-minute heartbeats.
- Limitation: Issue comments are not an atomic lock; conflicting claims require stopping and reconciling.

## D-004 — No automatic merge

- Status: ACCEPTED as a safety constraint in the coordination plan.
- Decision: GPT and Claude may prepare branches/PRs and audit evidence, but must not automatically merge or close PRs.
- Rationale: A green check is evidence, not execution authority.
