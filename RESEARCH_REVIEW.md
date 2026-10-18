# Research Review: Autopoiesis, Enactive Systems, and Self-Evolving Agents

Status: research synthesis and design recommendations; not a claim that the repository implements biological autopoiesis or proven autonomous self-improvement.

Research snapshot: 2026-10-18.

## Executive finding

There is no single established software architecture that combines biological autopoiesis, enactive cognition, autonomous gap discovery, self-modifying code, homeostasis, and auditable release control into one mature, generally accepted implementation. The useful precedent is a set of neighboring fields, each solving a different subproblem.

Autopoiesis research asks how a network of processes continually produces and maintains the organization that constitutes the system. Enactive approaches emphasize ongoing coupling between an agent and its environment. Self-evolving coding agents modify prompts, tools, workflows, or code and evaluate the resulting performance. Program optimizers such as DSPy tune a declared program against an explicit metric. Multi-agent frameworks such as AutoGen and MetaGPT organize work among agents, but role-based collaboration is not by itself autopoiesis.

For Autopoiesis Core, the strongest practical synthesis is:
1. Operationalize the system's boundary, state, relations, viability conditions, and observable environment.
2. Discover candidate gaps from state + history + evidence, but treat each gap as a hypothesis rather than authority.
3. Generate multiple bounded candidates and preserve a lineage/archive rather than overwriting the only current version.
4. Evaluate candidates against declared, versioned objectives and invariants using repeatable tests.
5. Keep safety/homeostasis separate from optimization fitness.
6. Apply accepted changes only in an isolated workspace; execute checks there; require a separate release gate.
7. Persist the decision receipt, parent digest, candidate digest, evaluator/policy versions, measurements, test results, and recovery lineage.
8. Track capability retention and regression, not just improvement on one benchmark.

## Conceptual distinctions

### Autopoiesis is not synonymous with self-modifying code

In the biological and artificial-life literature, autopoiesis concerns a self-producing network of processes and constraints whose organization is maintained through its own activity. A program that rewrites its source code may be self-modifying without being autopoietic. Conversely, a model can investigate autopoietic organization without editing source code.

A software adaptation should therefore define a testable engineering analogue, not claim biological equivalence. A possible operational analogue is: the system maintains a declared set of critical components and relations; detects perturbations that threaten those conditions; proposes changes that restore or improve viability; and checks that the relations needed for continued operation remain intact. This is an engineering criterion inspired by autopoiesis, not a proof that the software is alive.

### Enactivism is not just an internal feedback loop

Enactive cognition emphasizes agent–environment coupling and the role of action in determining what is sensed and learned. For software, an analogy requires more than reading its own files: it needs observations from actual tests, task outcomes, runtime/resource signals, dependency changes, or other declared environment interactions. The observations and their provenance must be explicit.

### Self-evolution is a family of mechanisms

The object being evolved can be:
- a candidate program or algorithm;
- an agent's prompt, toolset, memory, or skills;
- a workflow/harness or collaboration topology;
- an evaluation environment or curriculum;
- model parameters.

These are distinct change surfaces with different risks. Autopoiesis Core should name the change surface for each candidate and avoid treating changes to task memory, source code, evaluator, and governance policy as equivalent.

## Project-by-project review

### 1. Autopoietic Networks

Source: https://github.com/gbragafibra/autopoietic-nets

Type: artificial-life / cellular-automaton experiment.

What it does: a grid of binary units is updated using logic gates and neighborhood state. A persistence-like quantity (Phi) rises when a unit retains its state; once a threshold is met, neighboring units are recruited into an ensemble. The threshold can depend on network entropy.

Useful idea: organization can be studied through local processes, persistence, boundaries/ensembles, and perturbation responses rather than being imposed entirely as a central controller.

Limits: the repository itself describes its behaviour as only approaching autopoietic characteristics and says the examples fall short of a full characterization. Its Phi/entropy rules are a model-specific heuristic, not a generally validated measure of software viability.

Transfer decision: **research inspiration only; do not copy the cellular automaton or its entropy formula into the core.** The useful question is whether Core can define measurable conditions for maintaining a bounded organization and detect when those conditions are lost.

### 2. Computational autopoiesis review

