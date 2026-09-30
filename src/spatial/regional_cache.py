"""Carregamento do cache regional preparado para uma execução do piloto."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from collections.abc import Mapping

import geopandas as gpd
import networkx as nx
import osmnx as ox

from src.core.config import project_path


@dataclass(frozen=True, slots=True)
class RegionalCache:
    """Entradas espaciais prontas para simulação e roteamento."""

    region_name: str
    directory: Path
    origins: gpd.GeoDataFrame
    destinations: gpd.GeoDataFrame
    graphs: dict[str, nx.MultiDiGraph]


def load_regional_cache(
    config: Mapping,
    region_name: str,
) -> RegionalCache:
    """Carrega origens, destinos e grafos regionais previamente preparados."""

    directory = (
        project_path(config["paths"]["regional_cache"])
        / region_name
    )

    if not directory.exists():
        raise FileNotFoundError(
            f"Cache regional não encontrado: {directory}. "
            "Execute scripts/prepare_region.py primeiro."
        )

    origins_path = directory / "origins.gpkg"
    destinations_path = directory / "destinations.gpkg"

    _require_file(origins_path)
    _require_file(destinations_path)

    origins = gpd.read_file(
        origins_path,
        engine="pyogrio",
    )
    destinations = gpd.read_file(
        destinations_path,
        engine="pyogrio",
    )

    graphs: dict[str, nx.MultiDiGraph] = {}

    for mode in ("walk", "bike", "car"):
        path = directory / f"graph_{mode}.graphml"
        _require_file(path)
        graphs[mode] = ox.load_graphml(path)

    return RegionalCache(
        region_name=region_name,
        directory=directory,
        origins=origins,
        destinations=destinations,
        graphs=graphs,
    )


def _require_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(
            f"Arquivo esperado no cache regional não encontrado: {path}"
        )
