"""Identifica outliers técnicos de viagens transit sem apagar registros originais

Usa a distribuição combinada dos cenários para aplicar os mesmos limites
Exige simultaneamente distância roteada extrema e circuity extrema
Propaga a exclusão ao mesmo agent_id nos dois cenários quando configurado
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.routing.multimodal_router import SUCCESS_STATUSES


def _upper_tukey_fence(
    values: pd.Series,
    *,
    iqr_multiplier: float,
) -> dict:
    """Calcula quartis e cerca externa superior de Tukey"""

    numeric = pd.to_numeric(
        values,
        errors="coerce",
    ).dropna()

    if numeric.empty:
        return {
            "q1": np.nan,
            "q3": np.nan,
            "iqr": np.nan,
            "upper_fence": np.inf,
        }

    q1 = float(
        numeric.quantile(
            0.25
        )
    )
    q3 = float(
        numeric.quantile(
            0.75
        )
    )
    iqr = float(
        q3
        - q1
    )

    return {
        "q1": q1,
        "q3": q3,
        "iqr": iqr,
        "upper_fence": float(
            q3
            + iqr_multiplier
            * iqr
        ),
    }


def _with_route_ratio(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    """Adiciona a razão entre distância roteada e distância OD"""

    result = frame.copy()

    od = pd.to_numeric(
        result[
            "od_distance_m"
        ],
        errors="coerce",
    )
    routed = pd.to_numeric(
        result[
            "travel_distance_m"
        ],
        errors="coerce",
    )

    result[
        "route_to_od_ratio"
    ] = np.where(
        (
            od.notna()
            & routed.notna()
            & (
                od
                > 0
            )
        ),
        routed
        / od,
        np.nan,
    )

    return result


def apply_paired_transit_outlier_filter(
    summaries: dict[
        str,
        pd.DataFrame,
    ],
    *,
    config: dict,
) -> tuple[
    dict[
        str,
        pd.DataFrame,
    ],
    pd.DataFrame,
    pd.DataFrame,
]:
    """Marca outliers transit e retorna resumos e auditoria da exclusão"""

    enabled = bool(
        config.get(
            "enabled",
            False,
        )
    )
    iqr_multiplier = float(
        config.get(
            "iqr_multiplier",
            3.0,
        )
    )
    min_sample_size = int(
        config.get(
            "min_sample_size",
            20,
        )
    )
    paired_exclusion = bool(
        config.get(
            "paired_exclusion",
            True,
        )
    )

    if iqr_multiplier <= 0:
        raise ValueError(
            "iqr_multiplier precisa ser maior que zero"
        )

    prepared = {
        scenario_name: _with_route_ratio(
            summary
        )
        for scenario_name, summary
        in summaries.items()
    }

    combined = pd.concat(
        prepared.values(),
        ignore_index=True,
        sort=False,
    )

    eligible = combined.loc[
        (
            combined[
                "mode"
            ]
            == "transit"
        )
        & combined[
            "route_status"
        ].isin(
            SUCCESS_STATUSES
        )
        & combined[
            "travel_distance_m"
        ].notna()
        & combined[
            "route_to_od_ratio"
        ].notna()
    ].copy()

    enough_sample = (
        enabled
        and len(
            eligible
        )
        >= min_sample_size
    )

    if enough_sample:
        distance_stats = _upper_tukey_fence(
            eligible[
                "travel_distance_m"
            ],
            iqr_multiplier=iqr_multiplier,
        )
        circuity_stats = _upper_tukey_fence(
            eligible[
                "route_to_od_ratio"
            ],
            iqr_multiplier=iqr_multiplier,
        )
    else:
        distance_stats = {
            "q1": np.nan,
            "q3": np.nan,
            "iqr": np.nan,
            "upper_fence": np.inf,
        }
        circuity_stats = {
            "q1": np.nan,
            "q3": np.nan,
            "iqr": np.nan,
            "upper_fence": np.inf,
        }

    eligible[
        "outlier_route_distance"
    ] = (
        eligible[
            "travel_distance_m"
        ]
        > distance_stats[
            "upper_fence"
        ]
    )
    eligible[
        "outlier_route_to_od_ratio"
    ] = (
        (
            eligible[
                "route_to_od_ratio"
            ]
            > circuity_stats[
                "upper_fence"
            ]
        )
        & (
            eligible[
                "travel_distance_m"
            ]
            > distance_stats[
                "q3"
            ]
        )
    )
    eligible[
        "direct_outlier"
    ] = (
        enough_sample
        & (
            eligible[
                "outlier_route_distance"
            ]
            | eligible[
                "outlier_route_to_od_ratio"
            ]
        )
    )

    direct_rows = eligible.loc[
        eligible[
            "direct_outlier"
        ]
    ].copy()

    direct_agent_ids = set(
        direct_rows[
            "agent_id"
        ].tolist()
    )

    direct_pairs = {
        (
            str(
                row.scenario
            ),
            row.agent_id,
        )
        for row in direct_rows.itertuples(
            index=False
        )
    }

    trigger_scenarios = (
        direct_rows.groupby(
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
    )

    updated = {}
    exclusion_rows = []

    for scenario_name, frame in prepared.items():
        result = frame.copy()

        result[
            "direct_outlier"
        ] = [
            (
                scenario_name,
                agent_id,
            )
            in direct_pairs
            for agent_id in result[
                "agent_id"
            ]
        ]

        if paired_exclusion:
            result[
                "analysis_excluded_outlier"
            ] = result[
                "agent_id"
            ].isin(
                direct_agent_ids
            )
        else:
            result[
                "analysis_excluded_outlier"
            ] = result[
                "direct_outlier"
            ]

        result[
            "analysis_included"
        ] = ~result[
            "analysis_excluded_outlier"
        ]

        result[
            "analysis_exclusion_reason"
        ] = np.where(
            result[
                "direct_outlier"
            ],
            "direct_transit_route_outlier",
            np.where(
                result[
                    "analysis_excluded_outlier"
                ],
                "paired_with_outlier_in_other_scenario",
                "",
            ),
        )

        result[
            "outlier_distance_upper_fence_m"
        ] = distance_stats[
            "upper_fence"
        ]
        result[
            "outlier_circuity_upper_fence"
        ] = circuity_stats[
            "upper_fence"
        ]

        updated[
            scenario_name
        ] = result

        for row in result.loc[
            result[
                "analysis_excluded_outlier"
            ]
        ].itertuples(
            index=False
        ):
            exclusion_rows.append(
                {
                    "scenario": scenario_name,
                    "agent_id": row.agent_id,
                    "income_group": row.income_group,
                    "purpose": row.purpose,
                    "mode": row.mode,
                    "origin_id": row.origin_id,
                    "destination_id": row.destination_id,
                    "od_distance_m": row.od_distance_m,
                    "travel_distance_m": row.travel_distance_m,
                    "travel_time_s": row.travel_time_s,
                    "route_to_od_ratio": row.route_to_od_ratio,
                    "transit_in_vehicle_distance_m": getattr(
                        row,
                        "transit_in_vehicle_distance_m",
                        np.nan,
                    ),
                    "transit_in_vehicle_time_s": getattr(
                        row,
                        "transit_in_vehicle_time_s",
                        np.nan,
                    ),
                    "transit_n_transfers": getattr(
                        row,
                        "transit_n_transfers",
                        np.nan,
                    ),
                    "direct_outlier": bool(
                        row.direct_outlier
                    ),
                    "trigger_scenarios": trigger_scenarios.get(
                        row.agent_id,
                        "",
                    ),
                    "exclusion_reason": row.analysis_exclusion_reason,
                    "distance_upper_fence_m": distance_stats[
                        "upper_fence"
                    ],
                    "circuity_upper_fence": circuity_stats[
                        "upper_fence"
                    ],
                    "iqr_multiplier": iqr_multiplier,
                    "detection_method": config.get(
                        "method",
                        "pooled_joint_tukey_outer_fence",
                    ),
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
            "od_distance_m",
            "travel_distance_m",
            "travel_time_s",
            "route_to_od_ratio",
            "transit_in_vehicle_distance_m",
            "transit_in_vehicle_time_s",
            "transit_n_transfers",
            "direct_outlier",
            "trigger_scenarios",
            "exclusion_reason",
            "distance_upper_fence_m",
            "circuity_upper_fence",
            "iqr_multiplier",
            "detection_method",
            "removal_scope",
        ],
    )

    filter_summary = pd.DataFrame(
        [
            {
                "enabled": enabled,
                "method": config.get(
                    "method",
                    "pooled_joint_tukey_outer_fence",
                ),
                "rule": config.get(
                    "rule",
                    "distance_outer_or_circuity_with_long_route",
                ),
                "paired_exclusion": paired_exclusion,
                "iqr_multiplier": iqr_multiplier,
                "eligible_transit_routes": len(
                    eligible
                ),
                "sample_size_sufficient": enough_sample,
                "route_distance_q1_m": distance_stats[
                    "q1"
                ],
                "route_distance_q3_m": distance_stats[
                    "q3"
                ],
                "route_distance_iqr_m": distance_stats[
                    "iqr"
                ],
                "route_distance_upper_fence_m": distance_stats[
                    "upper_fence"
                ],
                "circuity_q1": circuity_stats[
                    "q1"
                ],
                "circuity_q3": circuity_stats[
                    "q3"
                ],
                "circuity_iqr": circuity_stats[
                    "iqr"
                ],
                "circuity_upper_fence": circuity_stats[
                    "upper_fence"
                ],
                "direct_outlier_routes": len(
                    direct_rows
                ),
                "unique_excluded_agents": len(
                    direct_agent_ids
                ),
                "excluded_scenario_rows": len(
                    exclusions
                ),
                "status": config.get(
                    "status",
                    "provisional_pilot",
                ),
            }
        ]
    )

    return (
        updated,
        exclusions,
        filter_summary,
    )
