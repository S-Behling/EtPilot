import unittest

import pandas as pd

from src.analysis.trip_outliers import (
    apply_paired_transit_outlier_filter,
)


class TripOutlierTests(unittest.TestCase):
    def _summary(
        self,
        scenario,
        *,
        extreme_agent=None,
    ):
        # Cria viagens transit regulares e uma trajetória extrema opcional
        rows = []

        for agent_id in range(
            1,
            7,
        ):
            od_distance = 1000.0
            route_distance = 1200.0

            if agent_id == extreme_agent:
                route_distance = 30000.0

            rows.append(
                {
                    "scenario": scenario,
                    "agent_id": agent_id,
                    "income_group": "low",
                    "purpose": "work",
                    "mode": "transit",
                    "origin_id": f"O{agent_id}",
                    "destination_id": f"D{agent_id}",
                    "od_distance_m": od_distance,
                    "travel_distance_m": route_distance,
                    "travel_time_s": 1800.0,
                    "route_status": "ok",
                    "transit_in_vehicle_distance_m": route_distance - 200.0,
                    "transit_in_vehicle_time_s": 1200.0,
                    "transit_n_transfers": 1,
                }
            )

        return pd.DataFrame(
            rows
        )

    def test_excludes_joint_transit_outlier_in_both_scenarios(self):
        # Propaga a exclusão ao mesmo agente para manter a população analítica pareada
        summaries = {
            "baseline": self._summary(
                "baseline",
                extreme_agent=1,
            ),
            "differentiated": self._summary(
                "differentiated",
            ),
        }

        (
            updated,
            exclusions,
            filter_summary,
        ) = apply_paired_transit_outlier_filter(
            summaries,
            config={
                "enabled": True,
                "method": "pooled_joint_tukey_outer_fence",
                "iqr_multiplier": 3.0,
                "min_sample_size": 4,
                "paired_exclusion": True,
                "rule": "route_distance_and_circuity",
            },
        )

        baseline_agent = updated[
            "baseline"
        ].loc[
            updated[
                "baseline"
            ][
                "agent_id"
            ]
            == 1
        ].iloc[
            0
        ]
        differentiated_agent = updated[
            "differentiated"
        ].loc[
            updated[
                "differentiated"
            ][
                "agent_id"
            ]
            == 1
        ].iloc[
            0
        ]

        self.assertTrue(
            baseline_agent[
                "direct_outlier"
            ]
        )
        self.assertFalse(
            baseline_agent[
                "analysis_included"
            ]
        )
        self.assertFalse(
            differentiated_agent[
                "direct_outlier"
            ]
        )
        self.assertFalse(
            differentiated_agent[
                "analysis_included"
            ]
        )
        self.assertEqual(
            len(
                exclusions
            ),
            2,
        )
        self.assertEqual(
            filter_summary.iloc[
                0
            ][
                "unique_excluded_agents"
            ],
            1,
        )

    def test_does_not_exclude_high_ratio_without_extreme_distance(self):
        # Preserva uma viagem curta com razão elevada quando a distância total não é extrema
        baseline = self._summary(
            "baseline"
        )
        baseline.loc[
            baseline[
                "agent_id"
            ]
            == 1,
            [
                "od_distance_m",
                "travel_distance_m",
            ],
        ] = [
            100.0,
            1200.0,
        ]

        summaries = {
            "baseline": baseline,
            "differentiated": self._summary(
                "differentiated"
            ),
        }

        updated, exclusions, _ = (
            apply_paired_transit_outlier_filter(
                summaries,
                config={
                    "enabled": True,
                    "iqr_multiplier": 3.0,
                    "min_sample_size": 4,
                    "paired_exclusion": True,
                },
            )
        )

        agent = updated[
            "baseline"
        ].loc[
            updated[
                "baseline"
            ][
                "agent_id"
            ]
            == 1
        ].iloc[
            0
        ]

        self.assertFalse(
            agent[
                "direct_outlier"
            ]
        )
        self.assertTrue(
            agent[
                "analysis_included"
            ]
        )
        self.assertTrue(
            exclusions.empty
        )


if __name__ == "__main__":
    unittest.main()
