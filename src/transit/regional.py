"""Carregamento dos produtos de transporte coletivo do cache regional."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import pandas as pd

from src.core.config import project_path


@dataclass(frozen=True, slots=True)
class RegionalTransitCache:
    """Dados regionais necessários ao roteamento temporal GTFS."""

    directory: Path
    stops: gpd.GeoDataFrame
    connectors: pd.DataFrame
    connections: pd.DataFrame
    physical_edges: gpd.GeoDataFrame
    connection_to_physical_edge: pd.DataFrame
    service_dates: pd.DataFrame


def load_regional_transit_cache(
    config: dict,
    region_name: str,
) -> RegionalTransitCache:
    """Carrega os produtos GTFS regionais produzidos por prepare_region.py."""

    directory = (
        project_path(config["paths"]["regional_cache"])
        / region_name
    )

    files = {
        "stops": directory / "transit_stops.gpkg",
        "connectors": directory / "transit_connectors.parquet",
        "connections": directory / "transit_connections.parquet",
        "physical_edges": directory / "transit_physical_edges.gpkg",
        "mapping": directory / "transit_connection_to_physical_edge.parquet",
        "service_dates": directory / "transit_service_dates.parquet",
    }

    for path in files.values():
        if not path.exists():
            raise FileNotFoundError(
                f"Arquivo regional de transporte não encontrado: {path}. "
                "Execute scripts/prepare_region.py primeiro."
            )

    return RegionalTransitCache(
        directory=directory,
        stops=gpd.read_file(
            files["stops"],
            engine="pyogrio",
        ),
        connectors=pd.read_parquet(
            files["connectors"],
        ),
        connections=pd.read_parquet(
            files["connections"],
        ),
        physical_edges=gpd.read_file(
            files["physical_edges"],
            engine="pyogrio",
        ),
        connection_to_physical_edge=pd.read_parquet(
            files["mapping"],
        ),
        service_dates=pd.read_parquet(
            files["service_dates"],
        ),
    )


def select_representative_service_date(
    transit: RegionalTransitCache,
) -> pd.Timestamp:
    """Seleciona a data com maior número de conexões GTFS programadas."""

    if transit.connections.empty:
        raise ValueError(
            "Não existem conexões GTFS no cache regional."
        )

    if transit.service_dates.empty:
        raise ValueError(
            "Não existem datas de serviço GTFS no cache regional."
        )

    connection_counts = (
        transit.connections[
            "service_id"
        ]
        .astype(str)
        .value_counts()
    )

    dates = transit.service_dates[
        ["service_id", "service_date"]
    ].copy()

    dates["service_id"] = (
        dates["service_id"].astype(str)
    )
    dates["service_date"] = pd.to_datetime(
        dates["service_date"]
    ).dt.normalize()

    dates["n_connections"] = (
        dates["service_id"]
        .map(connection_counts)
        .fillna(0)
        .astype("int64")
    )

    profile = (
        dates.groupby(
            "service_date",
            as_index=True,
        )["n_connections"]
        .sum()
        .sort_values(
            ascending=False,
        )
    )

    if profile.empty:
        raise ValueError(
            "Não foi possível selecionar uma data de serviço representativa."
        )

    return pd.Timestamp(profile.index[0]).normalize()