Source: https://pubmed.ncbi.nlm.nih.gov/15245628/

Type: review of roughly three decades of computational autopoiesis.

Useful idea: the field has produced increasingly rich lifelike simulations while exposing conceptual and methodological difficulties. This warns against claiming autopoiesis solely from visual complexity, persistence, or self-replication.

Transfer decision: use as a conceptual evaluation lens, not as a ready-made software architecture. Require operational criteria and counterexamples before assigning an “autopoietic” label.

### 3. Autopoiesis of the artificial: from systems to cognition (2023)

Source: https://doi.org/10.1016/j.biosystems.2023.104936

Type: conceptual review/argument about artificial systems and cognition.

Useful idea: the author argues that many AI approaches omit important autopoietic characteristics and that coupling between organization, history, and environment is difficult to capture. This supports keeping a clear distinction between a capable adaptive agent and a system meeting a stronger autopoietic criterion.

Limit: it is a theoretical analysis, not a drop-in implementation or empirical proof that a particular software architecture is autopoietic.

Transfer decision: use its questions to challenge architecture claims; do not treat it as evidence that the current Core is already autopoietic.

### 4. Deacon et al., “Autogenesis: An Alternative Path to Molecular Information” (2026)

Source: https://doi.org/10.1007/s13752-025-00528-1

Type: theoretical work on proto-life and the origin of molecular information.

Important naming correction: Deacon's **autogen/autogenesis** is a biological-origin and molecular-organization concept. It is not Microsoft's **AutoGen**, which is an LLM multi-agent software framework. They share similar names but solve different problems.

Useful idea: information and organization may arise from mutually constraining processes rather than from a single pre-specified controller.

Limit: the paper concerns molecular/proto-life theory; it does not validate a software self-improvement loop.

Transfer decision: conceptual inspiration only. Translate no molecular claims into software metrics without a separately justified model.

### 5. Enactive cognition and computational models

Source: https://pmc.ncbi.nlm.nih.gov/articles/PMC5972168/

Type: scholarly review of predictive processing, embodied cognition, enactivism, and active inference.

Useful idea: the paper emphasizes that approaches grouped under predictive processing differ in their commitments; it is a mistake to treat them as one unified theory. It also discusses attempts to connect self-organization with cognition.

Transfer decision: for Core, model environment coupling explicitly: observations, actions, consequences, and the next observation should form a trace. Keep claims about cognition or active inference out of the product description unless a specific formal model is implemented and evaluated.

### 6. DSPy optimizers

Source: https://github.com/stanfordnlp/dspy/blob/main/docs/docs/learn/optimization/optimizers.md

Type: optimization of LM programs against declared metrics and training examples.

What it contributes: a program, metric, and examples are explicit inputs; optimizers search for parameter/prompt/program configurations that score better.

Useful idea: make the objective and evaluation set explicit, versioned, and repeatable. This is a strong pattern for the candidate-evaluation layer.

Limits: DSPy optimization does not by itself provide autopoietic organization, an endogenous viability model, a general repository self-maintenance loop, or commit authorization.

Transfer decision: **borrow the explicit metric/evaluator interface, not the entire framework**. Keep objective optimization separate from invariants and release governance.

### 7. Self-Taught Optimizer (STOP, 2023)

Paper: https://arxiv.org/abs/2310.02304
Code: https://github.com/microsoft/stop

Type: recursive improvement of an LM-based code-generation scaffold.

What it contributes: an improver can propose changes to the program that itself performs improvement, then compare performance using a utility function. The authors explicitly note that the underlying language model is not modified, so this is not full recursive self-improvement. They also examine sandbox bypass concerns.

Useful idea: the improvement procedure itself can be a change surface and can be evaluated on downstream tasks.

Limits: proof-of-concept scale, dependence on an external LM, benchmark-specific utility, and sandbox/security concerns.

Transfer decision: later-stage experiment, after candidate evaluation, isolation, resource limits, and regression checks are dependable. Do not start by giving the current generator unrestricted write/execute access.

### 8. Darwin Gödel Machine (DGM, 2025)

Paper: https://arxiv.org/abs/2505.22954

Type: open-ended evolution of coding agents.

