"""Exclui da análise agentes com trechos transit impossíveis de espacializar

Preserva os registros originais dos agentes
Registra a falha espacial no cenário em que ela ocorre
Propaga a exclusão ao mesmo agent_id no outro cenário quando configurado
"""

from __future__ import annotations

import pandas as pd


def apply_paired_transit_spatial_exclusions(
    summaries: dict[
        str,
        pd.DataFrame,
    ],
    edge_usages: dict[
        str,
        pd.DataFrame,
    ],
    *,
    missing_modal_edge_ids: set[str],
    paired_exclusion: bool,
) -> tuple[
    dict[
        str,
        pd.DataFrame,
    ],
    dict[
        str,
        pd.DataFrame,
    ],
    pd.DataFrame,
    pd.DataFrame,
]:
    """Aplica exclusões espaciais pareadas e devolve tabelas auditáveis"""

    direct_pairs: set[
        tuple[
            str,
            object,
        ]
    ] = set()
    direct_details: list[
        dict,
    ] = []

    for scenario_name, usage in edge_usages.items():
        affected = usage.loc[
            usage[
                "modal_edge_id"
            ]
            .astype(
                str
            )
            .isin(
                missing_modal_edge_ids
            )
        ].copy()

        if affected.empty:
            continue

        grouped = (
            affected.groupby(
                "agent_id",
                as_index=False,
            )
            .agg(
                n_unmapped_connections=(
                    "modal_edge_id",
                    "nunique",
                ),
                transit_route_ids=(
                    "transit_route_id",
                    lambda values: "|".join(
                        sorted(
                            {
                                str(
                                    value
                                )
                                for value in values.dropna()
                            }
                        )
                    ),
                ),
                transit_trip_ids=(
                    "transit_trip_id",
                    lambda values: "|".join(
                        sorted(
                            {
                                str(
                                    value
                                )
                                for value in values.dropna()
                            }
                        )
                    ),
                ),
            )
        )

        for row in grouped.itertuples(
            index=False
        ):
            direct_pairs.add(
                (
                    scenario_name,
                    row.agent_id,
                )
            )
            direct_details.append(
                {
                    "scenario": scenario_name,
                    "agent_id": row.agent_id,
                    "n_unmapped_connections": int(
                        row.n_unmapped_connections
                    ),
                    "transit_route_ids": row.transit_route_ids,
                    "transit_trip_ids": row.transit_trip_ids,
                }
            )

    direct_agent_ids = {
        agent_id
        for _, agent_id
        in direct_pairs
    }

    trigger_scenarios = (
        pd.DataFrame(
            direct_details
        )
        .groupby(
            "agent_id"
        )[
            "scenario"
        ]
        .agg(
            lambda values: "|".join(
                sorted(
                    {
                        str(
                            value
                        )
                        for value in values
                    }
                )
            )
        )
        .to_dict()
        if direct_details
        else {}
    )

    detail_lookup = {
        (
            str(
                row[
                    "scenario"
                ]
            ),
            row[
                "agent_id"
            ],
        ): row
        for row in direct_details
    }

    updated_summaries: dict[
        str,
        pd.DataFrame,
    ] = {}
    filtered_edge_usages: dict[
        str,
        pd.DataFrame,
    ] = {}
    exclusion_rows: list[
        dict,
    ] = []

    for scenario_name, summary in summaries.items():
        frame = summary.copy()

        frame[
            "direct_spatial_mapping_failure"
        ] = [
            (
                scenario_name,
                agent_id,
            )
            in direct_pairs
            for agent_id in frame[
                "agent_id"
            ]
        ]

        if paired_exclusion:
            frame[
                "analysis_excluded_spatial_mapping"
            ] = frame[
                "agent_id"
            ].isin(
                direct_agent_ids
            )
        else:
            frame[
                "analysis_excluded_spatial_mapping"
            ] = frame[
                "direct_spatial_mapping_failure"
            ]

        existing_included = frame.get(
            "analysis_included",
            pd.Series(
                True,
                index=frame.index,
            ),
        ).astype(
            bool
        )

        frame[
            "analysis_included"
        ] = (
            existing_included
            & ~frame[
                "analysis_excluded_spatial_mapping"
            ]
        )

        existing_reason = frame.get(
            "analysis_exclusion_reason",
            pd.Series(
                "",
                index=frame.index,
            ),
        ).fillna(
            ""
        ).astype(
            str
        )

        spatial_reason = pd.Series(
            "",
            index=frame.index,
            dtype="string",
        )
        spatial_reason.loc[
            frame[
                "direct_spatial_mapping_failure"
            ]
        ] = "direct_transit_spatial_mapping_failure"
        spatial_reason.loc[
            frame[
                "analysis_excluded_spatial_mapping"
            ]
            & ~frame[
                "direct_spatial_mapping_failure"
            ]
        ] = "paired_with_spatial_mapping_failure_in_other_scenario"

        frame[
            "analysis_exclusion_reason"
        ] = [
            "|".join(
                reason
                for reason in [
                    existing,
                    spatial,
                ]
                if reason
            )
            for existing, spatial
            in zip(
                existing_reason,
                spatial_reason,
                strict=True,
            )
        ]

        updated_summaries[
            scenario_name
        ] = frame

        included_agent_ids = set(
            frame.loc[
                frame[
                    "analysis_included"
                ],
                "agent_id",
            ]
        )

        filtered_edge_usages[
            scenario_name
        ] = (
            edge_usages[
                scenario_name
            ]
            .loc[
                edge_usages[
                    scenario_name
                ][
                    "agent_id"
                ]
                .isin(
                    included_agent_ids
                )
            ]
            .copy()
            .reset_index(
                drop=True
            )
        )

        excluded = frame.loc[
            frame[
                "analysis_excluded_spatial_mapping"
            ]
        ]

        for row in excluded.itertuples(
            index=False
        ):
            direct_detail = detail_lookup.get(
                (
                    scenario_name,
                    row.agent_id,
                ),
                {},
            )

            exclusion_rows.append(
                {
                    "scenario": scenario_name,
                    "agent_id": row.agent_id,
                    "income_group": row.income_group,
                    "purpose": row.purpose,
                    "mode": row.mode,
                    "origin_id": row.origin_id,
                    "destination_id": row.destination_id,
                    "direct_spatial_mapping_failure": bool(
                        row.direct_spatial_mapping_failure
                    ),
                    "n_unmapped_connections": direct_detail.get(
                        "n_unmapped_connections",
                        0,
                    ),
                    "transit_route_ids": direct_detail.get(
                        "transit_route_ids",
                        "",
                    ),
                    "transit_trip_ids": direct_detail.get(
                        "transit_trip_ids",
                        "",
                    ),
                    "trigger_scenarios": trigger_scenarios.get(
                        row.agent_id,
                        "",
                    ),
                    "exclusion_reason": row.analysis_exclusion_reason,
                    "removal_scope": "trajectory_analysis_only",
                }
            )

    exclusions = pd.DataFrame(
        exclusion_rows,
        columns=[
            "scenario",
            "agent_id",
            "income_group",
            "purpose",
            "mode",
            "origin_id",
            "destination_id",
            "direct_spatial_mapping_failure",
            "n_unmapped_connections",
            "transit_route_ids",
            "transit_trip_ids",
            "trigger_scenarios",
            "exclusion_reason",
            "removal_scope",
        ],
    )

    summary = pd.DataFrame(
        [
            {
                "missing_transit_connections_before_exclusion": len(
                    missing_modal_edge_ids
                ),
                "directly_affected_agents": len(
                    direct_agent_ids
                ),
                "paired_exclusion": paired_exclusion,
                "excluded_scenario_rows": len(
                    exclusions
                ),
            }
        ]
    )

    return (
        updated_summaries,
        filtered_edge_usages,
        exclusions,
        summary,
    )
