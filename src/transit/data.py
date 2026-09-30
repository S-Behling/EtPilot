"""Carregamento dos produtos GTFS já processados do EtPilot."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import geopandas as gpd
import pandas as pd

from src.core.config import project_path


@dataclass(frozen=True, slots=True)
class TransitData:
    """Conjunto mínimo de dados necessário para roteamento coletivo."""

    stops: gpd.GeoDataFrame
    connectors: pd.DataFrame
    connections: pd.DataFrame
    physical_edges: gpd.GeoDataFrame
    connection_to_physical_edge: pd.DataFrame
    service_dates: pd.DataFrame


def load_transit_data(config: Mapping) -> TransitData:
    """Carrega os produtos GTFS processados configurados no projeto."""

    transit_config = config["transit"]
    data_dir = project_path(transit_config["data_dir"])
    files = transit_config["files"]

    _require_directory(data_dir)

    stops = gpd.read_file(
        data_dir / files["stops_walk"],
        engine="pyogrio",
    )
    connectors = pd.read_parquet(
        data_dir / files["stop_connectors"]
    )
    connections = pd.read_parquet(
        data_dir / files["connections"]
    )
    physical_edges = gpd.read_file(
        data_dir / files["physical_edges"],
        engine="pyogrio",
    )
    connection_to_physical_edge = pd.read_parquet(
        data_dir / files["connection_to_physical_edge"]
    )
    service_dates = pd.read_parquet(
        data_dir / files["service_dates"]
    )

    _validate_columns(
        stops,
        required={"stop_id", "geometry"},
        source="stops",
    )
    _validate_columns(
        connectors,
        required={"stop_id", "node_walk"},
        source="connectors",
    )
    _validate_columns(
        connections,
        required={
            "connection_id",
            "from_stop_id",
            "to_stop_id",
            "service_id",
            "trip_id",
            "route_id",
            "departure_seconds",
            "arrival_seconds",
        },
        source="connections",
    )
    _validate_columns(
        physical_edges,
        required={"transit_physical_edge_id", "geometry"},
        source="physical_edges",
    )
    _validate_columns(
        connection_to_physical_edge,
        required={
            "connection_id",
            "transit_physical_edge_id",
        },
        source="connection_to_physical_edge",
    )
    _validate_columns(
        service_dates,
        required={"service_id", "service_date"},
        source="service_dates",
    )

    return TransitData(
        stops=stops,
        connectors=connectors,
        connections=connections,
        physical_edges=physical_edges,
        connection_to_physical_edge=connection_to_physical_edge,
        service_dates=service_dates,
    )


def _require_directory(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(
            f"Diretório GTFS não encontrado: {path}"
        )


def _validate_columns(
    data,
    *,
    required: set[str],
    source: str,
) -> None:
    missing = required - set(data.columns)

    if missing:
        raise ValueError(
            f"{source} não possui as colunas obrigatórias: "
            f"{sorted(missing)}"
        )
