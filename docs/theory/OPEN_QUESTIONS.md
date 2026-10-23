# Open questions

Contradictions, untested assumptions and decisions that are still open. An entry is closed only with a reason, a date and a link to what closed it; closed entries stay in place.

Entry fields: `Question`, `Why it matters`, `Options`, `Who decides`, `Blocks`, `Status`.

### OQ-001 — What is the exact form of X/R in autopoiesis-core?
- Question: which elements and relation types exist, what they mean, how they are measured, and how a candidate is checked against them.
- Why it matters: the product goal (CLM-007) cannot be tested until this is defined; today the core stores a task queue (CLM-006).
- Options: port the Gnosis-Core model; define a smaller model for the queue first; defer until A9.
- Who decides: the owner (`PROJECT_UNDERSTANDING.md`, "Open questions").
- Blocks: T2C-004, CLM-004.
- Status: UNRESOLVED

### OQ-002 — Which primary sources define autopoiesis for this project?
- Question: no primary source on autopoiesis is registered; the seed sources are reviews and second-hand summaries.
- Why it matters: CON-001 and CLM-002 rest on summaries nobody has checked.
- Options: register primary sources with exact bibliographic data after reading them; keep only reviews.
- Who decides: GPT or Manus propose sources with exact references; Claude checks them against the claim.
- Blocks: CLM-002 becoming SUPPORTED.
- Status: UNRESOLVED

### OQ-003 — Is second-order cybernetics a foundation of the project?
- Question: it is named as a foundation in the request that started this base, but no definition, source or project use is recorded (CON-006).
- Why it matters: a foundation without a definition cannot be used to check a design decision.
- Options: define it with sources and link it to a claim; drop it from the foundations.
- Who decides: the owner and GPT.
- Blocks: CON-006.
- Status: UNRESOLVED

### OQ-004 — `ACCEPTED` means two different things
- Question: `ACCEPTED` is both a knowledge status here and an audit verdict in `AGENTS.md`.
- Why it matters: a reader can take an accepted design claim for an accepted audit, or the reverse. The verdict parser is not affected: it only reads a `Verdict:` block that opens a PR comment.
- Options: keep the word and always say "knowledge status" or "verdict"; rename the knowledge status (for example `ADOPTED`).
- Who decides: the owner.
- Blocks: nothing; a naming risk.
- Status: UNRESOLVED

### OQ-005 — Should homeostasis and fitness be separate decisions on `main`?
- Question: the split exists only in an unmerged design document and prototype code (T2C-005).
- Why it matters: it decides how candidates are evaluated once evaluation exists.
- Options: adopt with a roadmap stage; leave as a design input until X/R exists.
- Who decides: the owner, after OQ-001.
- Blocks: CLM-004.
- Status: UNRESOLVED

### OQ-006 — How independent is "independent verification" with one shared account?
- Question: all agents use one GitHub account; verdicts are told apart only by the auditor app id. Do the generator and the verifier share assumptions, prompts or context?
- Why it matters: CLM-003 predicts a lower error rate only if the checks are independent.
- Options: measure disagreement between Codex reviews and Claude's own checks over time; require the verifier to use inputs the executor did not produce.
- Who decides: GPT and the owner propose a check; Claude implements tests.
- Blocks: CLM-003 moving beyond HYPOTHESIZED.
- Status: UNRESOLVED

### OQ-007 — Should the architecture baseline documents move to `main`?
- Question: `RESEARCH_REVIEW.md`, `ARCHITECTURE.md`, `STATE_TRANSITION_CONTRACT.md` and `IMPLEMENTATION_GAP_ANALYSIS.md` exist only on branch `docs/autopoiesis-core-architecture-baseline` (draft PR #3), together with unmerged code.
- Why it matters: this base cites them, but citations to an unmerged branch can change or disappear.
- Options: move the documents alone to `docs/` in a separate PR; fold their content into this base entry by entry; keep citing the branch at `c69452f`.
- Who decides: the owner.
- Blocks: nothing; it affects how stable the citations are.
- Status: UNRESOLVED
