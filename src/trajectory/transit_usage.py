"""Converte rotas GTFS em observações compatíveis com a análise por segmento

Representa acesso e egresso com as arestas exatas da rede de caminhada
Representa o trecho embarcado com as conexões GTFS selecionadas pelo roteador
Extrai a geometria parcial do shape entre duas paradas consecutivas
Mapeia essas geometrias para a camada física comum usada pelo H_soc
"""

from __future__ import annotations

from collections.abc import Mapping
from math import atan2, degrees
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.ops import substring, unary_union

from src.domain.enums import TravelMode
from src.routing.multimodal_router import SUCCESS_STATUSES


def _enum_value(
    value,
) -> str | None:
    """Retorna o valor textual de um Enum quando disponível"""

    if value is None:
        return None

    return (
        value.value
        if hasattr(
            value,
            "value",
        )
        else str(
            value
        )
    )


def _safe_float(
    value,
) -> float | None:
    """Converte um valor em float quando possível"""

    try:
        return float(
            value
        )
    except (
        TypeError,
        ValueError,
    ):
        return None


def _stringify_osm_value(
    value,
) -> str | None:
    """Converte atributos OSM heterogêneos em texto estável"""

    if value is None:
        return None

    if isinstance(
        value,
        (
            list,
            tuple,
            set,
        ),
    ):
        return "|".join(
            str(
                item
            )
            for item in value
        )

    return str(
        value
    )


def _walk_edge_row(
    *,
    agent,
    scenario_name: str,
    walk_graph,
    edge: tuple[
        int,
        int,
        int,
    ],
    position: int,
    route_edge_count: int,
    leg_name: str,
) -> dict:
    """Cria uma linha de uso para acesso ou egresso pela rede de caminhada"""

    u, v, key = (
        int(
            edge[
                0
            ]
        ),
        int(
            edge[
                1
            ]
        ),
        int(
            edge[
                2
            ]
        ),
    )

    attributes = walk_graph.get_edge_data(
        u,
        v,
        key,
    )

    if attributes is None:
        raise ValueError(
            "Aresta de caminhada do transporte coletivo não encontrada: "
            f"({u}, {v}, {key})"
        )

    return {
        "scenario": scenario_name,
        "agent_id": agent.agent_id,
        "income_group": _enum_value(
            agent.income_group
        ),
        "purpose": _enum_value(
            agent.purpose
        ),
        "mode": TravelMode.TRANSIT.value,
        "mapping_mode": TravelMode.WALK.value,
        "leg_mode": TravelMode.WALK.value,
        "transit_leg": leg_name,
        "origin_id": agent.origin_id,
        "destination_id": agent.destination_id,
        "route_position": position,
        "route_edge_count": route_edge_count,
        "u": u,
        "v": v,
        "key": key,
        "modal_edge_id": (
            f"walk:{u}:{v}:{key}"
        ),
        "edge_length_m": _safe_float(
            attributes.get(
                "length"
            )
        ),
        "osmid": _stringify_osm_value(
            attributes.get(
                "osmid"
            )
        ),
        "name": _stringify_osm_value(
            attributes.get(
                "name"
            )
        ),
        "highway": _stringify_osm_value(
            attributes.get(
                "highway"
            )
        ),
        "transit_connection_id": None,
        "transit_trip_id": None,
        "transit_route_id": None,
        "transit_shape_id": None,
        "from_stop_id": None,
        "to_stop_id": None,
        "from_shape_position_m": None,
        "to_shape_position_m": None,
    }


