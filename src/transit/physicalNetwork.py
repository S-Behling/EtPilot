"""Constrói e integra a camada física completa do transporte coletivo

Agrupa conexões GTFS roteáveis em trechos físicos estáveis
Extrai a geometria stop a stop de cada trecho físico
Mantém somente trechos com geometria válida no roteador espacial
Integra transit à camada comum sem depender do número de agentes ou cenário
"""

from __future__ import annotations

from collections.abc import Mapping

import geopandas as gpd
import numpy as np
import pandas as pd

from src.domain.enums import TravelMode
from src.trajectory.transit_usage import (
    build_used_transit_connection_geometries,
    map_transit_connections_hierarchically,
)


def _position_signature(
    values: pd.Series,
) -> pd.Series:
    """Normaliza posições métricas para uma assinatura textual estável"""

    numeric = pd.to_numeric(
        values,
        errors="coerce",
    ).round(
        3
    )

    return (
        numeric
        .astype(
            "Float64"
        )
        .astype(
            "string"
        )
        .fillna(
            "NA"
        )
    )


def _build_physical_key(
    connections: pd.DataFrame,
) -> pd.Series:
    """Cria uma chave física independente do horário e da viagem"""

    required = {
        "shape_id",
        "from_stop_id",
        "to_stop_id",
        "from_shape_position_m",
        "to_shape_position_m",
    }

    missing = (
        required
        - set(
            connections.columns
        )
    )

    if missing:
        raise ValueError(
            "Conexões GTFS sem colunas necessárias para a rede física: "
            f"{sorted(missing)}"
        )

    return (
        connections[
            "shape_id"
        ].astype(
            "string"
        )
        .fillna(
            "NA"
        )
        + "|"
        + connections[
            "from_stop_id"
        ].astype(
            "string"
        )
        .fillna(
            "NA"
        )
        + "|"
        + connections[
            "to_stop_id"
        ].astype(
            "string"
        )
        .fillna(
            "NA"
        )
        + "|"
        + _position_signature(
            connections[
                "from_shape_position_m"
            ]
        )
        + "|"
        + _position_signature(
            connections[
                "to_shape_position_m"
            ]
        )
    )


