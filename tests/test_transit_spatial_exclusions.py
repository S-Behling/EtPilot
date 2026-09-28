import unittest

import pandas as pd

from src.analysis.transit_spatial_exclusions import (
    apply_paired_transit_spatial_exclusions,
)


class TransitSpatialExclusionTests(unittest.TestCase):
    def _summary(self, scenario):
        # Cria resumos já preparados pelo filtro anterior de outliers
        return pd.DataFrame(
            {
                "scenario": [
                    scenario,
                    scenario,
                ],
                "agent_id": [
                    1,
                    2,
                ],
                "income_group": [
                    "low",
                    "middle",
                ],
                "purpose": [
                    "work",
                    "shopping",
                ],
                "mode": [
                    "transit",
                    "car",
                ],
                "origin_id": [
                    "O1",
                    "O2",
                ],
                "destination_id": [
                    "D1",
                    "D2",
                ],
                "analysis_included": [
                    True,
                    True,
                ],
                "analysis_exclusion_reason": [
                    "",
                    "",
                ],
            }
        )

    def _usage(self, scenario):
        # Cria uma conexão transit não mapeada para o agente 1
        return pd.DataFrame(
            {
                "scenario": [
                    scenario,
                    scenario,
                ],
                "agent_id": [
                    1,
                    2,
                ],
                "modal_edge_id": [
                    "transit:C1",
                    "car:1:2:0",
                ],
                "transit_route_id": [
                    "R1",
                    None,
                ],
                "transit_trip_id": [
                    "T1",
                    None,
                ],
            }
        )

    def test_excludes_affected_agent_in_both_scenarios(self):
        # Mantém a análise pareada quando a falha ocorre em apenas um cenário
        summaries = {
            "baseline": self._summary(
                "baseline"
            ),
            "differentiated": self._summary(
                "differentiated"
            ),
        }
        edge_usages = {
            "baseline": self._usage(
                "baseline"
            ),
            "differentiated": pd.DataFrame(
                {
                    "scenario": [
                        "differentiated",
                    ],
                    "agent_id": [
                        2,
                    ],
                    "modal_edge_id": [
                        "car:1:2:0",
                    ],
                    "transit_route_id": [
                        None,
                    ],
                    "transit_trip_id": [
                        None,
                    ],
                }
            ),
        }

        (
            updated_summaries,
            filtered_edge_usages,
            exclusions,
            summary,
        ) = apply_paired_transit_spatial_exclusions(
            summaries,
            edge_usages,
            missing_modal_edge_ids={
                "transit:C1",
            },
            paired_exclusion=True,
        )

        self.assertFalse(
            updated_summaries[
                "baseline"
            ].loc[
                updated_summaries[
                    "baseline"
                ][
                    "agent_id"
                ]
                == 1,
                "analysis_included",
            ].iloc[
                0
            ]
        )
        self.assertFalse(
            updated_summaries[
                "differentiated"
            ].loc[
                updated_summaries[
                    "differentiated"
                ][
                    "agent_id"
                ]
                == 1,
                "analysis_included",
            ].iloc[
                0
            ]
        )
        self.assertNotIn(
            1,
            set(
                filtered_edge_usages[
                    "baseline"
                ][
                    "agent_id"
                ]
            ),
        )
        self.assertEqual(
            len(
                exclusions
            ),
            2,
        )
        self.assertEqual(
            summary.iloc[
                0
            ][
                "directly_affected_agents"
            ],
            1,
        )

    def test_preserves_existing_outlier_exclusion_reason(self):
        # Acrescenta a falha espacial sem apagar uma exclusão anterior
        baseline = self._summary(
            "baseline"
        )
        baseline.loc[
            baseline[
                "agent_id"
            ]
            == 1,
            "analysis_included",
        ] = False
        baseline.loc[
            baseline[
                "agent_id"
            ]
            == 1,
            "analysis_exclusion_reason",
        ] = "direct_transit_route_outlier"

        summaries = {
            "baseline": baseline,
            "differentiated": self._summary(
                "differentiated"
            ),
        }
        edge_usages = {
            "baseline": self._usage(
                "baseline"
            ),
            "differentiated": self._usage(
                "differentiated"
            ),
        }

        updated, _, _, _ = (
            apply_paired_transit_spatial_exclusions(
                summaries,
                edge_usages,
                missing_modal_edge_ids={
                    "transit:C1",
                },
                paired_exclusion=True,
            )
        )

        reason = updated[
            "baseline"
        ].loc[
            updated[
                "baseline"
            ][
                "agent_id"
            ]
            == 1,
            "analysis_exclusion_reason",
        ].iloc[
            0
        ]

        self.assertIn(
            "direct_transit_route_outlier",
            reason,
        )
        self.assertIn(
            "direct_transit_spatial_mapping_failure",
            reason,
        )


if __name__ == "__main__":
    unittest.main()
