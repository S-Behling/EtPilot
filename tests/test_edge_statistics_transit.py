import unittest

import pandas as pd

from src.analysis.edge_statistics import (
    build_segment_statistics,
)


class EdgeStatisticsTransitTests(unittest.TestCase):
    def test_counts_transit_as_main_trip_mode(self):
        # Conta transit ao lado dos demais modos sem alterar a deduplicação social
        usage = pd.DataFrame(
            {
                "scenario": [
                    "baseline",
                    "baseline",
                ],
                "analysis_segment_id": [
                    "S1",
                    "S1",
                ],
                "agent_id": [
                    1,
                    2,
                ],
                "income_group": [
                    "low",
                    "middle",
                ],
                "mode": [
                    "transit",
                    "walk",
                ],
                "purpose": [
                    "work",
                    "work",
                ],
                "modal_edge_id": [
                    "transit:C1",
                    "walk:1:2:0",
                ],
            }
        )

        statistics = build_segment_statistics(
            usage,
            min_agents_for_interpretation=2,
        )

        row = statistics.iloc[
            0
        ]

        self.assertEqual(
            row[
                "n_mode_transit"
            ],
            1,
        )
        self.assertEqual(
            row[
                "n_mode_walk"
            ],
            1,
        )
        self.assertEqual(
            row[
                "n_agents"
            ],
            2,
        )
        self.assertTrue(
            row[
                "sufficient_flow"
            ]
        )
        self.assertGreater(
            row[
                "H_soc"
            ],
            0.0,
        )


if __name__ == "__main__":
    unittest.main()