def build_transit_physical_network(
    connections: pd.DataFrame,
    *,
    shapes: gpd.GeoDataFrame,
    stops: gpd.GeoDataFrame,
) -> tuple[
    pd.DataFrame,
    gpd.GeoDataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:
    """Constrói trechos físicos estáveis a partir de todas as conexões roteáveis"""

    if connections.empty:
        raise ValueError(
            "connections não pode estar vazio"
        )

    frame = connections.copy()

    frame[
        "connection_id"
    ] = frame[
        "connection_id"
    ].astype(
        "string"
    )
    frame[
        "transit_physical_key"
    ] = _build_physical_key(
        frame
    )

    physical_keys = (
        frame[
            "transit_physical_key"
        ]
        .drop_duplicates()
        .sort_values(
            kind="stable"
        )
        .reset_index(
            drop=True
        )
    )

    physical_ids = pd.DataFrame(
        {
            "transit_physical_key": physical_keys,
            "transit_physical_edge_id": [
                f"T_{index:07d}"
                for index in range(
                    1,
                    len(
                        physical_keys
                    )
                    + 1,
                )
            ],
        }
    )

    frame = frame.merge(
        physical_ids,
        on="transit_physical_key",
        how="left",
        validate="many_to_one",
    )

    representatives = (
        frame.sort_values(
            [
                "transit_physical_key",
                "connection_id",
            ],
            kind="stable",
        )
        .drop_duplicates(
            subset=[
                "transit_physical_key",
            ]
        )
        .copy()
    )

    selector = pd.DataFrame(
        {
            "mapping_mode": TravelMode.TRANSIT.value,
            "transit_connection_id": (
                representatives[
                    "connection_id"
                ].astype(
                    "string"
                )
            ),
        }
    )

    representative_connections = (
        representatives.copy()
    )

    (
        representative_geometries,
        geometry_diagnostics,
    ) = build_used_transit_connection_geometries(
        selector,
        connections=representative_connections,
        shapes=shapes,
        stops=stops,
    )

    representative_lookup = representatives[
        [
            "connection_id",
            "transit_physical_key",
            "transit_physical_edge_id",
            "shape_id",
            "from_stop_id",
            "to_stop_id",
            "from_shape_position_m",
            "to_shape_position_m",
        ]
    ].copy()

    geometry_diagnostics = (
        geometry_diagnostics.merge(
            representative_lookup,
            on=[
                "connection_id",
                "shape_id",
            ],
            how="left",
            validate="one_to_one",
        )
    )

    valid_diagnostics = geometry_diagnostics.loc[
        geometry_diagnostics[
            "geometry_status"
        ]
        .astype(
            str
        )
        .str.startswith(
            "ok"
        )
    ].copy()

    geometry_lookup = (
        representative_geometries[
            [
                "connection_id",
                "geometry",
            ]
        ]
        .copy()
    )

    valid_physical = (
        valid_diagnostics.merge(
            geometry_lookup,
            on="connection_id",
            how="inner",
            validate="one_to_one",
        )
    )

    group_summary = (
        frame.groupby(
            "transit_physical_edge_id",
            as_index=False,
        )
        .agg(
            n_connections=(
                "connection_id",
                "size",
            ),
            n_trips=(
                "trip_id",
                "nunique",
            ),
            n_routes=(
                "route_id",
                "nunique",
            ),
        )
    )

    physical_edges = valid_physical.merge(
        group_summary,
        on="transit_physical_edge_id",
        how="left",
        validate="one_to_one",
    )
    physical_edges = gpd.GeoDataFrame(
        physical_edges,
        geometry="geometry",
        crs=shapes.crs,
    )

    physical_edges[
        "modal_edge_id"
    ] = (
        "transit:"
        + physical_edges[
            "transit_physical_edge_id"
        ].astype(
            "string"
        )
    )
    physical_edges[
        "mode"
    ] = TravelMode.TRANSIT.value
    physical_edges[
        "length_m"
    ] = physical_edges.geometry.length.astype(
        float
    )

    physical_edges = gpd.GeoDataFrame(
        physical_edges,
        geometry="geometry",
        crs=shapes.crs,
    )

    physical_edges = (
        physical_edges[
            [
                "transit_physical_edge_id",
                "modal_edge_id",
                "transit_physical_key",
                "shape_id",
                "from_stop_id",
                "to_stop_id",
                "from_shape_position_m",
                "to_shape_position_m",
                "geometry_status",
                "position_method",
                "from_snap_distance_m",
                "to_snap_distance_m",
                "length_m",
                "n_connections",
                "n_trips",
                "n_routes",
                "mode",
                "geometry",
            ]
        ]
        .sort_values(
            "transit_physical_edge_id"
        )
        .reset_index(
            drop=True
        )
    )

    valid_physical_ids = set(
        physical_edges[
            "transit_physical_edge_id"
        ].astype(
            str
        )
    )

    frame[
        "spatial_geometry_valid"
    ] = frame[
        "transit_physical_edge_id"
    ].astype(
        str
    ).isin(
        valid_physical_ids
    )

    spatial_routable_connections = (
        frame.loc[
            frame[
                "spatial_geometry_valid"
            ]
        ]
        .copy()
        .reset_index(
            drop=True
        )
    )

    connection_map = frame[
        [
            "connection_id",
            "transit_physical_edge_id",
            "transit_physical_key",
            "spatial_geometry_valid",
        ]
    ].copy()

    geometry_diagnostics[
        "transit_physical_edge_id"
    ] = geometry_diagnostics[
        "transit_physical_edge_id"
    ].astype(
        "string"
    )

    return (
        spatial_routable_connections,
        physical_edges,
        connection_map,
        geometry_diagnostics,
    )


def _next_analysis_segment_index(
    analysis_segments: gpd.GeoDataFrame,
) -> int:
    """Calcula o próximo índice sequencial da camada física comum"""

    if analysis_segments.empty:
        return 1

    values = (
        analysis_segments[
            "analysis_segment_id"
        ]
        .astype(
            str
        )
        .str.replace(
            "S_",
            "",
            regex=False,
        )
    )

    numeric = pd.to_numeric(
        values,
        errors="coerce",
    )

    if numeric.notna().any():
        return int(
            numeric.max()
        ) + 1

    return (
        len(
            analysis_segments
        )
        + 1
    )


def integrate_transit_physical_network(
    analysis_segments: gpd.GeoDataFrame,
    segment_mapping: pd.DataFrame,
    transit_physical_edges: gpd.GeoDataFrame,
    *,
    primary_config: Mapping,
    fallback_config: Mapping,
) -> tuple[
    gpd.GeoDataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:
    """Integra toda a rede física GTFS e cria segmentos exclusivos quando necessário"""

    if transit_physical_edges.empty:
        return (
            analysis_segments,
            segment_mapping,
            pd.DataFrame(),
            pd.DataFrame(),
        )

    car_supported_ids = set(
        segment_mapping.loc[
            segment_mapping[
                "mode"
            ]
            == TravelMode.CAR.value,
            "analysis_segment_id",
        ].astype(
            str
        )
    )

    primary_segments = (
        analysis_segments.loc[
            analysis_segments[
                "analysis_segment_id"
            ]
            .astype(
                str
            )
            .isin(
                car_supported_ids
            )
        ]
        .copy()
        .reset_index(
            drop=True
        )
    )

    if primary_segments.empty:
        raise RuntimeError(
            "A camada física não possui segmentos com suporte da rede car"
        )

    matcher_input = transit_physical_edges[
        [
            "modal_edge_id",
            "transit_physical_edge_id",
            "shape_id",
            "geometry",
        ]
    ].copy()

    matcher_input[
        "connection_id"
    ] = matcher_input[
        "transit_physical_edge_id"
    ].astype(
        "string"
    )

    (
        transit_mapping,
        diagnostics,
    ) = map_transit_connections_hierarchically(
        matcher_input,
        primary_segments=primary_segments,
        fallback_segments=analysis_segments,
        primary_config=primary_config,
        fallback_config=fallback_config,
    )

    mapped_ids = set(
        transit_mapping[
            "modal_edge_id"
        ].astype(
            str
        )
    )

    unmatched = (
        transit_physical_edges.loc[
            ~transit_physical_edges[
                "modal_edge_id"
            ]
            .astype(
                str
            )
            .isin(
                mapped_ids
            )
        ]
        .sort_values(
            "modal_edge_id"
        )
        .copy()
    )

    next_index = _next_analysis_segment_index(
        analysis_segments
    )

    exclusive_segment_rows = []
    exclusive_mapping_rows = []
    exclusive_stage = {}

    for offset, row in enumerate(
        unmatched.itertuples(
            index=False
        )
    ):
        segment_id = (
            f"S_{next_index + offset:07d}"
        )

        exclusive_segment_rows.append(
            {
                "analysis_segment_id": segment_id,
                "source_mode": TravelMode.TRANSIT.value,
                "source_modal_edge_id": str(
                    row.modal_edge_id
                ),
                "strict_key": (
                    "transit_exclusive:"
                    + str(
                        row.transit_physical_edge_id
                    )
                ),
                "osmid_signature": "",
                "osmid_set": frozenset(),
                "name_norm": "",
                "highway_norm": "transit",
                "length_m": float(
                    row.geometry.length
                ),
                "geometry": row.geometry,
            }
        )

        exclusive_mapping_rows.append(
            {
                "modal_edge_id": str(
                    row.modal_edge_id
                ),
                "mode": TravelMode.TRANSIT.value,
                "analysis_segment_id": segment_id,
                "match_method": "gtfs_exclusive",
                "match_quality": 1.0,
                "segment_coverage": 1.0,
                "shape_coverage": 1.0,
                "angle_difference_deg": 0.0,
                "accepted_by": "exclusive",
                "mapping_scope": "full_transit_physical_network",
                "match_stage": "exclusive",
            }
        )

        exclusive_stage[
            str(
                row.transit_physical_edge_id
            )
        ] = segment_id

    if exclusive_segment_rows:
        exclusive_segments = gpd.GeoDataFrame(
            exclusive_segment_rows,
            geometry="geometry",
            crs=analysis_segments.crs,
        )

        analysis_segments = pd.concat(
            [
                analysis_segments,
                exclusive_segments,
            ],
            ignore_index=True,
            sort=False,
        )
        analysis_segments = gpd.GeoDataFrame(
            analysis_segments,
            geometry="geometry",
            crs=exclusive_segments.crs,
        )

        transit_mapping = pd.concat(
            [
                transit_mapping,
                pd.DataFrame(
                    exclusive_mapping_rows
                ),
            ],
            ignore_index=True,
            sort=False,
        )

    segment_mapping = pd.concat(
        [
            segment_mapping,
            transit_mapping,
        ],
        ignore_index=True,
        sort=False,
    )

    if not diagnostics.empty:
        diagnostics = diagnostics.copy()

        unmatched_mask = diagnostics[
            "connection_id"
        ].astype(
            str
        ).isin(
            set(
                exclusive_stage
            )
        )

        diagnostics.loc[
            unmatched_mask,
            "matched_segments",
        ] = 1
        diagnostics.loc[
            unmatched_mask,
            "shape_coverage_pct",
        ] = 100.0
        diagnostics.loc[
            unmatched_mask,
            "match_stage",
        ] = "exclusive"
        diagnostics.loc[
            unmatched_mask,
            "final_match_stage",
        ] = "exclusive"

    expected = set(
        transit_physical_edges[
            "modal_edge_id"
        ].astype(
            str
        )
    )
    actual = set(
        transit_mapping[
            "modal_edge_id"
        ].astype(
            str
        )
    )

    if expected != actual:
        missing = sorted(
            expected
            - actual
        )

        raise RuntimeError(
            "A integração física transit não mapeou todos os trechos: "
            f"{len(missing)} ausentes"
        )

    return (
        analysis_segments,
        segment_mapping,
        transit_mapping,
        diagnostics,
    )


def summarize_transit_physical_integration(
    transit_physical_edges: gpd.GeoDataFrame,
    transit_mapping: pd.DataFrame,
    diagnostics: pd.DataFrame,
) -> dict:
    """Resume como a rede física GTFS foi incorporada à camada comum"""

    total = int(
        transit_physical_edges[
            "modal_edge_id"
        ].nunique()
    )

    if transit_mapping.empty:
        primary = 0
        fallback = 0
        exclusive = 0
    else:
        grouped = (
            transit_mapping.groupby(
                "match_stage"
            )[
                "modal_edge_id"
            ]
            .nunique()
        )
        primary = int(
            grouped.get(
                "primary",
                0,
            )
        )
        fallback = int(
            grouped.get(
                "fallback",
                0,
            )
        )
        exclusive = int(
            grouped.get(
                "exclusive",
                0,
            )
        )

    mean_coverage = (
        float(
            diagnostics[
                "shape_coverage_pct"
            ].mean()
        )
        if not diagnostics.empty
        else np.nan
    )

    median_coverage = (
        float(
            diagnostics[
                "shape_coverage_pct"
            ].median()
        )
        if not diagnostics.empty
        else np.nan
    )

    return {
        "transit_physical_edges": total,
        "primary_matches": primary,
        "fallback_matches": fallback,
        "exclusive_transit_segments": exclusive,
        "mapped_transit_physical_edges": (
            primary
            + fallback
            + exclusive
        ),
        "mean_shape_coverage_pct": mean_coverage,
        "median_shape_coverage_pct": median_coverage,
    }