def _transit_connection_row(
    *,
    agent,
    scenario_name: str,
    connection,
    position: int,
    route_edge_count: int,
) -> dict:
    """Cria uma linha de uso para uma conexão GTFS embarcada"""

    connection_id = str(
        connection.connection_id
    )

    return {
        "scenario": scenario_name,
        "agent_id": agent.agent_id,
        "income_group": _enum_value(
            agent.income_group
        ),
        "purpose": _enum_value(
            agent.purpose
        ),
        "mode": TravelMode.TRANSIT.value,
        "mapping_mode": TravelMode.TRANSIT.value,
        "leg_mode": TravelMode.TRANSIT.value,
        "transit_leg": "in_vehicle",
        "origin_id": agent.origin_id,
        "destination_id": agent.destination_id,
        "route_position": position,
        "route_edge_count": route_edge_count,
        "u": None,
        "v": None,
        "key": None,
        "modal_edge_id": (
            f"transit:{connection_id}"
        ),
        "edge_length_m": _safe_float(
            getattr(
                connection,
                "shape_segment_distance_m",
                None,
            )
        ),
        "osmid": None,
        "name": None,
        "highway": None,
        "transit_connection_id": connection_id,
        "transit_trip_id": str(
            connection.trip_id
        ),
        "transit_route_id": str(
            connection.route_id
        ),
        "transit_shape_id": (
            str(
                connection.shape_id
            )
            if hasattr(
                connection,
                "shape_id",
            )
            and pd.notna(
                connection.shape_id
            )
            else None
        ),
        "from_stop_id": str(
            connection.from_stop_id
        ),
        "to_stop_id": str(
            connection.to_stop_id
        ),
        "from_shape_position_m": _safe_float(
            getattr(
                connection,
                "from_shape_position_m",
                None,
            )
        ),
        "to_shape_position_m": _safe_float(
            getattr(
                connection,
                "to_shape_position_m",
                None,
            )
        ),
    }


def build_transit_edge_usage(
    agents,
    *,
    walk_graph,
    connections: pd.DataFrame,
    scenario_name: str,
) -> pd.DataFrame:
    """Explode rotas de transporte coletivo em caminhada e conexões GTFS"""

    if connections[
        "connection_id"
    ].duplicated().any():
        raise ValueError(
            "transit_connections_routable_processed.parquet possui connection_id duplicado"
        )

    connection_lookup = (
        connections.set_index(
            "connection_id",
            drop=False,
        )
    )

    rows: list[
        dict
    ] = []

    for agent in agents:
        if agent.route_status not in SUCCESS_STATUSES:
            continue

        if agent.mode is not TravelMode.TRANSIT:
            continue

        access_edges = list(
            agent.transit_access_walk_edges
        )
        connection_ids = list(
            agent.transit_connection_ids
        )
        egress_edges = list(
            agent.transit_egress_walk_edges
        )

        total_edges = (
            len(
                access_edges
            )
            + len(
                connection_ids
            )
            + len(
                egress_edges
            )
        )

        position = 0

        for edge in access_edges:
            rows.append(
                _walk_edge_row(
                    agent=agent,
                    scenario_name=scenario_name,
                    walk_graph=walk_graph,
                    edge=edge,
                    position=position,
                    route_edge_count=total_edges,
                    leg_name="access_walk",
                )
            )
            position += 1

        for connection_id in connection_ids:
            connection_id = str(
                connection_id
            )

            if connection_id not in connection_lookup.index:
                raise ValueError(
                    "Conexão GTFS usada pelo agente não está na tabela roteável: "
                    f"{connection_id}"
                )

            connection = connection_lookup.loc[
                connection_id
            ]

            rows.append(
                _transit_connection_row(
                    agent=agent,
                    scenario_name=scenario_name,
                    connection=connection,
                    position=position,
                    route_edge_count=total_edges,
                )
            )
            position += 1

        for edge in egress_edges:
            rows.append(
                _walk_edge_row(
                    agent=agent,
                    scenario_name=scenario_name,
                    walk_graph=walk_graph,
                    edge=edge,
                    position=position,
                    route_edge_count=total_edges,
                    leg_name="egress_walk",
                )
            )
            position += 1

    columns = [
        "scenario",
        "agent_id",
        "income_group",
        "purpose",
        "mode",
        "mapping_mode",
        "leg_mode",
        "transit_leg",
        "origin_id",
        "destination_id",
        "route_position",
        "route_edge_count",
        "u",
        "v",
        "key",
        "modal_edge_id",
        "edge_length_m",
        "osmid",
        "name",
        "highway",
        "transit_connection_id",
        "transit_trip_id",
        "transit_route_id",
        "transit_shape_id",
        "from_stop_id",
        "to_stop_id",
        "from_shape_position_m",
        "to_shape_position_m",
    ]

    return pd.DataFrame(
        rows,
        columns=columns,
    )


