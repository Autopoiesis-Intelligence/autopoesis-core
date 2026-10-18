import unittest

from autopoesis.core import digest_state
from autopoesis.evaluation import EvaluationPolicy, evaluate_transition


class TransitionEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.parent = {"score": 1}
        self.candidate = {"score": 2}
        self.fixtures = {"case": "fixed-v1"}
        self.policy = EvaluationPolicy(
            policy_id="test-policy", policy_version="1",
            evaluator_id="score-field", evaluator_version="1",
            objective_direction="maximize", min_improvement=0.5,
        )

    def evaluate(self, **overrides):
        args = {
            "parent_state": self.parent, "candidate_state": self.candidate,
            "expected_parent_digest": digest_state(self.parent),
            "candidate_id": "candidate-1", "policy": self.policy,
            "evaluator": lambda state, fixtures: state["score"],
            "fixtures": self.fixtures,
            "invariants": (lambda state: "score" in state,),
            "homeostasis_check": lambda parent, candidate, fixtures: True,
        }
        args.update(overrides)
        return evaluate_transition(**args)

    def test_accepts_measurable_improvement_when_all_gates_pass(self):
        receipt = self.evaluate()
        self.assertEqual(receipt["decision"], "ACCEPTED")
        self.assertEqual(receipt["reason"], "IMPROVEMENT_THRESHOLD_MET")
        self.assertEqual(receipt["parent_state_digest"], digest_state(self.parent))
        self.assertEqual(receipt["candidate_state_digest"], digest_state(self.candidate))
        self.assertEqual(receipt["improvement"], 1.0)

    def test_rejects_noop(self):
        self.assertEqual(self.evaluate(candidate_state={"score": 1})["reason"], "NO_STATE_CHANGE")

    def test_rejects_stale_parent(self):
        self.assertEqual(self.evaluate(expected_parent_digest="stale")["reason"], "STALE_PARENT")

    def test_missing_evaluator_is_unresolved(self):
        self.assertEqual(self.evaluate(evaluator=None)["reason"], "MISSING_EVALUATION_EVIDENCE")

    def test_missing_homeostasis_check_is_unresolved(self):
        self.assertEqual(self.evaluate(homeostasis_check=None)["reason"], "HOMEOSTASIS_CHECK_MISSING")

    def test_homeostasis_receives_both_states(self):
        seen = {}
        def check(parent, candidate, fixtures):
            seen["parent"] = parent["score"]
            seen["candidate"] = candidate["score"]
            return candidate["score"] >= parent["score"]
        self.assertEqual(self.evaluate(homeostasis_check=check)["decision"], "ACCEPTED")
        self.assertEqual(seen, {"parent": 1, "candidate": 2})

    def test_homeostasis_violation_rejects_even_if_fitness_improves(self):
        self.assertEqual(self.evaluate(homeostasis_check=lambda p, c, f: False)["reason"],
                         "HOMEOSTASIS_BOUND_VIOLATION")

    def test_empty_invariants_fail_closed(self):
        receipt = self.evaluate(invariants=())
        self.assertEqual(receipt["decision"], "UNRESOLVED")
        self.assertEqual(receipt["reason"], "INVARIANTS_MISSING")

    def test_invariant_failure_rejects(self):
        self.assertEqual(self.evaluate(invariants=(lambda state: False,))["reason"],
                         "INVARIANT_VIOLATION")

    def test_missing_invariant_result_is_unresolved(self):
        self.assertEqual(self.evaluate(invariants=(lambda state: None,))["reason"],
                         "INVARIANT_RESULT_MISSING_OR_INVALID")

    def test_insufficient_improvement_is_rejected(self):
        self.assertEqual(self.evaluate(candidate_state={"score": 1.25})["reason"],
                         "INSUFFICIENT_IMPROVEMENT")

    def test_minimize_objective_uses_reversed_delta(self):
        parent, candidate = {"error": 0.8}, {"error": 0.5}
        policy = EvaluationPolicy("min-policy", "1", "error-rate", "1", "minimize", 0.1)
        receipt = self.evaluate(
            parent_state=parent, candidate_state=candidate,
            expected_parent_digest=digest_state(parent), policy=policy,
            evaluator=lambda state, fixtures: state["error"],
            invariants=(lambda state: "error" in state,),
        )
        self.assertEqual(receipt["decision"], "ACCEPTED")
        self.assertAlmostEqual(receipt["improvement"], 0.3)

    def test_non_finite_measurement_is_unresolved(self):
        self.assertEqual(self.evaluate(evaluator=lambda state, fixtures: float("nan"))["reason"],
                         "FITNESS_EVALUATION_ERROR")

    def test_state_size_limit_is_enforced(self):
        policy = EvaluationPolicy("p", "1", "e", "1", "maximize", max_state_bytes=8)
        self.assertEqual(self.evaluate(policy=policy)["reason"], "STATE_SIZE_LIMIT_EXCEEDED")

    def test_state_depth_limit_is_enforced(self):
        policy = EvaluationPolicy("p", "1", "e", "1", "maximize", max_state_depth=1)
        self.assertEqual(self.evaluate(policy=policy)["reason"], "STATE_DEPTH_LIMIT_EXCEEDED")

    def test_callbacks_cannot_mutate_original_inputs(self):
        def mutating_evaluator(state, fixtures):
            original_score = float(state["score"])
            state["score"] = 999
            fixtures["case"] = "mutated"
            return original_score
        receipt = self.evaluate(evaluator=mutating_evaluator)
        self.assertEqual(receipt["decision"], "ACCEPTED")
        self.assertEqual(self.parent, {"score": 1})
        self.assertEqual(self.candidate, {"score": 2})
        self.assertEqual(self.fixtures, {"case": "fixed-v1"})

    def test_threshold_boundary_is_accepted(self):
        policy = EvaluationPolicy("p", "1", "e", "1", "maximize", 1.0)
        self.assertEqual(self.evaluate(policy=policy)["decision"], "ACCEPTED")


if __name__ == "__main__":
    unittest.main()
