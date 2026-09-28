import math
import unittest

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString

from src.analysis.scenario_comparison import (
    attach_comparison_to_segments,
    build_scenario_comparison,
    comparison_summary,
)


class ScenarioComparisonTests(unittest.TestCase):
    def _statistics(self):
        # Cria segmentos compartilhados e exclusivos para testar a comparação
        return pd.DataFrame(
            [
                {
                    "scenario": "baseline",
                    "analysis_segment_id": "S_1",
                    "n_passages": 10,
                    "n_agents": 5,
                    "n_low": 2,
                    "n_middle": 2,
                    "n_high": 1,
                    "p_low": 0.4,
                    "p_middle": 0.4,
                    "p_high": 0.2,
                    "H_soc": 0.90,
                },
                {
                    "scenario": "differentiated",
                    "analysis_segment_id": "S_1",
                    "n_passages": 12,
                    "n_agents": 6,
                    "n_low": 1,
                    "n_middle": 3,
                    "n_high": 2,
                    "p_low": 1 / 6,
                    "p_middle": 0.5,
                    "p_high": 1 / 3,
                    "H_soc": 0.95,
                },
                {
                    "scenario": "baseline",
                    "analysis_segment_id": "S_2",
                    "n_passages": 2,
                    "n_agents": 1,
                    "n_low": 1,
                    "n_middle": 0,
                    "n_high": 0,
                    "p_low": 1.0,
                    "p_middle": 0.0,
                    "p_high": 0.0,
                    "H_soc": 0.0,
                },
                {
                    "scenario": "differentiated",
                    "analysis_segment_id": "S_3",
                    "n_passages": 4,
                    "n_agents": 2,
                    "n_low": 0,
                    "n_middle": 2,
                    "n_high": 0,
                    "p_low": 0.0,
                    "p_middle": 1.0,
                    "p_high": 0.0,
                    "H_soc": 0.0,
                },
            ]
        )

    def test_pair_same_segment_and_compute_delta(self):
        comparison = build_scenario_comparison(
            self._statistics(),
            min_agents_for_interpretation=5,
            flow_thresholds=(2, 5),
        )

        shared = comparison.loc[
            comparison["analysis_segment_id"]
            == "S_1"
        ].iloc[0]

        self.assertEqual(
            shared["usage_status"],
            "used_both",
        )
        self.assertTrue(
            shared["used_both"]
        )
        self.assertAlmostEqual(
            shared["delta_H_soc"],
            0.05,
        )
        self.assertEqual(
            shared["delta_n_agents"],
            1,
        )
        self.assertTrue(
            shared["sufficient_flow_both"]
        )
        self.assertTrue(
            shared["flow_ge_5_both"]
        )

    def test_preserve_scenario_only_segments_without_false_delta(self):
        comparison = build_scenario_comparison(
            self._statistics(),
            flow_thresholds=(2, 5),
        )

        baseline_only = comparison.loc[
            comparison["analysis_segment_id"]
            == "S_2"
        ].iloc[0]

        differentiated_only = comparison.loc[
            comparison["analysis_segment_id"]
            == "S_3"
        ].iloc[0]

        self.assertEqual(
            baseline_only["usage_status"],
            "baseline_only",
        )
        self.assertEqual(
            differentiated_only["usage_status"],
            "differentiated_only",
        )
        self.assertTrue(
            math.isnan(
                baseline_only["delta_H_soc"]
            )
        )
        self.assertTrue(
            math.isnan(
                differentiated_only["delta_H_soc"]
            )
        )

    def test_attach_comparison_preserves_unused_network_segments(self):
        segments = gpd.GeoDataFrame(
            [
                {
                    "analysis_segment_id": "S_1",
                    "geometry": LineString(
                        [(0, 0), (1, 0)]
                    ),
                },
                {
                    "analysis_segment_id": "S_4",
                    "geometry": LineString(
                        [(1, 0), (2, 0)]
                    ),
                },
            ],
            geometry="geometry",
            crs="EPSG:31982",
        )

        comparison = build_scenario_comparison(
            self._statistics(),
            flow_thresholds=(2, 5),
        )

        result = attach_comparison_to_segments(
            segments,
            comparison,
        )

        unused = result.loc[
            result["analysis_segment_id"]
            == "S_4"
        ].iloc[0]

        self.assertEqual(
            unused["usage_status"],
            "unused_both",
        )
        self.assertFalse(
            unused["used_both"]
        )
        self.assertEqual(
            unused["n_agents_baseline"],
            0,
        )
        self.assertEqual(
            unused["n_agents_differentiated"],
            0,
        )
        self.assertTrue(
            math.isnan(
                unused["delta_H_soc"]
            )
        )

    def test_summary_uses_only_paired_segments_for_delta(self):
        comparison = build_scenario_comparison(
            self._statistics(),
            min_agents_for_interpretation=5,
            flow_thresholds=(2, 5),
        )

        summary = comparison_summary(
            comparison,
            min_agents_for_interpretation=5,
            flow_thresholds=(2, 5),
        )

        self.assertEqual(
            summary["segments_union"],
            3,
        )
        self.assertEqual(
            summary["used_both"],
            1,
        )
        self.assertEqual(
            summary["baseline_only"],
            1,
        )
        self.assertEqual(
            summary["differentiated_only"],
            1,
        )
        self.assertEqual(
            summary["sufficient_flow_both"],
            1,
        )
        self.assertAlmostEqual(
            summary["paired_delta_H_soc_mean"],
            0.05,
        )


if __name__ == "__main__":
    unittest.main()
