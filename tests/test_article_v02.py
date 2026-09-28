import unittest

import numpy as np
import pandas as pd

from src.analysis.article_v02 import (
    _linewidth,
    _observed_modal_shares,
)


class ArticleV02Tests(unittest.TestCase):
    def test_linewidth_is_bounded_and_monotonic(self):
        values = np.array(
            [
                0.0,
                1.0,
                4.0,
            ]
        )

        widths = _linewidth(
            values,
            reference_max=4.0,
            minimum=0.5,
            maximum=4.5,
        )

        self.assertGreaterEqual(
            widths[0],
            0.5,
        )
        self.assertLessEqual(
            widths[-1],
            4.5,
        )
        self.assertTrue(
            np.all(
                np.diff(widths)
                >= 0
            )
        )

    def test_observed_modal_shares_sum_to_one_by_seed_class_scenario(self):
        behavior = pd.DataFrame(
            {
                "seed": [
                    42,
                    42,
                    42,
                    42,
                ],
                "income_group": [
                    "low",
                    "low",
                    "middle",
                    "middle",
                ],
                "mode_baseline": [
                    "walk",
                    "car",
                    "walk",
                    "car",
                ],
                "mode_differentiated": [
                    "transit",
                    "transit",
                    "car",
                    "car",
                ],
                "analysis_included_both": [
                    True,
                    True,
                    True,
                    True,
                ],
            }
        )

        result = _observed_modal_shares(
            behavior
        )

        totals = (
            result.groupby(
                [
                    "seed",
                    "income_group",
                    "scenario",
                ]
            )[
                "share"
            ]
            .sum()
        )

        self.assertTrue(
            np.allclose(
                totals.to_numpy(),
                1.0,
            )
        )

    def test_differentiated_modal_share_can_diverge_by_class(self):
        behavior = pd.DataFrame(
            {
                "seed": [
                    42,
                    42,
                    42,
                    42,
                ],
                "income_group": [
                    "low",
                    "low",
                    "high",
                    "high",
                ],
                "mode_baseline": [
                    "car",
                    "transit",
                    "car",
                    "transit",
                ],
                "mode_differentiated": [
                    "transit",
                    "transit",
                    "car",
                    "car",
                ],
                "analysis_included_both": [
                    True,
                    True,
                    True,
                    True,
                ],
            }
        )

        result = _observed_modal_shares(
            behavior
        )

        differentiated = result.loc[
            result[
                "scenario"
            ]
            == "differentiated"
        ]

        low_transit = differentiated.loc[
            (
                differentiated[
                    "income_group"
                ]
                == "low"
            )
            & (
                differentiated[
                    "mode"
                ]
                == "transit"
            ),
            "share",
        ].iloc[0]

        high_car = differentiated.loc[
            (
                differentiated[
                    "income_group"
                ]
                == "high"
            )
            & (
                differentiated[
                    "mode"
                ]
                == "car"
            ),
            "share",
        ].iloc[0]

        self.assertAlmostEqual(
            low_transit,
            1.0,
        )
        self.assertAlmostEqual(
            high_car,
            1.0,
        )


if __name__ == "__main__":
    unittest.main()
