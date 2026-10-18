from __future__ import annotations

from autopoesis.core import digest_state
from autopoesis.evaluation import EvaluationPolicy, evaluate_transition
from autopoesis.receipt_store import append_record, load_journal
from pathlib import Path
import tempfile
import json

policy = EvaluationPolicy(
    policy_id="journal-integration-smoke",
    policy_version="1",
    evaluator_id="counter-evaluator",
    evaluator_version="1",
    objective_direction="maximize",
)
parent = {"score": 1}
candidate = {"score": 2}
receipt = evaluate_transition(
    parent,
    candidate,
    expected_parent_digest=digest_state(parent),
    candidate_id="candidate-journal-smoke",
    policy=policy,
    evaluator=lambda state, fixtures: state["score"],
    fixtures={"fixture_set": "synthetic-v1"},
    invariants=(lambda state: state["score"] >= 0,),
    homeostasis_check=lambda before, after, fixtures: after["score"] >= before["score"],
)
assert receipt["decision"] == "ACCEPTED", receipt
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / "decisions.json"
    entry = append_record(path, {"receipt_id": "evaluation-smoke-1", **receipt})
    restored = load_journal(path)
    assert restored["entries"][0]["record"]["decision"] == receipt["decision"]
    assert restored["entries"][0]["record"]["candidate_state_digest"] == receipt["candidate_state_digest"]
    print(json.dumps({
        "evaluation_decision": receipt["decision"],
        "persisted": True,
        "policy_id": receipt["evaluation_policy_id"],
        "evaluator_id": receipt["evaluator_id"],
        "fixtures_digest_present": "fixtures_digest" in receipt,
        "journal_entry_digest": entry["entry_digest"],
    }, indent=2))
