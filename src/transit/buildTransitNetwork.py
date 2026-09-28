"""Prepara a estrutura de transporte coletivo para o roteamento temporal

Associa cada parada GTFS ao nó mais próximo da rede de caminhada
Calcula a distância e o tempo do conector entre parada e rede pedonal
Transforma stop_times em conexões temporais entre paradas consecutivas
Resume a topologia das ligações e o volume de viagens por data de serviço
Mantém a tabela de conexões em vez de criar um grafo temporal expandido
"""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from src.network.multimodal import (
    assign_modal_nodes,
    load_mode_graphs,
)
from src.transit.validateGTFSTemporalQuality import (
    build_trip_temporal_quality,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config" / "config.json"


def _load_config() -> dict:
    """Carrega a configuração principal do projeto"""

    with CONFIG_PATH.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(
            file
        )


def _format_int_pt(
    value,
) -> str:
    """Formata números inteiros com separador de milhar brasileiro"""

    return f"{int(value):,}".replace(
        ",",
        ".",
    )


def _format_float_pt(
    value,
    *,
    decimals: int = 1,
) -> str:
    """Formata números decimais com vírgula"""

    formatted = f"{float(value):,.{decimals}f}"

    return (
        formatted
        .replace(
            ",",
            "_",
        )
        .replace(
            ".",
            ",",
        )
        .replace(
            "_",
            ".",
        )
    )


def _format_percentage_pt(
    numerator,
    denominator,
) -> str:
    """Formata uma proporção como percentual com vírgula decimal"""

    denominator_value = float(
        denominator
    )

    if denominator_value <= 0:
        return "0,0%"

    value = (
        100.0
        * float(
            numerator
        )
        / denominator_value
    )

    return (
        f"{value:.1f}%"
        .replace(
            ".",
            ",",
        )
    )


def _format_date_pt(
    value,
) -> str:
    """Formata uma data no padrão dia/mês/ano"""

    return pd.Timestamp(
        value
    ).strftime(
        "%d/%m/%Y"
    )


def _replace_gpkg(
    geodata: gpd.GeoDataFrame,
    path: Path,
    *,
    layer: str,
) -> None:
    """Substitui um GeoPackage processado de forma explícita"""

    if path.exists():
        path.unlink()

    geodata.to_file(
        path,
        layer=layer,
        driver="GPKG",
        engine="pyogrio",
    )


def _load_processed_gtfs(
    data_dir: Path,
) -> tuple[
    gpd.GeoDataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:
    """Carrega as tabelas processadas necessárias para a rede temporal"""

    required = {
        "stops": (
            data_dir
            / "stops_processed.gpkg"
        ),
        "trips": (
            data_dir
            / "trips_processed.parquet"
        ),
        "stop_times": (
            data_dir
            / "stop_times_processed.parquet"
        ),
        "service_dates": (
            data_dir
            / "service_dates_processed.parquet"
        ),
    }

    missing = [
        str(
            path
        )
        for path in required.values()
        if not path.exists()
    ]

    if missing:
        raise FileNotFoundError(
            "Produtos GTFS processados ausentes: "
            f"{missing}"
        )

    stops = gpd.read_file(
        required[
            "stops"
        ],
        layer="stops_processed",
        engine="pyogrio",
    )
    trips = pd.read_parquet(
        required[
            "trips"
        ]
    )
    stop_times = pd.read_parquet(
        required[
            "stop_times"
        ]
    )
    service_dates = pd.read_parquet(
        required[
            "service_dates"
        ]
    )

    return (
        stops,
        trips,
        stop_times,
        service_dates,
    )


def _connect_stops_to_walk_network(
    stops: gpd.GeoDataFrame,
    walk_graph,
    *,
    walk_speed_m_s: float,
) -> tuple[
    gpd.GeoDataFrame,
    pd.DataFrame,
]:
    """Associa cada parada ao nó de caminhada mais próximo"""

    if walk_speed_m_s <= 0:
        raise ValueError(
            "walk_speed_m_s precisa ser maior que zero"
        )

    connected = assign_modal_nodes(
        stops,
        {
            "walk": walk_graph,
        },
        prefix="node_",
    )

    node_x = connected[
        "node_walk"
    ].map(
        lambda node: float(
            walk_graph.nodes[
                int(
                    node
                )
            ][
                "x"
            ]
        )
    )
    node_y = connected[
        "node_walk"
    ].map(
        lambda node: float(
            walk_graph.nodes[
                int(
                    node
                )
            ][
                "y"
            ]
        )
    )

    connector_distance = np.hypot(
        connected.geometry.x.to_numpy(
            dtype=float
        )
        - node_x.to_numpy(
            dtype=float
        ),
        connected.geometry.y.to_numpy(
            dtype=float
        )
        - node_y.to_numpy(
            dtype=float
        ),
    )

    connected[
        "walk_connector_distance_m"
    ] = connector_distance
    connected[
        "walk_connector_time_s"
    ] = (
        connector_distance
        / walk_speed_m_s
    )

    connectors = connected[
        [
            "stop_id",
            "node_walk",
            "walk_connector_distance_m",
            "walk_connector_time_s",
        ]
    ].copy()

    connectors[
        "node_walk"
    ] = pd.to_numeric(
        connectors[
            "node_walk"
        ],
        errors="raise",
    ).astype(
        "Int64"
    )

    return (
        connected,
        connectors,
    )


def _build_scheduled_connections(
    *,
    trips: pd.DataFrame,
    stop_times: pd.DataFrame,
) -> pd.DataFrame:
    """Cria uma conexão temporal para cada par consecutivo de paradas"""

    required_trip_columns = {
        "trip_id",
        "route_id",
        "service_id",
    }
    required_stop_time_columns = {
        "trip_id",
        "stop_id",
        "stop_sequence",
        "arrival_seconds",
        "departure_seconds",
        "time_interpolated",
        "time_interpolation_method",
    }

    missing_trips = (
        required_trip_columns
        - set(
            trips.columns
        )
    )
    missing_stop_times = (
        required_stop_time_columns
        - set(
            stop_times.columns
        )
    )

    if missing_trips:
        raise ValueError(
            "trips_processed.parquet não possui: "
            f"{sorted(missing_trips)}"
        )

    if missing_stop_times:
        raise ValueError(
            "stop_times_processed.parquet não possui: "
            f"{sorted(missing_stop_times)}"
        )

    trip_columns = [
        "trip_id",
        "route_id",
        "service_id",
    ]

    if (
        "shape_id" in trips.columns
        and "shape_id" not in stop_times.columns
    ):
        trip_columns.append(
            "shape_id"
        )

    timetable = stop_times.merge(
        trips[
            trip_columns
        ],
        on="trip_id",
        how="left",
        validate="many_to_one",
    )

    if timetable[
        "route_id"
    ].isna().any():
        raise ValueError(
            "Há stop_times sem route_id após a associação com trips"
        )

    timetable = (
        timetable
        .sort_values(
            [
                "trip_id",
                "stop_sequence",
            ]
        )
        .reset_index(
            drop=True
        )
    )

    grouped = timetable.groupby(
        "trip_id",
        sort=False,
    )

    timetable[
        "to_stop_id"
    ] = grouped[
        "stop_id"
    ].shift(
        -1
    )
    timetable[
        "to_stop_sequence"
    ] = grouped[
        "stop_sequence"
    ].shift(
        -1
    )
    timetable[
        "to_arrival_seconds"
    ] = grouped[
        "arrival_seconds"
    ].shift(
        -1
    )
    timetable[
        "to_time_interpolated"
    ] = grouped[
        "time_interpolated"
    ].shift(
        -1
    )
    timetable[
        "to_time_interpolation_method"
    ] = grouped[
        "time_interpolation_method"
    ].shift(
        -1
    )

    if "shape_position_m" in timetable.columns:
        timetable[
            "to_shape_position_m"
        ] = grouped[
            "shape_position_m"
        ].shift(
            -1
        )

    connections = timetable.loc[
        timetable[
            "to_stop_id"
        ].notna()
    ].copy()

    connections[
        "from_stop_id"
    ] = connections[
        "stop_id"
    ]
    connections[
        "from_stop_sequence"
    ] = pd.to_numeric(
        connections[
            "stop_sequence"
        ],
        errors="raise",
    ).astype(
        "Int64"
    )
    connections[
        "to_stop_sequence"
    ] = pd.to_numeric(
        connections[
            "to_stop_sequence"
        ],
        errors="raise",
    ).astype(
        "Int64"
    )
    connections[
        "departure_seconds"
    ] = pd.to_numeric(
        connections[
            "departure_seconds"
        ],
        errors="raise",
    ).astype(
        "Int64"
    )
    connections[
        "arrival_seconds"
    ] = pd.to_numeric(
        connections[
            "to_arrival_seconds"
        ],
        errors="raise",
    ).astype(
        "Int64"
    )

    connections[
        "in_vehicle_time_s"
    ] = (
        connections[
            "arrival_seconds"
        ]
        - connections[
            "departure_seconds"
        ]
    )

    invalid_duration = (
        connections[
            "in_vehicle_time_s"
        ]
        < 0
    )

    if invalid_duration.any():
        sample = (
            connections.loc[
                invalid_duration,
                [
                    "trip_id",
                    "from_stop_id",
                    "to_stop_id",
                    "departure_seconds",
                    "arrival_seconds",
                ],
            ]
            .head(
                5
            )
            .to_dict(
                orient="records"
            )
        )

        raise ValueError(
            "Há conexões GTFS com duração negativa: "
            f"{sample}"
        )

    connections[
        "from_time_interpolated"
    ] = connections[
        "time_interpolated"
    ].astype(
        bool
    )
    connections[
        "from_time_interpolation_method"
    ] = connections[
        "time_interpolation_method"
    ].astype(
        "string"
    )
    connections[
        "to_time_interpolated"
    ] = connections[
        "to_time_interpolated"
    ].fillna(
        False
    ).astype(
        bool
    )
    connections[
        "to_time_interpolation_method"
    ] = connections[
        "to_time_interpolation_method"
    ].astype(
        "string"
    )
    connections[
        "uses_interpolated_time"
    ] = (
        connections[
            "from_time_interpolated"
        ]
        | connections[
            "to_time_interpolated"
        ]
    )

    if "shape_position_m" in connections.columns:
        connections[
            "from_shape_position_m"
        ] = pd.to_numeric(
            connections[
                "shape_position_m"
            ],
            errors="coerce",
        )
        connections[
            "to_shape_position_m"
        ] = pd.to_numeric(
            connections[
                "to_shape_position_m"
            ],
            errors="coerce",
        )

        shape_distance = (
            connections[
                "to_shape_position_m"
            ]
            - connections[
                "from_shape_position_m"
            ]
        )

        connections[
            "shape_segment_distance_m"
        ] = shape_distance.where(
            shape_distance
            >= 0
        )
    else:
        connections[
            "from_shape_position_m"
        ] = pd.NA
        connections[
            "to_shape_position_m"
        ] = pd.NA
        connections[
            "shape_segment_distance_m"
        ] = pd.NA

    connections[
        "connection_id"
    ] = (
        connections[
            "trip_id"
        ].astype(
            "string"
        )
        + ":"
        + connections[
            "from_stop_sequence"
        ].astype(
            "string"
        )
        + ":"
        + connections[
            "to_stop_sequence"
        ].astype(
            "string"
        )
    )

    columns = [
        "connection_id",
        "route_id",
        "service_id",
        "trip_id",
    ]

    if "shape_id" in connections.columns:
        columns.append(
            "shape_id"
        )

    columns.extend(
        [
            "from_stop_id",
            "to_stop_id",
            "from_stop_sequence",
            "to_stop_sequence",
            "departure_seconds",
            "arrival_seconds",
            "in_vehicle_time_s",
            "from_time_interpolated",
            "to_time_interpolated",
            "uses_interpolated_time",
            "from_time_interpolation_method",
            "to_time_interpolation_method",
            "from_shape_position_m",
            "to_shape_position_m",
            "shape_segment_distance_m",
        ]
    )

    return (
        connections[
            columns
        ]
        .sort_values(
            [
                "departure_seconds",
                "trip_id",
                "from_stop_sequence",
            ]
        )
        .reset_index(
            drop=True
        )
    )


def _build_topology(
    connections: pd.DataFrame,
) -> pd.DataFrame:
    """Resume as ligações físicas recorrentes entre paradas por rota"""

    topology = (
        connections
        .groupby(
            [
                "route_id",
                "from_stop_id",
                "to_stop_id",
            ],
            as_index=False,
        )
        .agg(
            n_trips=(
                "trip_id",
                "nunique",
            ),
            min_in_vehicle_time_s=(
                "in_vehicle_time_s",
                "min",
            ),
            median_in_vehicle_time_s=(
                "in_vehicle_time_s",
                "median",
            ),
            max_in_vehicle_time_s=(
                "in_vehicle_time_s",
                "max",
            ),
        )
    )

    return topology


def _build_service_day_profile(
    *,
    trips: pd.DataFrame,
    service_dates: pd.DataFrame,
) -> pd.DataFrame:
    """Calcula o número de viagens programadas em cada data do feed"""

    required = {
        "service_id",
        "service_date",
    }

    missing = (
        required
        - set(
            service_dates.columns
        )
    )

    if missing:
        raise ValueError(
            "service_dates_processed.parquet não possui: "
            f"{sorted(missing)}"
        )

    trips_by_service = (
        trips
        .groupby(
            "service_id",
            as_index=False,
        )
        .agg(
            n_trips=(
                "trip_id",
                "nunique",
            )
        )
    )

    profile = service_dates.merge(
        trips_by_service,
        on="service_id",
        how="left",
        validate="many_to_one",
    )

    profile[
        "n_trips"
    ] = profile[
        "n_trips"
    ].fillna(
        0
    ).astype(
        int
    )

    daily = (
        profile
        .groupby(
            "service_date",
            as_index=False,
        )
        .agg(
            n_active_service_ids=(
                "service_id",
                "nunique",
            ),
            n_scheduled_trips=(
                "n_trips",
                "sum",
            ),
        )
        .sort_values(
            [
                "n_scheduled_trips",
                "service_date",
            ],
            ascending=[
                False,
                True,
            ],
        )
        .reset_index(
            drop=True
        )
    )

    weekday_labels = {
        0: "segunda-feira",
        1: "terça-feira",
        2: "quarta-feira",
        3: "quinta-feira",
        4: "sexta-feira",
        5: "sábado",
        6: "domingo",
    }

    daily[
        "weekday"
    ] = (
        pd.to_datetime(
            daily[
                "service_date"
            ]
        )
        .dt.weekday
        .map(
            weekday_labels
        )
    )

    return daily


def _build_routing_quality_filter(
    quality: pd.DataFrame,
    *,
    quality_config: dict,
) -> pd.DataFrame:
    """Classifica viagens aptas ao roteamento sem apagar o diagnóstico completo"""

    result = quality.copy()

    result[
        "routing_excluded_missing_temporal_summary"
    ] = False
    result[
        "routing_excluded_nonpositive_duration"
    ] = False
    result[
        "routing_excluded_infeasible_regularization"
    ] = False
    result[
        "routing_excluded_implied_speed"
    ] = False

    if bool(
        quality_config.get(
            "exclude_missing_temporal_summary",
            True,
        )
    ):
        result[
            "routing_excluded_missing_temporal_summary"
        ] = (
            result[
                "missing_stop_time_summary"
            ]
            | result[
                "missing_connection_summary"
            ]
        )

    if bool(
        quality_config.get(
            "exclude_nonpositive_duration",
            True,
        )
    ):
        result[
            "routing_excluded_nonpositive_duration"
        ] = result[
            "nonpositive_scheduled_duration"
        ]

    if bool(
        quality_config.get(
            "exclude_infeasible_regularization",
            True,
        )
    ):
        result[
            "routing_excluded_infeasible_regularization"
        ] = result[
            "infeasible_temporal_regularization"
        ]

    max_speed = quality_config.get(
        "max_implied_shape_speed_kmh"
    )

    if max_speed is not None:
        max_speed_value = float(
            max_speed
        )

        if max_speed_value <= 0:
            raise ValueError(
                "max_implied_shape_speed_kmh precisa ser maior que zero"
            )

        result[
            "routing_excluded_implied_speed"
        ] = (
            result[
                "implied_shape_speed_kmh"
            ]
            .notna()
            & (
                result[
                    "implied_shape_speed_kmh"
                ]
                > max_speed_value
            )
        )

    reason_columns = [
        "routing_excluded_missing_temporal_summary",
        "routing_excluded_nonpositive_duration",
        "routing_excluded_infeasible_regularization",
        "routing_excluded_implied_speed",
    ]

    result[
        "routable_for_transit"
    ] = ~result[
        reason_columns
    ].any(
        axis=1
    )

    labels = {
        "routing_excluded_missing_temporal_summary": "missing_temporal_summary",
        "routing_excluded_nonpositive_duration": "nonpositive_duration",
        "routing_excluded_infeasible_regularization": "infeasible_regularization",
        "routing_excluded_implied_speed": "implied_speed_above_limit",
    }

    def build_reason(
        row,
    ) -> str:
        """Resume os motivos de exclusão da viagem"""

        reasons = [
            label
            for column, label
            in labels.items()
            if bool(
                row[
                    column
                ]
            )
        ]

        return (
            "ok"
            if not reasons
            else "|".join(
                reasons
            )
        )

    result[
        "routing_quality_status"
    ] = result.apply(
        build_reason,
        axis=1,
    )

    return result


def build_transit_network() -> dict:
    """Prepara conexões GTFS e associação das paradas à rede de caminhada"""

    config = _load_config()

    gtfs_config = config[
        "transit"
    ][
        "gtfs"
    ]
    network_config = config[
        "transit"
    ][
        "network"
    ]

    data_dir = (
        PROJECT_ROOT
        / gtfs_config[
            "data_dir"
        ]
    )

    stops, trips, stop_times, service_dates = (
        _load_processed_gtfs(
            data_dir
        )
    )

    walk_speed_m_s = float(
        network_config[
            "walk_speed_m_s"
        ]
    )
    routing_config = config[
        "transit"
    ][
        "routing"
    ]
    max_access_walk_m = float(
        routing_config[
            "max_access_walk_m"
        ]
    )
    service_date_strategy = str(
        network_config[
            "service_date_strategy"
        ]
    )

    if service_date_strategy != "max_scheduled_trips":
        raise ValueError(
            "service_date_strategy ainda suporta somente "
            "'max_scheduled_trips'"
        )

    walk_graph = load_mode_graphs(
        config=config,
        project_root=PROJECT_ROOT,
        modes=[
            "walk",
        ],
    )[
        "walk"
    ]

    connected_stops, connectors = (
        _connect_stops_to_walk_network(
            stops,
            walk_graph,
            walk_speed_m_s=walk_speed_m_s,
        )
    )

    connections = _build_scheduled_connections(
        trips=trips,
        stop_times=stop_times,
    )

    shapes_path = (
        data_dir
        / "shapes_processed.gpkg"
    )
    shapes = (
        gpd.read_file(
            shapes_path,
            layer="shapes_processed",
            engine="pyogrio",
        )
        if shapes_path.exists()
        else None
    )

    trip_quality = build_trip_temporal_quality(
        trips=trips,
        stop_times=stop_times,
        connections=connections,
        shapes=shapes,
    )

    quality_config = routing_config.get(
        "quality_filter",
        {}
    )
    trip_quality = _build_routing_quality_filter(
        trip_quality,
        quality_config=quality_config,
    )

    routable_trip_ids = set(
        trip_quality.loc[
            trip_quality[
                "routable_for_transit"
            ],
            "trip_id",
        ].astype(
            str
        )
    )

    routable_connections = (
        connections.loc[
            connections[
                "trip_id"
            ]
            .astype(
                str
            )
            .isin(
                routable_trip_ids
            )
        ]
        .copy()
        .reset_index(
            drop=True
        )
    )

    topology = _build_topology(
        routable_connections
    )

    routable_trips = trips.loc[
        trips[
            "trip_id"
        ]
        .astype(
            str
        )
        .isin(
            routable_trip_ids
        )
    ].copy()

    service_profile = _build_service_day_profile(
        trips=routable_trips,
        service_dates=service_dates,
    )

    if service_profile.empty:
        raise ValueError(
            "O perfil diário de serviço ficou vazio"
        )

    representative = service_profile.iloc[
        0
    ]

    stops_walk_path = (
        data_dir
        / network_config[
            "stops_walk_file"
        ]
    )
    connectors_path = (
        data_dir
        / network_config[
            "stop_connectors_file"
        ]
    )
    connections_path = (
        data_dir
        / network_config[
            "connections_file"
        ]
    )
    routable_connections_path = (
        data_dir
        / network_config[
            "routable_connections_file"
        ]
    )
    trip_quality_path = (
        data_dir
        / network_config[
            "trip_quality_file"
        ]
    )
    topology_path = (
        data_dir
        / network_config[
            "topology_file"
        ]
    )
    service_profile_path = (
        data_dir
        / network_config[
            "service_day_profile_file"
        ]
    )
    summary_path = (
        data_dir
        / network_config[
            "summary_file"
        ]
    )

    _replace_gpkg(
        connected_stops,
        stops_walk_path,
        layer="stops_walk_connected_processed",
    )
    connectors.to_parquet(
        connectors_path,
        index=False,
    )
    connections.to_parquet(
        connections_path,
        index=False,
    )
    routable_connections.to_parquet(
        routable_connections_path,
        index=False,
    )
    trip_quality.to_csv(
        trip_quality_path,
        index=False,
        encoding="utf-8",
    )
    topology.to_parquet(
        topology_path,
        index=False,
    )
    service_profile.to_csv(
        service_profile_path,
        index=False,
        encoding="utf-8",
    )

    connector_distances = connected_stops[
        "walk_connector_distance_m"
    ]
    connector_times = connected_stops[
        "walk_connector_time_s"
    ]

    summary = {
        "n_stops_connected": int(
            len(
                connected_stops
            )
        ),
        "n_walk_nodes_used": int(
            connected_stops[
                "node_walk"
            ].nunique()
        ),
        "walk_speed_m_s": walk_speed_m_s,
        "connector_distance_mean_m": float(
            connector_distances.mean()
        ),
        "connector_distance_median_m": float(
            connector_distances.median()
        ),
        "connector_distance_p95_m": float(
            connector_distances.quantile(
                0.95
            )
        ),
        "connector_distance_max_m": float(
            connector_distances.max()
        ),
        "connector_time_mean_s": float(
            connector_times.mean()
        ),
        "connector_time_median_s": float(
            connector_times.median()
        ),
        "connector_time_p95_s": float(
            connector_times.quantile(
                0.95
            )
        ),
        "connector_time_max_s": float(
            connector_times.max()
        ),
        "connector_access_limit_m": max_access_walk_m,
        "n_connectors_above_access_limit": int(
            (
                connector_distances
                > max_access_walk_m
            ).sum()
        ),
        "n_scheduled_connections": int(
            len(
                connections
            )
        ),
        "n_routable_connections": int(
            len(
                routable_connections
            )
        ),
        "n_total_trips_quality": int(
            len(
                trip_quality
            )
        ),
        "n_routable_trips": int(
            trip_quality[
                "routable_for_transit"
            ].sum()
        ),
        "n_excluded_trips": int(
            (
                ~trip_quality[
                    "routable_for_transit"
                ]
            ).sum()
        ),
        "n_excluded_missing_temporal_summary": int(
            trip_quality[
                "routing_excluded_missing_temporal_summary"
            ].sum()
        ),
        "n_excluded_nonpositive_duration": int(
            trip_quality[
                "routing_excluded_nonpositive_duration"
            ].sum()
        ),
        "n_excluded_infeasible_regularization": int(
            trip_quality[
                "routing_excluded_infeasible_regularization"
            ].sum()
        ),
        "n_excluded_implied_speed": int(
            trip_quality[
                "routing_excluded_implied_speed"
            ].sum()
        ),
        "max_implied_shape_speed_kmh": (
            float(
                quality_config[
                    "max_implied_shape_speed_kmh"
                ]
            )
            if quality_config.get(
                "max_implied_shape_speed_kmh"
            )
            is not None
            else None
        ),
        "n_unique_stop_pairs": int(
            routable_connections[
                [
                    "from_stop_id",
                    "to_stop_id",
                ]
            ]
            .drop_duplicates()
            .shape[
                0
            ]
        ),
        "n_route_stop_links": int(
            len(
                topology
            )
        ),
        "connections_with_interpolated_time": int(
            connections[
                "uses_interpolated_time"
            ].sum()
        ),
        "zero_duration_connections": int(
            (
                connections[
                    "in_vehicle_time_s"
                ]
                == 0
            ).sum()
        ),
        "routable_zero_duration_connections": int(
            (
                routable_connections[
                    "in_vehicle_time_s"
                ]
                == 0
            ).sum()
        ),
        "connection_time_median_s": float(
            routable_connections[
                "in_vehicle_time_s"
            ].median()
        ),
        "connection_time_p95_s": float(
            routable_connections[
                "in_vehicle_time_s"
            ].quantile(
                0.95
            )
        ),
        "representative_service_date": (
            pd.Timestamp(
                representative[
                    "service_date"
                ]
            )
            .date()
            .isoformat()
        ),
        "representative_weekday": str(
            representative[
                "weekday"
            ]
        ),
        "representative_scheduled_trips": int(
            representative[
                "n_scheduled_trips"
            ]
        ),
        "service_date_strategy": service_date_strategy,
    }

    pd.DataFrame(
        [
            summary
        ]
    ).to_csv(
        summary_path,
        index=False,
        encoding="utf-8",
    )

    return summary


def main() -> None:
    """Executa a preparação da rede temporal de ônibus"""

    print(
        "\n"
        + "="
        * 72
    )
    print(
        "PREPARAÇÃO DA REDE TEMPORAL DE ÔNIBUS"
    )
    print(
        "="
        * 72
    )

    summary = build_transit_network()

    print(
        "\nConexão das paradas à rede de caminhada"
    )
    print(
        "  Paradas conectadas: "
        f"{_format_int_pt(summary['n_stops_connected'])} unidades"
    )
    print(
        "  Nós distintos da rede de caminhada utilizados: "
        f"{_format_int_pt(summary['n_walk_nodes_used'])} nós"
    )
    print(
        "  Velocidade de caminhada adotada: "
        f"{_format_float_pt(summary['walk_speed_m_s'], decimals=2)} m/s"
    )
    print(
        "  Distância do conector — média: "
        f"{_format_float_pt(summary['connector_distance_mean_m'])} m"
    )
    print(
        "  Distância do conector — mediana: "
        f"{_format_float_pt(summary['connector_distance_median_m'])} m"
    )
    print(
        "  Distância do conector — percentil 95: "
        f"{_format_float_pt(summary['connector_distance_p95_m'])} m"
    )
    print(
        "  Distância do conector — máxima: "
        f"{_format_float_pt(summary['connector_distance_max_m'])} m"
    )
    print(
        "  Tempo do conector — média: "
        f"{_format_float_pt(summary['connector_time_mean_s'])} s"
    )
    print(
        "  Tempo do conector — mediana: "
        f"{_format_float_pt(summary['connector_time_median_s'])} s"
    )
    print(
        "  Tempo do conector — percentil 95: "
        f"{_format_float_pt(summary['connector_time_p95_s'])} s"
    )
    print(
        "  Tempo do conector — máximo: "
        f"{_format_float_pt(summary['connector_time_max_s'])} s"
    )
    print(
        "  Paradas cujo conector excede o limite de acesso "
        f"({_format_float_pt(summary['connector_access_limit_m'])} m): "
        f"{_format_int_pt(summary['n_connectors_above_access_limit'])} paradas "
        f"({_format_percentage_pt(summary['n_connectors_above_access_limit'], summary['n_stops_connected'])})"
    )

    print(
        "\nConexões temporais entre paradas"
    )
    print(
        "  Conexões programadas no feed processado: "
        f"{_format_int_pt(summary['n_scheduled_connections'])} conexões"
    )
    print(
        "  Conexões aptas ao roteamento: "
        f"{_format_int_pt(summary['n_routable_connections'])} conexões "
        f"({_format_percentage_pt(summary['n_routable_connections'], summary['n_scheduled_connections'])})"
    )
    print(
        "  Pares direcionais de paradas distintos: "
        f"{_format_int_pt(summary['n_unique_stop_pairs'])} pares"
    )
    print(
        "  Ligações rota × par de paradas: "
        f"{_format_int_pt(summary['n_route_stop_links'])} ligações"
    )
    print(
        "  Conexões que usam pelo menos um horário interpolado: "
        f"{_format_int_pt(summary['connections_with_interpolated_time'])} "
        "conexões "
        f"({_format_percentage_pt(summary['connections_with_interpolated_time'], summary['n_scheduled_connections'])})"
    )
    print(
        "  Conexões com duração igual a zero no conjunto completo: "
        f"{_format_int_pt(summary['zero_duration_connections'])} conexões "
        f"({_format_percentage_pt(summary['zero_duration_connections'], summary['n_scheduled_connections'])})"
    )
    print(
        "  Conexões com duração igual a zero no conjunto roteável: "
        f"{_format_int_pt(summary['routable_zero_duration_connections'])} conexões "
        f"({_format_percentage_pt(summary['routable_zero_duration_connections'], summary['n_routable_connections'])})"
    )
    print(
        "  Duração entre paradas — mediana: "
        f"{_format_float_pt(summary['connection_time_median_s'])} s"
    )
    print(
        "  Duração entre paradas — percentil 95: "
        f"{_format_float_pt(summary['connection_time_p95_s'])} s"
    )

    print(
        "\nFiltro de qualidade para roteamento"
    )
    print(
        "  Viagens avaliadas: "
        f"{_format_int_pt(summary['n_total_trips_quality'])} viagens"
    )
    print(
        "  Viagens aptas ao roteamento: "
        f"{_format_int_pt(summary['n_routable_trips'])} viagens "
        f"({_format_percentage_pt(summary['n_routable_trips'], summary['n_total_trips_quality'])})"
    )
    print(
        "  Viagens excluídas por pelo menos um critério: "
        f"{_format_int_pt(summary['n_excluded_trips'])} viagens "
        f"({_format_percentage_pt(summary['n_excluded_trips'], summary['n_total_trips_quality'])})"
    )
    print(
        "    sem resumo temporal: "
        f"{_format_int_pt(summary['n_excluded_missing_temporal_summary'])} viagens"
    )
    print(
        "    duração não positiva: "
        f"{_format_int_pt(summary['n_excluded_nonpositive_duration'])} viagens"
    )
    print(
        "    regularização temporal inviável: "
        f"{_format_int_pt(summary['n_excluded_infeasible_regularization'])} viagens"
    )

    if summary[
        "max_implied_shape_speed_kmh"
    ] is not None:
        print(
            "    velocidade implícita acima do limite técnico "
            f"({_format_float_pt(summary['max_implied_shape_speed_kmh'])} km/h): "
            f"{_format_int_pt(summary['n_excluded_implied_speed'])} viagens"
        )

    print(
        "\nData de serviço de referência"
    )
    print(
        "  Estratégia: maior número de viagens programadas no feed"
    )
    print(
        "  Data: "
        f"{_format_date_pt(summary['representative_service_date'])}"
    )
    print(
        "  Dia da semana: "
        f"{summary['representative_weekday']}"
    )
    print(
        "  Viagens roteáveis programadas nessa data: "
        f"{_format_int_pt(summary['representative_scheduled_trips'])} viagens"
    )

    from src.reporting.exportPilotMetadata import (
        export_pilot_metadata,
    )

    metadata_paths = export_pilot_metadata(
        project_root=PROJECT_ROOT
    )

    print(
        "\nDocumentação do piloto"
    )
    print(
        "  Metadados XLSX: "
        f"{metadata_paths['xlsx']}"
    )
    print(
        "  Metadados HTML: "
        f"{metadata_paths['html']}"
    )


if __name__ == "__main__":
    main()
