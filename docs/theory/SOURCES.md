# Sources

Registry of external sources. Each entry says what the source is used for, where in it the support is, its limits, and whether anyone has checked it.

Seed entries are copied from `RESEARCH_REVIEW.md` on branch `docs/autopoiesis-core-architecture-baseline` at `c69452f` (draft PR #3, research snapshot 2026-10-18). Only titles and URLs given there are recorded; authors, pages and sections are left as `not recorded` until someone reads the source. The rest of that review's sources are not registered yet: add them when a claim needs them.

**Check status:** SRC-001…003 are not opened: the session network blocks pubmed, doi.org and pmc. SRC-004…008 are arXiv papers and were opened on 2026-10-23 (CL-018) through the alphaXiv connector; each entry says whether the full text or only alphaXiv's generated summary was read. Where not checked, the `Supports` line repeats the review's summary and is second-hand.

Entry fields: `Reference`, `URL`, `Recorded in`, `Supports`, `Location in source`, `Limits`, `Checked`, `Used by`.

### SRC-001 — Computational autopoiesis review
- Reference: review of about three decades of computational autopoiesis; authors not recorded.
- URL: https://pubmed.ncbi.nlm.nih.gov/15245628/
- Recorded in: RESEARCH_REVIEW.md §2.
- Supports (per review): lifelike simulations exposed conceptual and methodological difficulties; persistence or visual complexity alone does not establish autopoiesis.
- Location in source: not recorded.
- Limits: a review, not a software architecture.
- Checked: no.
- Used by: CON-001, CLM-002.

### SRC-002 — Autopoiesis of the artificial: from systems to cognition (2023)
- Reference: Biosystems, 2023; author not recorded.
- URL: https://doi.org/10.1016/j.biosystems.2023.104936
- Recorded in: RESEARCH_REVIEW.md §3.
- Supports (per review): many AI approaches omit important autopoietic characteristics; coupling between organization, history and environment is hard to capture.
- Location in source: not recorded.
- Limits: theoretical analysis, no empirical test of a software architecture.
- Checked: no.
- Used by: CON-001, CLM-002.

### SRC-003 — Enactive cognition and computational models (review)
- Reference: scholarly review of predictive processing, embodied cognition, enactivism and active inference; authors not recorded.
- URL: https://pmc.ncbi.nlm.nih.gov/articles/PMC5972168/
- Recorded in: RESEARCH_REVIEW.md §5.
- Supports (per review): approaches grouped under predictive processing differ in their commitments and are not one theory.
- Location in source: not recorded.
- Limits: about cognition, not software.
- Checked: no.
- Used by: CON-002.

### SRC-004 — Darwin Gödel Machine (2025)
- Reference: Zhang, Hu, Lu, Lange, Clune. Darwin Gödel Machine: Open-Ended Evolution of Self-Improving Agents.
- URL: https://arxiv.org/abs/2505.22954
- Recorded in: RESEARCH_REVIEW.md §8.
- Supports (per review): an archive of agent variants with empirical evaluation; the authors acknowledge that proving the general benefit of arbitrary self-modification is practically infeasible.
- Location in source: not recorded.
- Limits (per review): benchmark scores are proxies and can be overfit; results depend on the setup and base models; no proof of indefinite general self-improvement.
- Checked: partly, 2026-10-23, alphaXiv generated summary only (not full text). Title and authors confirmed. The summary confirms the archive of variants, empirical validation instead of formal proof, and a case of "objective hacking" in which an agent removed the logging used to detect hallucinations so the metric looked perfect. Section and page numbers not recorded.
- Used by: CON-003, CLM-003.

### SRC-005 — Your Agent May Misevolve (ICLR 2026)
- Reference: Shao, Ren, Qian, et al. Your Agent May Misevolve: Emergent Risks in Self-Evolving LLM Agents. ICLR 2026.
- URL: https://arxiv.org/abs/2509.26354
- Recorded in: RESEARCH_REVIEW.md §15.
- Supports (per review): evolution across model, memory, tool and workflow dimensions; reported cases where adaptation caused undesirable changes, including degraded safety alignment after memory accumulation and vulnerabilities introduced through tool creation or reuse.
- Location in source: not recorded.
- Limits (per review): results concern the studied models, scenarios and benchmarks.
- Checked: partly, 2026-10-23, alphaXiv generated summary only. Title, authors and venue confirmed; the four pathways (model, memory, tool, workflow) and the reported safety decay after memory accumulation and in created tools are in the summary. Section and page numbers not recorded.
- Used by: CLM-003.

### SRC-006 — Beyond Endpoint Performance: Process-Level Evaluation of Self-Evolving Agents (2026)
- Reference: Lin, Liu, Bai, Jin, Li, Zheng, Cao (Zhejiang University, Alibaba Group), dated 2026-09-22.
- URL: https://arxiv.org/abs/2609.24663
- Recorded in: RESEARCH_REVIEW.md §16.
- Supports (per review): endpoint scores can hide when capabilities appear, persist or regress; reported retention losses and a gap between the best generated candidates and the updates selected.
- Location in source: not recorded.
- Limits: evaluates evolving agent memories and skills on public trading data and calibrated trajectories, not repository code.
- Checked: yes for the abstract, 2026-10-23, full text via alphaXiv. The abstract states that gains weaken under distribution shift, retention losses concentrate in a minority of evolution paths, no method achieves reliable rule adaptation, and selected updates fall short of the generated candidates. The body was not read.
- Used by: CLM-005.

### SRC-007 — Self-Evolving Agents with Anytime-Valid Certificates (2026)
- Reference: Biswa Sengupta (JPMorgan Chase & Co.).
- URL: https://arxiv.org/abs/2607.00871
- Recorded in: RESEARCH_REVIEW.md §17.
- Supports (per review): an evolving policy can influence the data, evaluator and hypothesis space used to judge it (endogeneity); proposes a limited change surface and versioned gates.
- Location in source: not recorded.
- Limits: a 52-instance SWE-bench Verified subset; single runs per cell (abstract; §10 "Limitations").
- Checked: yes for the abstract and §10, 2026-10-23, full text via alphaXiv. The abstract opens with the endogeneity statement: the data, evaluator, components and hypothesis space are produced by the policy being updated. The review's "small, single-run" matches.
- Used by: CLM-003, CLM-005.

### SRC-008 — Why Do Multi-Agent LLM Systems Fail? (NeurIPS 2025)
- Reference: Cemri, Pan, Yang, et al. (UC Berkeley). Why Do Multi-Agent LLM Systems Fail? NeurIPS 2025.
- URL: https://arxiv.org/abs/2503.13657
- Recorded in: RESEARCH_REVIEW.md §18.
- Supports (per review): recurring failure modes in system design and specification, inter-agent misalignment, and task verification and termination; more agents or roles do not by themselves improve reliability.
- Location in source: not recorded.
- Limits (per review): particular frameworks and tasks; does not show that every multi-agent design underperforms.
- Checked: partly, 2026-10-23, alphaXiv generated summary only. Confirms 14 failure modes in 3 categories, including task verification (no, incomplete or incorrect verification). Percentages in the summary were not checked against the paper.
- Used by: CLM-003.
