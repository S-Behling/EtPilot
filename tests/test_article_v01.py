import unittest

import numpy as np
import pandas as pd

from src.analysis.article_v01 import (
    _add_entropy_contributions,
    _bootstrap_scenario,
    _entropy_term,
    _weighted_mean,
)


class ArticleV01Tests(unittest.TestCase):
    def test_weighted_mean(self):
        result = _weighted_mean(
            [0.0, 1.0],
            [1.0, 3.0],
        )
        self.assertAlmostEqual(
            result,
            0.75,
        )

    def test_entropy_terms_reconstruct_delta(self):
        frame = pd.DataFrame(
            {
                "p_low_baseline": [0.2],
                "p_middle_baseline": [0.6],
                "p_high_baseline": [0.2],
                "p_low_differentiated": [0.4],
                "p_middle_differentiated": [0.4],
                "p_high_differentiated": [0.2],
            }
        )

        baseline_h = sum(
            _entropy_term(
                frame[f"p_{group}_baseline"]
            )[0]
            for group in ("low", "middle", "high")
        )
        differentiated_h = sum(
            _entropy_term(
                frame[f"p_{group}_differentiated"]
            )[0]
            for group in ("low", "middle", "high")
        )
        frame["delta_H_soc"] = (
            differentiated_h
            - baseline_h
        )

        result = _add_entropy_contributions(
            frame
        )

        self.assertAlmostEqual(
            result.iloc[0][
                "delta_H_soc_reconstructed"
            ],
            frame.iloc[0]["delta_H_soc"],
            places=12,
        )
        self.assertAlmostEqual(
            result.iloc[0][
                "delta_H_soc_reconstruction_error"
            ],
            0.0,
            places=12,
        )

    def test_bootstrap_resamples_complete_agents_with_multiplicity(self):
        observations = pd.DataFrame(
            {
                "agent_id": [
                    "a",
                    "a",
                    "b",
                ],
                "analysis_segment_id": [
                    "s1",
                    "s2",
                    "s1",
                ],
                "income_group": [
                    "low",
                    "low",
                    "high",
                ],
            }
        )
        draw_counts = pd.Series(
            {
                "a": 2,
                "b": 1,
            }
        )

        result = _bootstrap_scenario(
            observations,
            draw_counts=draw_counts,
        )

        self.assertEqual(
            result.loc["s1", "n_agents"],
            3,
        )
        self.assertAlmostEqual(
            result.loc["s1", "p_low"],
            2 / 3,
        )
        self.assertAlmostEqual(
            result.loc["s1", "p_high"],
            1 / 3,
        )
        self.assertEqual(
            result.loc["s2", "n_agents"],
            2,
        )
        self.assertAlmostEqual(
            result.loc["s2", "p_low"],
            1.0,
        )


if __name__ == "__main__":
    unittest.main()
