import math
import unittest

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString

from src.analysis.edge_statistics import (
    attach_statistics_to_segments,
    build_segment_statistics,
)


class EdgeStatisticsTests(unittest.TestCase):
    def test_count_unique_agents_for_social_composition(self):
        # Repete uma passagem do mesmo agente para testar a deduplicação social
        edge_usage = pd.DataFrame(
            [
                {
                    "scenario": "baseline",
                    "analysis_segment_id": "S_1",
                    "agent_id": 1,
                    "income_group": "low",
                    "mode": "walk",
                    "purpose": "work",
                    "modal_edge_id": "walk:1:2:0",
                },
                {
                    "scenario": "baseline",
                    "analysis_segment_id": "S_1",
                    "agent_id": 1,
                    "income_group": "low",
                    "mode": "walk",
                    "purpose": "work",
                    "modal_edge_id": "walk:2:3:0",
                },
                {
                    "scenario": "baseline",
                    "analysis_segment_id": "S_1",
                    "agent_id": 2,
                    "income_group": "high",
                    "mode": "car",
                    "purpose": "work",
                    "modal_edge_id": "car:1:3:0",
                },
            ]
        )

        result = build_segment_statistics(
            edge_usage,
            min_agents_for_interpretation=2,
        )

        row = result.iloc[
            0
        ]

        self.assertEqual(
            row["n_passages"],
            3,
        )
        self.assertEqual(
            row["n_agents"],
            2,
        )
        self.assertEqual(
            row["n_low"],
            1,
        )
        self.assertEqual(
            row["n_middle"],
            0,
        )
        self.assertEqual(
            row["n_high"],
            1,
        )
        self.assertAlmostEqual(
            row["p_low"],
            0.5,
        )
        self.assertAlmostEqual(
            row["p_high"],
            0.5,
        )
        self.assertAlmostEqual(
            row["H_soc"],
            math.log(2) / math.log(3),
        )
        self.assertTrue(
            row["sufficient_flow"]
        )

    def test_single_income_group_returns_zero_entropy(self):
        # Verifica que homogeneidade observada produza H_soc igual a zero
        edge_usage = pd.DataFrame(
            [
                {
                    "scenario": "baseline",
                    "analysis_segment_id": "S_1",
                    "agent_id": 1,
                    "income_group": "middle",
                    "mode": "bike",
                    "purpose": "education",
                    "modal_edge_id": "bike:1:2:0",
                }
            ]
        )

        result = build_segment_statistics(
            edge_usage
        )

        row = result.iloc[
            0
        ]

        self.assertEqual(
            row["H_soc"],
            0.0,
        )
        self.assertFalse(
            row["sufficient_flow"]
        )

    def test_preserve_unused_segments_with_nan_entropy(self):
        # Preserva a rede completa e marca os trechos sem agentes como não usados
        segments = gpd.GeoDataFrame(
            [
                {
                    "analysis_segment_id": "S_1",
                    "geometry": LineString(
                        [(0, 0), (1, 0)]
                    ),
                },
                {
                    "analysis_segment_id": "S_2",
                    "geometry": LineString(
                        [(1, 0), (2, 0)]
                    ),
                },
            ],
            geometry="geometry",
            crs="EPSG:31982",
        )

        edge_usage = pd.DataFrame(
            [
                {
                    "scenario": "baseline",
                    "analysis_segment_id": "S_1",
                    "agent_id": 1,
                    "income_group": "low",
                    "mode": "walk",
                    "purpose": "shopping",
                    "modal_edge_id": "walk:1:2:0",
                }
            ]
        )

        statistics = build_segment_statistics(
            edge_usage
        )

        result = attach_statistics_to_segments(
            segments,
            statistics,
            scenario_name="baseline",
        )

        unused = result.loc[
            result["analysis_segment_id"]
            == "S_2"
        ].iloc[0]

        self.assertEqual(
            unused["n_agents"],
            0,
        )
        self.assertFalse(
            unused["used"]
        )
        self.assertTrue(
            math.isnan(
                unused["H_soc"]
            )
        )


if __name__ == "__main__":
    unittest.main()