What it contributes: maintains an archive/tree of agent variants, selects variants to mutate, and empirically evaluates them on coding benchmarks. The paper reports improvements on SWE-bench and Polyglot and describes sandboxing and human oversight. It also explicitly acknowledges that proving general benefit of arbitrary self-modification is practically infeasible.

Useful ideas:
- preserve a lineage/archive of variants;
- explore from more than the single latest candidate;
- combine mutation with empirical evaluation;
- retain useful intermediate “stepping stones”;
- make safety and traceability part of the experimental design.

Limits:
- benchmark scores are proxies for capability, not universal fitness;
- a benchmark can be overfit;
- the paper does not prove indefinite, general-purpose self-improvement;
- reported results depend on the experimental setup and base models.

Transfer decision: **high-priority architecture pattern for a later evolution archive**, after the basic evaluation contract and sandbox are reliable. Preserve diversity, but never let archive membership imply acceptance or authority.

### 9. Gödel Agent (ACL 2025)

Paper: https://aclanthology.org/2025.acl-long.1354/
Preprint: https://arxiv.org/abs/2410.04444

Type: self-referential agent that can modify its own logic and improvement procedure.

What it contributes: expands the change surface beyond task policy to include the process that improves the policy. The authors report results on several domains.

Important caution: the paper's own project page notes mixed statistical evidence across benchmarks and that some optimization trials fell below the starting policy. This is a concrete reason to retain baselines, measure regressions, and never assume recursive modification is monotonically beneficial.

Transfer decision: research reference for future meta-evolution. Do not let Core rewrite its evaluator or governance policy in the same step that it is evaluated by them; otherwise the candidate can weaken its own exam.

### 10. AlphaEvolve (2025)

Paper: https://arxiv.org/abs/2506.13131
Google DeepMind overview: https://deepmind.google/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/

Type: LLM-guided evolutionary search for algorithms with automated evaluators.

What it contributes: candidate generation becomes productive when a domain has a meaningful automatic evaluator. It demonstrates the value of iterative program changes plus external measurable feedback in constrained algorithmic tasks.

Limits: task-specific evaluators and compute-intensive search do not automatically generalize to an open-ended software-maintenance objective. The evaluator defines what the search can optimize and can become a source of blind spots.

Transfer decision: borrow evaluator-driven candidate search for narrow, testable Core tasks. Do not assume an aggregate “fitness” score captures every important property of the system.

### 11. AutoGen (Microsoft)

Source: https://www.microsoft.com/en-us/research/project/autogen/publications/

Type: open-source framework for agentic applications and multi-agent conversations.

What it contributes: coordination between agents/tools, human-agent interaction, and patterns for orchestrating work.

Limit: assigning roles to multiple agents is not itself autopoiesis, endogenous gap discovery, or evidence-based state evolution. Coordination can also add latency, complexity, and additional failure paths.

Transfer decision: no dependency required for the core loop. A future research adapter could use an external agent as a candidate proposer or reviewer while keeping all authority and state-transition decisions inside Core.

### 12. MetaGPT

Paper: https://arxiv.org/abs/2308.00352
Code: https://github.com/geekan/MetaGPT

Type: role-based multi-agent software-production workflow.

What it contributes: standardized intermediate artefacts and checks across analyst, architect, engineer, and QA-like roles; reduces some inconsistency from naïvely chaining agent dialogue.

Limit: a workflow that imitates a software team is still a predesigned workflow; it does not establish that the system autonomously maintains its own organization. More roles do not automatically improve correctness.

Transfer decision: borrow only the idea of typed intermediate artefacts and explicit handoff contracts if the current single-process architecture later needs them. Avoid adding multiple agents merely for appearance.

## Comparative matrix