def build_used_transit_connection_geometries(
    edge_usage: pd.DataFrame,
    *,
    connections: pd.DataFrame,
    shapes: gpd.GeoDataFrame,
) -> tuple[
    gpd.GeoDataFrame,
    pd.DataFrame,
]:
    """Extrai somente os trechos de shape usados pelos agentes do piloto"""

    used_ids = (
        edge_usage.loc[
            edge_usage[
                "mapping_mode"
            ]
            == TravelMode.TRANSIT.value,
            "transit_connection_id",
        ]
        .dropna()
        .astype(
            str
        )
        .drop_duplicates()
        .tolist()
    )

    if not used_ids:
        empty = gpd.GeoDataFrame(
            columns=[
                "modal_edge_id",
                "connection_id",
                "shape_id",
                "geometry",
            ],
            geometry="geometry",
            crs=shapes.crs,
        )

        return (
            empty,
            pd.DataFrame(
                columns=[
                    "connection_id",
                    "geometry_status",
                    "geometry_length_m",
                ]
            ),
        )

    selected = (
        connections.loc[
            connections[
                "connection_id"
            ]
            .astype(
                str
            )
            .isin(
                used_ids
            )
        ]
        .drop_duplicates(
            subset=[
                "connection_id",
            ]
        )
        .copy()
    )

    shape_lookup = (
        shapes[
            [
                "shape_id",
                "geometry",
            ]
        ]
        .drop_duplicates(
            subset=[
                "shape_id",
            ]
        )
        .set_index(
            "shape_id"
        )[
            "geometry"
        ]
        .to_dict()
    )

    geometry_rows: list[
        dict
    ] = []
    diagnostics: list[
        dict
    ] = []

    for row in selected.itertuples(
        index=False
    ):
        connection_id = str(
            row.connection_id
        )
        shape_id = (
            str(
                row.shape_id
            )
            if hasattr(
                row,
                "shape_id",
            )
            and pd.notna(
                row.shape_id
            )
            else None
        )

        start = _safe_float(
            getattr(
                row,
                "from_shape_position_m",
                None,
            )
        )
        end = _safe_float(
            getattr(
                row,
                "to_shape_position_m",
                None,
            )
        )

        status = "ok"
        geometry = None

        if shape_id is None:
            status = "missing_shape_id"
        elif shape_id not in shape_lookup:
            status = "missing_shape_geometry"
        elif start is None or end is None:
            status = "missing_shape_position"
        else:
            line = shape_lookup[
                shape_id
            ]

            if (
                line is None
                or line.is_empty
                or line.length <= 0
            ):
                status = "invalid_shape_geometry"
            else:
                start_clamped = min(
                    max(
                        float(
                            start
                        ),
                        0.0,
                    ),
                    float(
                        line.length
                    ),
                )
                end_clamped = min(
                    max(
                        float(
                            end
                        ),
                        0.0,
                    ),
                    float(
                        line.length
                    ),
                )

                if end_clamped <= start_clamped:
                    status = "nonpositive_shape_progress"
                else:
                    geometry = substring(
                        line,
                        start_clamped,
                        end_clamped,
                        normalized=False,
                    )

                    if (
                        geometry is None
                        or geometry.is_empty
                        or geometry.length <= 0
                    ):
                        status = "empty_substring"
                        geometry = None

        diagnostics.append(
            {
                "connection_id": connection_id,
                "shape_id": shape_id,
                "geometry_status": status,
                "geometry_length_m": (
                    float(
                        geometry.length
                    )
                    if geometry is not None
                    else np.nan
                ),
            }
        )

        if geometry is None:
            continue

        geometry_rows.append(
            {
                "modal_edge_id": (
                    f"transit:{connection_id}"
                ),
                "connection_id": connection_id,
                "shape_id": shape_id,
                "geometry": geometry,
            }
        )

    geometry_frame = gpd.GeoDataFrame(
        geometry_rows,
        geometry="geometry",
        crs=shapes.crs,
    )

    return (
        geometry_frame,
        pd.DataFrame(
            diagnostics
        ),
    )


