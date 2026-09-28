import unittest

import pandas as pd

from src.analysis.final_pilot_sensitivity import (
    _build_sensitivity_plan,
    _nominal_seed_stability,
    _parameter_comparison,
    _validate_seeds,
)


class FinalPilotSensitivityTests(unittest.TestCase):
    def test_validates_and_preserves_seed_order(self):
        seeds = _validate_seeds(
            [11, 23, 42, 73, 101, 23],
            reference_seed=42,
        )

        self.assertEqual(
            seeds,
            [11, 23, 42, 73, 101],
        )

    def test_reference_seed_must_be_present(self):
        with self.assertRaises(ValueError):
            _validate_seeds(
                [11, 23, 73, 101],
                reference_seed=42,
            )

    def test_builds_expected_final_plan(self):
        plan = _build_sensitivity_plan(
            seeds=[11, 23, 42, 73, 101],
            reference_seed=42,
            destination_multipliers=[0.75, 1.0, 1.25],
            mode_multipliers=[0.75, 1.0, 1.25],
            include_mode_homogenized=True,
        )

        self.assertEqual(
            len(
                plan.loc[
                    plan["experiment"]
                    == "nominal_seed"
                ]
            ),
            5,
        )
        self.assertEqual(
            len(plan),
            10,
        )
        self.assertEqual(
            len(
                plan.loc[
                    plan["experiment"]
                    == "destination_decay"
                ]
            ),
            2,
        )
        self.assertEqual(
            len(
                plan.loc[
                    plan["experiment"]
                    == "mode_decay"
                ]
            ),
            2,
        )
        self.assertEqual(
            len(
                plan.loc[
                    plan["experiment"]
                    == "mode_homogenized"
                ]
            ),
            1,
        )

    def test_seed_stability_uses_nominal_runs_only(self):
        runs = pd.DataFrame(
            {
                "experiment": [
                    "nominal_seed",
                    "nominal_seed",
                    "nominal_seed",
                    "destination_decay",
                ],
                "analysis_retention_pct": [
                    97.0,
                    96.0,
                    98.0,
                    50.0,
                ],
                "used_both_share_pct": [
                    53.0,
                    54.0,
                    55.0,
                    10.0,
                ],
                "flow_ge_5_both": [
                    42,
                    50,
                    48,
                    1,
                ],
                "flow_ge_10_both": [
                    0,
                    1,
                    0,
                    0,
                ],
                "H_soc_mean_supported_baseline": [
                    0.70,
                    0.72,
                    0.71,
                    0.20,
                ],
                "H_soc_mean_supported_differentiated": [
                    0.66,
                    0.67,
                    0.65,
                    0.10,
                ],
                "sufficient_delta_H_soc_mean": [
                    -0.12,
                    -0.10,
                    -0.11,
                    0.50,
                ],
                "paired_delta_H_soc_mean": [
                    -0.03,
                    -0.02,
                    -0.04,
                    0.60,
                ],
            }
        )

        stability = _nominal_seed_stability(
            runs
        )

        row = stability.loc[
            stability["metric"]
            == "sufficient_delta_H_soc_mean"
        ].iloc[0]

        self.assertEqual(
            row["n_valid_seeds"],
            3,
        )
        self.assertAlmostEqual(
            row["same_sign_as_median_share"],
            1.0,
        )

    def test_mode_homogenized_uses_same_seed_nominal_reference(self):
        runs = pd.DataFrame(
            {
                "run_id": [
                    "nominal_seed_42",
                    "nominal_seed_73",
                    "mode_homogenized_seed_73",
                ],
                "experiment": [
                    "nominal_seed",
                    "nominal_seed",
                    "mode_homogenized",
                ],
                "seed": [
                    42,
                    73,
                    73,
                ],
                "destination_decay_multiplier": [
                    1.0,
                    1.0,
                    1.0,
                ],
                "mode_decay_multiplier": [
                    1.0,
                    1.0,
                    1.0,
                ],
                "homogenize_differentiated_mode": [
                    False,
                    False,
                    True,
                ],
                "analysis_retention_pct": [
                    97.0,
                    98.0,
                    98.0,
                ],
                "used_both_share_pct": [
                    53.0,
                    55.0,
                    54.0,
                ],
                "flow_ge_5_both": [
                    42,
                    48,
                    46,
                ],
                "flow_ge_10_both": [
                    0,
                    1,
                    1,
                ],
                "H_soc_mean_supported_baseline": [
                    0.71,
                    0.74,
                    0.74,
                ],
                "H_soc_mean_supported_differentiated": [
                    0.66,
                    0.68,
                    0.70,
                ],
                "sufficient_delta_H_soc_mean": [
                    -0.12,
                    -0.06,
                    -0.04,
                ],
                "paired_delta_H_soc_mean": [
                    -0.03,
                    -0.02,
                    -0.01,
                ],
            }
        )

        comparison = _parameter_comparison(
            runs,
            reference_seed=42,
        )

        mechanism = comparison.loc[
            comparison["experiment"]
            == "mode_homogenized"
        ].iloc[0]

        self.assertEqual(
            mechanism["reference_seed"],
            73,
        )
        self.assertEqual(
            mechanism["reference_kind"],
            "same_seed_nominal",
        )
        self.assertAlmostEqual(
            mechanism[
                "change_sufficient_delta_H_soc_mean"
            ],
            0.02,
        )

    def test_parameter_comparison_uses_reference_seed(self):
        runs = pd.DataFrame(
            {
                "run_id": [
                    "nominal_seed_42",
                    "destination_decay_0p75",
                ],
                "experiment": [
                    "nominal_seed",
                    "destination_decay",
                ],
                "seed": [
                    42,
                    42,
                ],
                "destination_decay_multiplier": [
                    1.0,
                    0.75,
                ],
                "mode_decay_multiplier": [
                    1.0,
                    1.0,
                ],
                "homogenize_differentiated_mode": [
                    False,
                    False,
                ],
                "analysis_retention_pct": [
                    97.0,
                    96.0,
                ],
                "used_both_share_pct": [
                    53.0,
                    52.0,
                ],
                "flow_ge_5_both": [
                    42,
                    40,
                ],
                "flow_ge_10_both": [
                    0,
                    0,
                ],
                "H_soc_mean_supported_baseline": [
                    0.71,
                    0.70,
                ],
                "H_soc_mean_supported_differentiated": [
                    0.66,
                    0.65,
                ],
                "sufficient_delta_H_soc_mean": [
                    -0.12,
                    -0.10,
                ],
                "paired_delta_H_soc_mean": [
                    -0.03,
                    -0.02,
                ],
            }
        )

        comparison = _parameter_comparison(
            runs,
            reference_seed=42,
        )

        self.assertEqual(
            len(comparison),
            1,
        )
        self.assertAlmostEqual(
            comparison.iloc[0][
                "change_sufficient_delta_H_soc_mean"
            ],
            0.02,
        )
        self.assertTrue(
            comparison.iloc[0][
                "same_sign_sufficient_delta_H_soc_mean"
            ]
        )


if __name__ == "__main__":
    unittest.main()