| Family | What evolves / is maintained | Main evidence signal | Strongest transferable pattern | What not to infer |
|---|---|---|---|---|
| Computational autopoiesis / ALife | Local processes, constraints, boundary/organization | Simulated dynamics and persistence | Define organization and perturbation response | That persistence or complexity proves life |
| Enactive / active-inference models | Agent–environment coupling and action/perception loop | Prediction/action outcomes under a formal model | Trace observations, actions, and consequences | That a feedback loop alone is enactivism |
| DSPy | Program/prompt configuration | Declared metric on examples | Explicit objective and evaluator | That metric optimization equals self-maintenance |
| STOP | Improver/scaffold code | Utility on downstream tasks | Evaluate the improver itself | That the base model or whole system has recursively improved |
| DGM | Agent code and agent variants | Coding benchmarks | Archive, lineage, mutation, empirical selection | That one benchmark proves general fitness |
| Gödel Agent | Agent logic and improvement procedure | Task benchmarks | Meta-level improvement is a distinct change surface | That recursive changes are always beneficial |
| AlphaEvolve | Candidate algorithms | Automated domain evaluator | Search with strong objective-specific feedback | That objective coverage is complete |
| AutoGen / MetaGPT | Agent workflow and collaboration | Task completion and artefact checks | Typed handoffs and tool orchestration | That multi-agent orchestration is autopoiesis |

## What this means for the current Autopoiesis Core repository

The current codebase should be treated as a small, bounded evolution harness, not as a completed autopoietic system. Its existing primitives are a reasonable foundation for deterministic state hashing, queueing, and preparing isolated patch artefacts. They do not yet establish the complete loop.

The new `evaluate_transition` prototype is an initial decision layer, but it has specific gaps that should be addressed before it is treated as a reliable gate:

1. **The invariant collection may be empty.** In that case, `all([])` passes. A production policy must declare whether zero invariants are allowed; fail closed by default when required invariants are absent.
2. **Checks currently inspect the candidate, not the parent/candidate pair.** Homeostasis and invariants may need to compare both states and verify that the parent was viable before claiming improvement.
3. **Purity is documented, not enforced.** Injected evaluator/check callbacks can mutate mutable inputs or access undeclared resources. Pass defensive copies or immutable representations and document the trust boundary.
4. **No configured state size/depth limits yet.** The design contract mentions them, but the prototype does not implement them.
5. **Reproducibility is only partially represented.** The receipt hashes fixtures, but it does not independently prove the evaluator was deterministic or that the implementation/version represented by the policy ID matches the actual callable.
6. **The result is not persisted by this function.** A receipt object is not a durable audit record.
7. **The evaluator is a caller-supplied scalar.** That is intentionally generic, but a real policy must specify metric meaning, units, direction, fixtures, noise/repeats, and regression guardrails.
8. **No CI evidence was observed for the recent commits.** These files have been created and fetched through GitHub; the relevant commit query returned no workflow runs. This does not prove the tests pass.

## Recommended order of work

### Phase A — Make the decision layer trustworthy

- Correct the prototype against the gaps above.
- Make invariants and homeostasis policy explicit, versioned, and fail-closed.
- Define a stable receipt schema and test its serialization/digest.
- Add tests for callback exceptions, mutation attempts, missing policy, invalid fixtures, threshold boundary, candidate regressions, and unchanged parent state.
- Obtain a real CI run on an exact SHA before proceeding.

### Phase B — Define the operational viability model

- Enumerate critical components and relations the Core requires to operate.
- Define observable indicators and their units: e.g. task-processing success, queue integrity, test success, error rate, resource limits, and recoverability. These are engineering candidates, not assumed universal autopoiesis metrics.
- Define perturbations, acceptable operating envelopes, recovery conditions, and counterexamples.
- Keep the fitness objective separate from non-negotiable invariants.

### Phase C — Endogenous gap discovery

Implement a read-only gap detector over state, history, and evidence:
`state + history + evidence -> gap hypothesis`

Each gap hypothesis should include supporting records, affected components/relations, missing capability, expected impact, counterevidence, confidence/uncertainty, and a proposed falsification test. A gap hypothesis must not mutate state, create authority, or authorize a patch.

### Phase D — Candidate search and isolated verification

- Generate bounded patch candidates from accepted gap hypotheses.
- Validate paths, hashes, size, syntax, and declared scope.
- Apply only to disposable isolated sandboxes.
- Run declared tests and regression checks in a controlled executor with resource limits.
- Compare candidate and parent on the same test set; preserve all outcomes and failure traces.

### Phase E — Archive and controlled evolution

- Store candidates and receipts as a lineage tree keyed by parent/candidate digest.
- Retain the current best verified version plus diverse, potentially useful alternatives.
- Detect regression, oscillation, repeated no-op, test overfitting, and capability loss.
- Keep evaluator changes separate from the candidates they judge.
- Require a separate release gate before repository changes become accepted.

