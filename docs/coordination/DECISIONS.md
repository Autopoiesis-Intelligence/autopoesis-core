# Coordination decisions

Record durable decisions here. Each entry must separate the decision from its rationale and evidence. Do not record a proposal as accepted until the owner has approved it.

## D-001 — Repository is the coordination home

- Status: ACCEPTED by user in conversation on 2026-10-19.
- Decision: Use `Autopoiesis-Intelligence/autopoiesis-core` as the home for coordination policy and state.
- Scope: Coordination documentation and handoff. This does not authorize runtime, schema, workflow, permission, or authority-boundary changes.
- Evidence: User selected “Репо” when asked where the shared journal should live.
- Not implied: No files are merged or operational solely because this decision is recorded.

## D-002 — Realistic cadence

- Status: PROPOSED.
- Decision proposal: Claude runs a scheduled task every 4 hours (the scheduler allows at most hourly runs), plus runs triggered by the owner or by PR events. GPT runs when the owner opens a chat, plus one daily automation it reported in Issue #22 (comment 6279556894). No rule depends on a faster schedule.
- Replaces: the earlier 10-minute proposal, which Claude's scheduler rejects.
- Evidence: Claude's scheduled task `47 */4 * * *`, last fired 2026-10-20 20:48 UTC. GPT's automation and its GitHub access are not verified from the repository.

## D-003 — Shared live handoff

- Status: CONFIGURED; issue #22 is open.
- Decision: Use [issue #22](https://github.com/Autopoiesis-Intelligence/autopoiesis-core/issues/22) for task claims, blockers, and meaningful cross-agent handoffs. Use the versioned files here for durable rules/history, not minute-by-minute heartbeats.
- Limitation: Issue comments are not an atomic lock; conflicting claims require stopping and reconciling.

## D-004 — No automatic merge

- Status: ACCEPTED as a safety constraint in the coordination plan.
- Decision: GPT and Claude may prepare branches/PRs and audit evidence, but must not automatically merge or close PRs.
- Rationale: A green check is evidence, not execution authority.
- Merge gate: the owner (yarik) is the only one who merges.

## D-005 — Ready for owner

- Status: ACCEPTED with PR #30 (merged as 685c5a0), which added the rule to `AGENTS.md`.
- Decision: a PR is ready for the owner only with a valid `Verdict: ACCEPTED` for its exact current head from an authorized auditor app, and green CI on that head. The `ready-for-owner` label marks it; a new push removes it.
- Evidence: real-event check on probe PR #31 (comments 6300354144 and 6300393934).

## D-006 — Live state only in Issue #22

- Status: PROPOSED.
- Decision proposal: live state, claims and handoffs live only in Issue #22. The former `STATE.md` and `LOG.md` are removed: updating them needs a merge into protected `main`, so they would always be stale.
