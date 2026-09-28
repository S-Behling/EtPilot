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
        "transit_physical_edge_id": None,
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
    physical_edge_id = str(
        connection.transit_physical_edge_id
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
            f"transit:{physical_edge_id}"
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
        "transit_physical_edge_id": physical_edge_id,
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

    connection_table = connections.copy()
    connection_table[
        "connection_id"
    ] = connection_table[
        "connection_id"
    ].astype(
        "string"
    )

    connection_lookup = (
        connection_table.set_index(
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
        "transit_physical_edge_id",
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


def _projection_candidates_on_line(
    line,
    point,
    *,
    max_candidates: int = 16,
) -> list[tuple[float, float]]:
    """Calcula posições candidatas de um ponto ao longo de um shape"""

    if (
        line is None
        or point is None
        or line.is_empty
        or point.is_empty
        or line.geom_type != "LineString"
    ):
        return []

    coordinates = np.asarray(
        line.coords,
        dtype=float,
    )

    if len(
        coordinates
    ) < 2:
        return []

    starts = coordinates[
        :-1,
        :2,
    ]
    ends = coordinates[
        1:,
        :2,
    ]
    vectors = (
        ends
        - starts
    )
    lengths = np.linalg.norm(
        vectors,
        axis=1,
    )
    valid = lengths > 1e-9

    if not valid.any():
        return []

    point_xy = np.asarray(
        [
            float(
                point.x
            ),
            float(
                point.y
            ),
        ],
        dtype=float,
    )

    squared = (
        lengths
        * lengths
    )
    t = np.zeros(
        len(
            lengths
        ),
        dtype=float,
    )

    t[
        valid
    ] = (
        np.sum(
            (
                point_xy
                - starts[
                    valid
                ]
            )
            * vectors[
                valid
            ],
            axis=1,
        )
        / squared[
            valid
        ]
    )
    t = np.clip(
        t,
        0.0,
        1.0,
    )

    projected = (
        starts
        + vectors
        * t[
            :,
            None,
        ]
    )
    distances = np.linalg.norm(
        projected
        - point_xy,
        axis=1,
    )

    cumulative = np.concatenate(
        [
            np.asarray(
                [
                    0.0,
                ]
            ),
            np.cumsum(
                lengths
            ),
        ]
    )
    positions = (
        cumulative[
            :-1
        ]
        + t
        * lengths
    )

    candidate_indices = np.argsort(
        distances,
        kind="stable",
    )[
        :max_candidates
    ]

    return [
        (
            float(
                positions[
                    index
                ]
            ),
            float(
                distances[
                    index
                ]
            ),
        )
        for index in candidate_indices
        if valid[
            index
        ]
    ]


def _forward_stop_positions(
    line,
    from_point,
    to_point,
) -> tuple[
    float,
    float,
    float,
    float,
] | None:
    """Seleciona projeções sucessivas compatíveis com a ordem das paradas"""

    from_candidates = _projection_candidates_on_line(
        line,
        from_point,
    )
    to_candidates = _projection_candidates_on_line(
        line,
        to_point,
    )

    pairs: list[
        tuple[
            float,
            float,
            float,
            float,
            float,
            float,
        ]
    ] = []

    for (
        start,
        start_distance,
    ) in from_candidates:
        for (
            end,
            end_distance,
        ) in to_candidates:
            route_distance = (
                end
                - start
            )

            if route_distance <= 1e-6:
                continue

            pairs.append(
                (
                    start_distance
                    + end_distance,
                    route_distance,
                    start,
                    end,
                    start_distance,
                    end_distance,
                )
            )

    if not pairs:
        return None

    (
        _,
        _,
        start,
        end,
        start_distance,
        end_distance,
    ) = min(
        pairs,
        key=lambda item: (
            item[
                0
            ],
            item[
                1
            ],
        ),
    )

    return (
        float(
            start
        ),
        float(
            end
        ),
        float(
            start_distance
        ),
        float(
            end_distance
        ),
    )


def build_used_transit_connection_geometries(
    edge_usage: pd.DataFrame,
    *,
    connections: pd.DataFrame,
    shapes: gpd.GeoDataFrame,
    stops: gpd.GeoDataFrame | None = None,
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
                    "shape_id",
                    "geometry_status",
                    "position_method",
                    "from_snap_distance_m",
                    "to_snap_distance_m",
                    "geometry_length_m",
                ]
            ),
        )

    connection_table = connections.copy()
    connection_table[
        "connection_id"
    ] = connection_table[
        "connection_id"
    ].astype(
        "string"
    )

    selected = (
        connection_table.loc[
            connection_table[
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

    shape_table = shapes[
        [
            "shape_id",
            "geometry",
        ]
    ].copy()
    shape_table[
        "shape_id"
    ] = shape_table[
        "shape_id"
    ].astype(
        "string"
    )

    shape_lookup = (
        shape_table
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

    if stops is not None:
        stop_table = stops[
            [
                "stop_id",
                "geometry",
            ]
        ].copy()
        stop_table[
            "stop_id"
        ] = stop_table[
            "stop_id"
        ].astype(
            "string"
        )
        stop_lookup = (
            stop_table
            .drop_duplicates(
                subset=[
                    "stop_id",
                ]
            )
            .set_index(
                "stop_id"
            )[
                "geometry"
            ]
            .to_dict()
        )
    else:
        stop_lookup = {}

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
        position_method = None
        from_snap_distance_m = np.nan
        to_snap_distance_m = np.nan

        if shape_id is None:
            status = "missing_shape_id"
        elif shape_id not in shape_lookup:
            status = "missing_shape_geometry"
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
                valid_processed_positions = (
                    start is not None
                    and end is not None
                    and float(
                        end
                    )
                    > float(
                        start
                    )
                )

                if valid_processed_positions:
                    position_method = "processed_shape_position"
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
                else:
                    from_stop_id = str(
                        row.from_stop_id
                    )
                    to_stop_id = str(
                        row.to_stop_id
                    )
                    fallback_positions = (
                        _forward_stop_positions(
                            line,
                            stop_lookup.get(
                                from_stop_id
                            ),
                            stop_lookup.get(
                                to_stop_id
                            ),
                        )
                        if stop_lookup
                        else None
                    )

                    if fallback_positions is None:
                        status = (
                            "missing_shape_position"
                            if start is None
                            or end is None
                            else "nonpositive_shape_progress"
                        )
                        start_clamped = None
                        end_clamped = None
                    else:
                        (
                            start_clamped,
                            end_clamped,
                            from_snap_distance_m,
                            to_snap_distance_m,
                        ) = fallback_positions
                        position_method = "forward_stop_projection"
                        status = "ok_fallback_projection"

                if (
                    start_clamped is not None
                    and end_clamped is not None
                    and end_clamped > start_clamped
                ):
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
                "position_method": position_method,
                "from_snap_distance_m": from_snap_distance_m,
                "to_snap_distance_m": to_snap_distance_m,
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

    if geometry_rows:
        geometry_frame = gpd.GeoDataFrame(
            geometry_rows,
            geometry="geometry",
            crs=shapes.crs,
        )
    else:
        geometry_frame = gpd.GeoDataFrame(
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


def _local_orientation_deg(
    geometry,
    reference_point,
    *,
    half_window_m: float = 25.0,
) -> float | None:
    """Calcula a orientação local da linha próxima ao segmento candidato"""

    if (
        geometry is None
        or geometry.is_empty
        or geometry.length <= 0
    ):
        return None

    projected = float(
        geometry.project(
            reference_point
        )
    )

    start = max(
        0.0,
        projected
        - half_window_m,
    )
    end = min(
        float(
            geometry.length
        ),
        projected
        + half_window_m,
    )

    if end <= start:
        return _orientation_deg(
            geometry
        )

    local_geometry = substring(
        geometry,
        start,
        end,
        normalized=False,
    )

    return _orientation_deg(
        local_geometry
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
    min_coverage: float,
    max_angle_difference_deg: float,
    match_method: str = "gtfs_shape_geometry",
    mapping_scope: str = "used_transit_connections",
    match_stage: str = "primary",
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
]:
    """Mapeia trechos GTFS usados para os segmentos físicos comuns"""

    if tolerance_m <= 0:
        raise ValueError(
            "tolerance_m precisa ser maior que zero"
        )

    if not 0 < min_coverage <= 1:
        raise ValueError(
            "min_coverage precisa estar no intervalo (0, 1]"
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
                    "segment_coverage",
                    "shape_coverage",
                    "angle_difference_deg",
                    "accepted_by",
                    "mapping_scope",
                    "match_stage",
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

            segment_midpoint = segment_geometry.interpolate(
                0.5,
                normalized=True,
            )
            local_connection_angle = (
                _local_orientation_deg(
                    geometry,
                    segment_midpoint,
                )
            )
            angle_difference = (
                _angle_difference_deg(
                    local_connection_angle,
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

            covered_segment = segment_geometry.intersection(
                search_geometry
            )
            segment_coverage = min(
                1.0,
                float(
                    covered_segment.length
                )
                / float(
                    segment_geometry.length
                ),
            )

            covered_shape = geometry.intersection(
                segment_geometry.buffer(
                    tolerance_m
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

            coverage = max(
                segment_coverage,
                shape_coverage,
            )

            if coverage < min_coverage:
                continue

            accepted_by = (
                "both"
                if (
                    segment_coverage
                    >= min_coverage
                    and shape_coverage
                    >= min_coverage
                )
                else (
                    "segment_coverage"
                    if segment_coverage
                    >= min_coverage
                    else "shape_coverage"
                )
            )

            mapping_rows.append(
                {
                    "modal_edge_id": str(
                        row.modal_edge_id
                    ),
                    "mode": TravelMode.TRANSIT.value,
                    "analysis_segment_id": str(
                        segment.analysis_segment_id
                    ),
                    "match_method": match_method,
                    "match_quality": float(
                        coverage
                    ),
                    "segment_coverage": float(
                        segment_coverage
                    ),
                    "shape_coverage": float(
                        shape_coverage
                    ),
                    "angle_difference_deg": float(
                        angle_difference
                    ),
                    "accepted_by": accepted_by,
                    "mapping_scope": mapping_scope,
                    "match_stage": match_stage,
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
                "match_stage": match_stage,
            }
        )

    if mapping_rows:
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
    else:
        mapping = pd.DataFrame(
            columns=[
                "modal_edge_id",
                "mode",
                "analysis_segment_id",
                "match_method",
                "match_quality",
                "segment_coverage",
                "shape_coverage",
                "angle_difference_deg",
                "accepted_by",
                "mapping_scope",
                "match_stage",
            ]
        )

    diagnostics = pd.DataFrame(
        diagnostic_rows,
        columns=[
            "connection_id",
            "shape_id",
            "geometry_length_m",
            "matched_segments",
            "shape_coverage_pct",
            "match_stage",
        ],
    )

    return (
        mapping,
        diagnostics,
    )


def map_transit_connections_hierarchically(
    connection_geometries: gpd.GeoDataFrame,
    *,
    primary_segments: gpd.GeoDataFrame,
    fallback_segments: gpd.GeoDataFrame,
    primary_config: Mapping,
    fallback_config: Mapping,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
]:
    """Aplica uma etapa primária e uma etapa de fallback ao mapeamento GTFS"""

    primary_mapping, primary_diagnostics = (
        map_transit_connections_to_analysis_segments(
            connection_geometries,
            analysis_segments=primary_segments,
            tolerance_m=float(
                primary_config[
                    "tolerance_m"
                ]
            ),
            min_coverage=float(
                primary_config[
                    "min_coverage"
                ]
            ),
            max_angle_difference_deg=float(
                primary_config[
                    "max_angle_difference_deg"
                ]
            ),
            match_method="gtfs_shape_geometry_primary",
            mapping_scope=str(
                primary_config.get(
                    "candidate_scope",
                    "primary",
                )
            ),
            match_stage="primary",
        )
    )

    primary_matched_ids = set(
        primary_mapping[
            "modal_edge_id"
        ].astype(
            str
        )
    )

    fallback_enabled = bool(
        fallback_config.get(
            "enabled",
            True,
        )
    )

    if (
        not fallback_enabled
        or connection_geometries.empty
    ):
        final_diagnostics = (
            primary_diagnostics.copy()
        )
        final_diagnostics[
            "final_match_stage"
        ] = np.where(
            final_diagnostics[
                "matched_segments"
            ]
            > 0,
            "primary",
            "unmatched",
        )

        return (
            primary_mapping,
            final_diagnostics,
        )

    fallback_geometries = (
        connection_geometries.loc[
            ~connection_geometries[
                "modal_edge_id"
            ]
            .astype(
                str
            )
            .isin(
                primary_matched_ids
            )
        ]
        .copy()
        .reset_index(
            drop=True
        )
    )

    fallback_mapping, fallback_diagnostics = (
        map_transit_connections_to_analysis_segments(
            fallback_geometries,
            analysis_segments=fallback_segments,
            tolerance_m=float(
                fallback_config[
                    "tolerance_m"
                ]
            ),
            min_coverage=float(
                fallback_config[
                    "min_coverage"
                ]
            ),
            max_angle_difference_deg=float(
                fallback_config[
                    "max_angle_difference_deg"
                ]
            ),
            match_method="gtfs_shape_geometry_fallback",
            mapping_scope=str(
                fallback_config.get(
                    "candidate_scope",
                    "fallback",
                )
            ),
            match_stage="fallback",
        )
    )

    mapping = (
        pd.concat(
            [
                primary_mapping,
                fallback_mapping,
            ],
            ignore_index=True,
            sort=False,
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

    primary_by_connection = (
        primary_diagnostics.set_index(
            "connection_id"
        )
    )
    fallback_by_connection = (
        fallback_diagnostics.set_index(
            "connection_id"
        )
        if not fallback_diagnostics.empty
        else pd.DataFrame()
    )

    final_rows: list[
        dict
    ] = []

    for row in connection_geometries.itertuples(
        index=False
    ):
        connection_id = str(
            row.connection_id
        )

        primary_row = (
            primary_by_connection.loc[
                connection_id
            ]
            if connection_id
            in primary_by_connection.index
            else None
        )

        if (
            primary_row is not None
            and int(
                primary_row[
                    "matched_segments"
                ]
            )
            > 0
        ):
            final_rows.append(
                {
                    **primary_row.to_dict(),
                    "connection_id": connection_id,
                    "final_match_stage": "primary",
                }
            )
            continue

        if (
            not fallback_diagnostics.empty
            and connection_id
            in fallback_by_connection.index
        ):
            fallback_row = fallback_by_connection.loc[
                connection_id
            ]

            final_rows.append(
                {
                    **fallback_row.to_dict(),
                    "connection_id": connection_id,
                    "final_match_stage": (
                        "fallback"
                        if int(
                            fallback_row[
                                "matched_segments"
                            ]
                        )
                        > 0
                        else "unmatched"
                    ),
                }
            )
            continue

        final_rows.append(
            {
                "connection_id": connection_id,
                "shape_id": str(
                    row.shape_id
                ),
                "geometry_length_m": float(
                    row.geometry.length
                ),
                "matched_segments": 0,
                "shape_coverage_pct": 0.0,
                "match_stage": "none",
                "final_match_stage": "unmatched",
            }
        )

    return (
        mapping,
        pd.DataFrame(
            final_rows
        ),
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
        geometry_diagnostics[
            "geometry_status"
        ]
        .astype(
            str
        )
        .str.startswith(
            "ok"
        )
        .sum()
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

    primary_matches = int(
        (
            match_diagnostics.get(
                "final_match_stage",
                pd.Series(
                    dtype="string"
                ),
            )
            == "primary"
        ).sum()
    )
    fallback_matches = int(
        (
            match_diagnostics.get(
                "final_match_stage",
                pd.Series(
                    dtype="string"
                ),
            )
            == "fallback"
        ).sum()
    )

    return {
        "used_transit_connections": total_connections,
        "connections_with_valid_geometry": valid_geometry,
        "connections_with_segment_match": matched_connections,
        "primary_matches": primary_matches,
        "fallback_matches": fallback_matches,
        "mean_shape_coverage_pct": mean_coverage,
        "median_shape_coverage_pct": median_coverage,
    }