### Phase F — Research adapters only when needed

Consider DSPy, DGM/STOP ideas, AutoGen, or MetaGPT only if a concrete bottleneck remains after the minimal loop is measured. Prefer a small local implementation for the core protocol. An external LLM or agent may propose candidates, but it should not own canonical state, acceptance policy, or release authority.

## Proposed acceptance criteria for calling the system self-evolving

A credible minimum demonstration would need all of the following:

1. Core observes a real, reproducible deficiency from its own state/history/evidence.
2. It emits a gap hypothesis without changing authority or accepted state.
3. It produces at least one bounded candidate with parent lineage.
4. A controlled evaluator compares parent and candidate using the same declared fixtures.
5. Safety/invariant checks can veto a candidate even when its score improves.
6. Failed or unresolved candidates leave the accepted state unchanged.
7. An accepted candidate can be applied in isolation, executed through declared checks, and compared against baseline.
8. A durable receipt records the exact digests, evaluator/policy versions, test results, and decision.
9. The system can reload the lineage after a fresh process starts.
10. A CI run proves the tested commit SHA; a separate runtime demonstration proves the end-to-end loop.
11. Repeated trials show that improvement is not a one-off or test-set artefact and that existing capabilities are not silently lost.

Until these criteria are demonstrated, describe the repository as an **early self-evolution prototype** rather than a proven autonomous autopoietic system.

## Source links

- Autopoietic Networks: https://github.com/gbragafibra/autopoietic-nets
- Computational autopoiesis review: https://pubmed.ncbi.nlm.nih.gov/15245628/
- Autopoiesis of the artificial: https://doi.org/10.1016/j.biosystems.2023.104936
- Enactive/embodied computational review: https://pmc.ncbi.nlm.nih.gov/articles/PMC5972168/
- Deacon et al., Autogenesis (2026): https://doi.org/10.1007/s13752-025-00528-1
- DSPy optimizers: https://github.com/stanfordnlp/dspy/blob/main/docs/docs/learn/optimization/optimizers.md
- STOP paper: https://arxiv.org/abs/2310.02304
- STOP code: https://github.com/microsoft/stop
- Darwin Gödel Machine: https://arxiv.org/abs/2505.22954
- Gödel Agent: https://aclanthology.org/2025.acl-long.1354/
- AlphaEvolve: https://arxiv.org/abs/2506.13131
- AutoGen publications: https://www.microsoft.com/en-us/research/project/autogen/publications/
- MetaGPT: https://arxiv.org/abs/2308.00352
- 2026 survey of self-evolving coding agents: https://arxiv.org/abs/2608.03392
- Curated self-evolving-agent research map: https://github.com/sukoji/awesome-self-evolving-agents

## Evidence note

This review is a literature-informed design synthesis based on the linked public sources and the repository files inspected in this session. It is not an exhaustive systematic review, an independent reproduction of every paper, or evidence that the recommended mechanisms are implemented. Research references should be revisited before adoption, and each adopted mechanism should be justified by a concrete observed gap and a testable acceptance criterion.

## Additional research: misevolution, process-level evaluation, and independent gates

Research update: 2026-10-18. These sources sharpen the risk analysis beyond endpoint benchmark scores.

### 15. Your Agent May Misevolve (ICLR 2026)

Paper: https://arxiv.org/abs/2509.26354
Code and experimental materials: https://github.com/ShaoShuai0605/Misevolution

Type: empirical study of failure modes in self-evolving LLM agents.

Finding: the authors study evolution across model, memory, tool, and workflow dimensions and report cases where adaptation causes undesirable changes, including degraded safety alignment after memory accumulation and vulnerabilities introduced through tool creation/reuse.

Transfer: model evolution surfaces separately; require regression tests for every changed surface; treat newly generated tools and accumulated memory as potentially unsafe artifacts; retain parent versions and rollback paths.

Limit: results concern the studied models, scenarios, and benchmarks; they do not quantify every risk in a repository-native system.

### 16. Beyond Endpoint Performance: Process-Level Evaluation of Self-Evolving Agents (2026)