def _orientation_deg(
    geometry,
) -> float | None:
    """Calcula a orientação global de uma linha no intervalo de zero a 180 graus"""

    if (
        geometry is None
        or geometry.is_empty
        or geometry.geom_type != "LineString"
    ):
        return None

    coordinates = list(
        geometry.coords
    )

    if len(
        coordinates
    ) < 2:
        return None

    x1, y1 = coordinates[
        0
    ][
        :2
    ]
    x2, y2 = coordinates[
        -1
    ][
        :2
    ]

    dx = float(
        x2
        - x1
    )
    dy = float(
        y2
        - y1
    )

    if (
        abs(
            dx
        )
        + abs(
            dy
        )
        <= 1e-9
    ):
        return None

    angle = degrees(
        atan2(
            dy,
            dx,
        )
    )

    return (
        angle
        % 180.0
    )


def _angle_difference_deg(
    first: float | None,
    second: float | None,
) -> float:
    """Calcula a menor diferença entre orientações não direcionais"""

    if (
        first is None
        or second is None
    ):
        return 0.0

    difference = abs(
        float(
            first
        )
        - float(
            second
        )
    )

    return min(
        difference,
        180.0
        - difference,
    )


def map_transit_connections_to_analysis_segments(
    connection_geometries: gpd.GeoDataFrame,
    *,
    analysis_segments: gpd.GeoDataFrame,
    tolerance_m: float,
    min_segment_coverage: float,
    max_angle_difference_deg: float,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
]:
    """Mapeia trechos GTFS usados para os segmentos físicos comuns"""

    if tolerance_m <= 0:
        raise ValueError(
            "tolerance_m precisa ser maior que zero"
        )

    if not 0 < min_segment_coverage <= 1:
        raise ValueError(
            "min_segment_coverage precisa estar no intervalo (0, 1]"
        )

    if not 0 < max_angle_difference_deg <= 90:
        raise ValueError(
            "max_angle_difference_deg precisa estar no intervalo (0, 90]"
        )

    if connection_geometries.empty:
        return (
            pd.DataFrame(
                columns=[
                    "modal_edge_id",
                    "mode",
                    "analysis_segment_id",
                    "match_method",
                    "match_quality",
                    "mapping_scope",
                ]
            ),
            pd.DataFrame(
                columns=[
                    "connection_id",
                    "matched_segments",
                    "shape_coverage_pct",
                ]
            ),
        )

    if (
        connection_geometries.crs is None
        or analysis_segments.crs is None
    ):
        raise ValueError(
            "connection_geometries e analysis_segments precisam possuir CRS"
        )

    if str(
        connection_geometries.crs
    ) != str(
        analysis_segments.crs
    ):
        connection_geometries = (
            connection_geometries.to_crs(
                analysis_segments.crs
            )
        )

    if not analysis_segments.crs.is_projected:
        raise ValueError(
            "analysis_segments precisa usar CRS projetado em metros"
        )

    mapping_rows: list[
        dict
    ] = []
    diagnostic_rows: list[
        dict
    ] = []

    for row in connection_geometries.itertuples(
        index=False
    ):
        geometry = row.geometry
        connection_angle = _orientation_deg(
            geometry
        )
        search_geometry = geometry.buffer(
            tolerance_m
        )

        candidate_positions = list(
            analysis_segments.sindex.intersection(
                search_geometry.bounds
            )
        )

        matched_geometries = []

        for position in candidate_positions:
            segment = analysis_segments.iloc[
                position
            ]
            segment_geometry = segment.geometry

            if (
                segment_geometry is None
                or segment_geometry.is_empty
                or segment_geometry.length <= 0
            ):
                continue

            angle_difference = (
                _angle_difference_deg(
                    connection_angle,
                    _orientation_deg(
                        segment_geometry
                    ),
                )
            )

            if (
                angle_difference
                > max_angle_difference_deg
            ):
                continue

            covered = segment_geometry.intersection(
                search_geometry
            )

            coverage = min(
                1.0,
                float(
                    covered.length
                )
                / float(
                    segment_geometry.length
                ),
            )

            if coverage < min_segment_coverage:
                continue

            mapping_rows.append(
                {
                    "modal_edge_id": str(
                        row.modal_edge_id
                    ),
                    "mode": TravelMode.TRANSIT.value,
                    "analysis_segment_id": str(
                        segment.analysis_segment_id
                    ),
                    "match_method": "gtfs_shape_geometry",
                    "match_quality": float(
                        coverage
                    ),
                    "mapping_scope": "used_transit_connections",
                }
            )
            matched_geometries.append(
                segment_geometry
            )

        if matched_geometries:
            covered_shape = geometry.intersection(
                unary_union(
                    [
                        candidate.buffer(
                            tolerance_m
                        )
                        for candidate in matched_geometries
                    ]
                )
            )

            shape_coverage = min(
                1.0,
                float(
                    covered_shape.length
                )
                / float(
                    geometry.length
                ),
            )
        else:
            shape_coverage = 0.0

        diagnostic_rows.append(
            {
                "connection_id": str(
                    row.connection_id
                ),
                "shape_id": str(
                    row.shape_id
                ),
                "geometry_length_m": float(
                    geometry.length
                ),
                "matched_segments": len(
                    matched_geometries
                ),
                "shape_coverage_pct": (
                    100.0
                    * shape_coverage
                ),
            }
        )

    mapping = (
        pd.DataFrame(
            mapping_rows
        )
        .drop_duplicates(
            subset=[
                "modal_edge_id",
                "analysis_segment_id",
            ]
        )
        .reset_index(
            drop=True
        )
    )

    diagnostics = pd.DataFrame(
        diagnostic_rows
    )

    return (
        mapping,
        diagnostics,
    )


def summarize_transit_spatial_matching(
    geometry_diagnostics: pd.DataFrame,
    match_diagnostics: pd.DataFrame,
) -> dict:
    """Resume a disponibilidade geométrica e a cobertura do mapeamento GTFS"""

    total_connections = int(
        len(
            geometry_diagnostics
        )
    )
    valid_geometry = int(
        (
            geometry_diagnostics[
                "geometry_status"
            ]
            == "ok"
        ).sum()
    )

    if match_diagnostics.empty:
        matched_connections = 0
        mean_coverage = float(
            "nan"
        )
        median_coverage = float(
            "nan"
        )
    else:
        matched_connections = int(
            (
                match_diagnostics[
                    "matched_segments"
                ]
                > 0
            ).sum()
        )
        mean_coverage = float(
            match_diagnostics[
                "shape_coverage_pct"
            ].mean()
        )
        median_coverage = float(
            match_diagnostics[
                "shape_coverage_pct"
            ].median()
        )

    return {
        "used_transit_connections": total_connections,
        "connections_with_valid_geometry": valid_geometry,
        "connections_with_segment_match": matched_connections,
        "mean_shape_coverage_pct": mean_coverage,
        "median_shape_coverage_pct": median_coverage,
    }
