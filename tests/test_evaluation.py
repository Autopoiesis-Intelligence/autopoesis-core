import unittest

from autopoesis.core import digest_state
from autopoesis.evaluation import EvaluationPolicy, evaluate_transition


class TransitionEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.parent = {"score": 1}
        self.candidate = {"score": 2}
        self.fixtures = {"case": "fixed-v1"}
        self.policy = EvaluationPolicy(
            policy_id="test-policy",
            policy_version="1",
            evaluator_id="score-field",
            evaluator_version="1",
            objective_direction="maximize",
            min_improvement=0.5,
        )

    def evaluate(self, **overrides):
        args = {
            "parent_state": self.parent,
            "candidate_state": self.candidate,
            "expected_parent_digest": digest_state(self.parent),
            "candidate_id": "candidate-1",
            "policy": self.policy,
            "evaluator": lambda state, fixtures: state["score"],
            "fixtures": self.fixtures,
            "invariants": (lambda state: "score" in state,),
            "homeostasis_check": lambda state, fixtures: True,
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
        receipt = self.evaluate(candidate_state={"score": 1})
        self.assertEqual(receipt["decision"], "REJECTED")
        self.assertEqual(receipt["reason"], "NO_STATE_CHANGE")

    def test_rejects_stale_parent(self):
        receipt = self.evaluate(expected_parent_digest="stale")
        self.assertEqual(receipt["decision"], "REJECTED")
        self.assertEqual(receipt["reason"], "STALE_PARENT")

    def test_missing_evaluator_is_unresolved(self):
        receipt = self.evaluate(evaluator=None)
        self.assertEqual(receipt["decision"], "UNRESOLVED")
        self.assertEqual(receipt["reason"], "MISSING_EVALUATION_EVIDENCE")

    def test_missing_homeostasis_check_is_unresolved(self):
        receipt = self.evaluate(homeostasis_check=None)
        self.assertEqual(receipt["decision"], "UNRESOLVED")
        self.assertEqual(receipt["reason"], "HOMEOSTASIS_CHECK_MISSING")

    def test_homeostasis_violation_rejects_even_if_fitness_improves(self):
        receipt = self.evaluate(homeostasis_check=lambda state, fixtures: False)
        self.assertEqual(receipt["decision"], "REJECTED")
        self.assertEqual(receipt["reason"], "HOMEOSTASIS_BOUND_VIOLATION")

    def test_invariant_failure_rejects(self):
        receipt = self.evaluate(invariants=(lambda state: False,))
        self.assertEqual(receipt["decision"], "REJECTED")
        self.assertEqual(receipt["reason"], "INVARIANT_VIOLATION")

    def test_missing_invariant_result_is_unresolved(self):
        receipt = self.evaluate(invariants=(lambda state: None,))
        self.assertEqual(receipt["decision"], "UNRESOLVED")
        self.assertEqual(receipt["reason"], "INVARIANT_RESULT_MISSING_OR_INVALID")

    def test_insufficient_improvement_is_rejected(self):
        receipt = self.evaluate(
            candidate_state={"score": 1.25},
            evaluator=lambda state, fixtures: state["score"],
        )
        self.assertEqual(receipt["decision"], "REJECTED")
        self.assertEqual(receipt["reason"], "INSUFFICIENT_IMPROVEMENT")

    def test_minimize_objective_uses_reversed_delta(self):
        policy = EvaluationPolicy(
            policy_id="min-policy",
            policy_version="1",
            evaluator_id="error-rate",
            evaluator_version="1",
            objective_direction="minimize",
            min_improvement=0.1,
        )
        receipt = self.evaluate(
            parent_state={"error": 0.8},
            candidate_state={"error": 0.5},
            expected_parent_digest=digest_state({"error": 0.8}),
            policy=policy,
            evaluator=lambda state, fixtures: state["error"],
            invariants=(lambda state: "error" in state,),
        )
        self.assertEqual(receipt["decision"], "ACCEPTED")
        self.assertAlmostEqual(receipt["improvement"], 0.3)

    def test_non_finite_measurement_is_unresolved(self):
        receipt = self.evaluate(evaluator=lambda state, fixtures: float("nan"))
        self.assertEqual(receipt["decision"], "UNRESOLVED")
        self.assertEqual(receipt["reason"], "FITNESS_EVALUATION_ERROR")


if __name__ == "__main__":
    unittest.main()