Paper: https://arxiv.org/abs/2609.24663

Type: benchmark and evaluation-method proposal for evolving memories/skills.

Finding: endpoint scores alone can hide when capabilities appear, persist, or regress. The paper freezes artifacts at successive checkpoints and evaluates individual capabilities on held-out episodes. Its reported results include weaker transfer under distribution shift, retention losses on some paths, unreliable adaptation to new rules, and a gap between the best candidates generated and the updates ultimately selected.

Transfer: add checkpointed capability-retention tests, held-out evaluation, distribution-shift probes, and records for rejected candidates. Measure the selection procedure itself, not only the winning candidate. This supports keeping an archive of candidate results and comparing the selected candidate against the best measured alternative.

Limit: these are benchmark-specific findings; they motivate evaluation design rather than proving a universal failure rate.

### 17. Self-Evolving Agents with Anytime-Valid Certificates (2026)

Paper: https://arxiv.org/abs/2607.00871

Type: proposed architecture for self-evolving agents with versioned gates and auditable certificates.

Finding: the paper identifies a central endogeneity problem: an evolving policy can influence the data, evaluator, components, and hypothesis space used to judge itself. It proposes limiting the change surface and using versioned gates with explicit error budgets. The authors note that their reported evaluation is small and single-run, so variance and broader generalization remain open questions.

Transfer: do not let a candidate change the evaluator or governance policy that judges that same candidate. Bind every decision to a specific evaluator/policy version and evidence set. Treat a receipt as an auditable record of a decision, not as a mathematical proof of correctness unless the certificate's assumptions and guarantees are actually established.

Limit: this is a recent proposal with limited experiments, not a settled general solution.

### 18. Why Do Multi-Agent LLM Systems Fail? (NeurIPS 2025)

Paper: https://arxiv.org/abs/2503.13657
Dataset/project: https://github.com/multi-agent-systems-failure-taxonomy/MAST

Type: empirical failure analysis of multi-agent systems.

Finding: the authors identify recurring failure modes involving system design/specification, inter-agent misalignment, and task verification/termination. Their study cautions against assuming that agent count or role assignment automatically improves reliability.

Transfer: keep the Core loop single and minimal until a measured bottleneck justifies extra agents. If external agents are later used, specify typed input/output contracts, termination criteria, provenance, and an independent verification step.

Limit: the study covers particular frameworks and tasks; it does not establish that every multi-agent design underperforms.

## Revised architectural conclusions

The new evidence reinforces five non-negotiable design rules:

1. **Separate candidate generation from candidate authority.** Generated text, patches, tools, memories, and self-reported success are proposals/evidence, not permission to commit.
2. **Keep the judge stable during the trial.** Candidate code must not silently redefine the metric, fixtures, invariants, or acceptance threshold used to evaluate it.
3. **Evaluate trajectories, not only endpoints.** Preserve parent and candidate digests, intermediate receipts, failed attempts, test traces, and capability-retention results across checkpoints.
4. **Measure both gain and damage.** A candidate that improves one score but violates invariants or regresses an existing capability must not be accepted solely on aggregate fitness.
5. **Prefer reversible, small changes.** Use isolated workspaces, explicit change scopes, bounded execution, durable lineage, and rollback. Expand the change surface only after the smaller surface is proven.

For the current repository, the practical next sequence remains: (A) harden the evaluator transition function and its contract tests; (B) define a small operational viability model; (C) build read-only gap hypotheses from state/history/evidence; (D) connect bounded generation to sandbox execution and independent verification; (E) persist lineage and receipts; (F) demonstrate the complete loop at an exact SHA with CI and runtime evidence.

## Additional sources

- Your Agent May Misevolve (ICLR 2026): https://arxiv.org/abs/2509.26354
- Misevolution reference implementation: https://github.com/ShaoShuai0605/Misevolution
- Beyond Endpoint Performance: https://arxiv.org/abs/2609.24663
- Self-Evolving Agents with Anytime-Valid Certificates: https://arxiv.org/abs/2607.00871
- Why Do Multi-Agent LLM Systems Fail?: https://arxiv.org/abs/2503.13657
- MAST failure taxonomy and dataset: https://github.com/multi-agent-systems-failure-taxonomy/MAST
