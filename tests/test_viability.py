import unittest

from autopoesis.viability import MetricBound, ViabilityPolicy, evaluate_viability


class ViabilityEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.parent = {"memory_mb": 120, "errors": 3}
        self.candidate = {"memory_mb": 128, "errors": 1}
        self.policy = ViabilityPolicy(
            policy_id="core-envelope",
            policy_version="1",
            metrics=(
                MetricBound("memory", "process-memory", "1", "MB", maximum=256),
                MetricBound("errors", "validation-errors", "1", "count", minimum=0, maximum=2),
            ),
        )

    def measure(self, state, metric):
        return state["memory_mb"] if metric.name == "memory" else state["errors"]

    def test_candidate_within_explicit_bounds_is_viable(self):
        result = evaluate_viability(self.parent, self.candidate, policy=self.policy, measure=self.measure)
        self.assertEqual(result["decision"], "ACCEPTED")
        self.assertEqual(result["reason"], "VIABILITY_BOUNDS_SATISFIED")
        self.assertEqual(result["measurements"]["memory"]["unit"], "MB")

    def test_candidate_outside_bound_is_rejected(self):
        candidate = {"memory_mb": 300, "errors": 1}
        result = evaluate_viability(self.parent, candidate, policy=self.policy, measure=self.measure)
        self.assertEqual(result["decision"], "REJECTED")
        self.assertEqual(result["violations"], ["memory"])

    def test_missing_policy_or_measurer_is_unresolved(self):
        self.assertEqual(
            evaluate_viability(self.parent, self.candidate, policy=None, measure=self.measure)["decision"],
            "UNRESOLVED",
        )
        self.assertEqual(
            evaluate_viability(self.parent, self.candidate, policy=self.policy, measure=None)["decision"],
            "UNRESOLVED",
        )

    def test_empty_metric_set_fails_closed(self):
        policy = ViabilityPolicy("empty", "1", ())
        result = evaluate_viability(self.parent, self.candidate, policy=policy, measure=self.measure)
        self.assertEqual(result["decision"], "UNRESOLVED")
        self.assertEqual(result["reason"], "INVALID_VIABILITY_POLICY")

    def test_non_finite_measurement_is_unresolved(self):
        result = evaluate_viability(
            self.parent, self.candidate, policy=self.policy,
            measure=lambda state, metric: float("nan"),
        )
        self.assertEqual(result["decision"], "UNRESOLVED")
        self.assertEqual(result["reason"], "VIABILITY_MEASUREMENT_ERROR")

    def test_duplicate_metric_names_are_invalid(self):
        policy = ViabilityPolicy("duplicate", "1", (
            MetricBound("same", "a", "1", "unitless", minimum=0),
            MetricBound("same", "b", "1", "unitless", maximum=1),
        ))
        result = evaluate_viability(self.parent, self.candidate, policy=policy, measure=self.measure)
        self.assertEqual(result["reason"], "INVALID_VIABILITY_POLICY")

    def test_callback_mutation_is_isolated(self):
        def mutate(state, metric):
            state["memory_mb"] = -1
            return 100.0 if metric.name == "memory" else 1.0
        result = evaluate_viability(self.parent, self.candidate, policy=self.policy, measure=mutate)
        self.assertEqual(result["decision"], "ACCEPTED")
        self.assertEqual(self.parent["memory_mb"], 120)
        self.assertEqual(self.candidate["memory_mb"], 128)

    def test_parent_and_candidate_are_both_measured(self):
        seen = []
        def track(state, metric):
            seen.append(state["memory_mb"])
            return state["memory_mb"] if metric.name == "memory" else state["errors"]
        evaluate_viability(self.parent, self.candidate, policy=self.policy, measure=track)
        self.assertIn(120, seen)
        self.assertIn(128, seen)


if __name__ == "__main__":
    unittest.main()
