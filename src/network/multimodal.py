"""Utilidades para redes OSM multimodais do EtPilot.

As redes de carro, caminhada e bicicleta são mantidas separadas. Origens e
destinos permanecem entidades espaciais independentes e recebem um nó por
modo somente depois de definido o recorte espacial da execução.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import geopandas as gpd
import networkx as nx
import osmnx as ox


SUPPORTED_MODES = ("car", "walk", "bike")


def graph_path_for_mode(
    config: Mapping,
    mode: str,
) -> Path:
    """Retorna o GraphML configurado para um modo."""

    _validate_mode(mode)

    key = f"graph_{mode}"

    try:
        relative = config["paths"][key]
    except KeyError as exc:
        raise KeyError(
            f"Caminho ausente no config.json: paths.{key}"
        ) from exc

    from src.core.config import project_path

    return project_path(relative)


def load_mode_graphs(
    config: Mapping,
    *,
    modes: tuple[str, ...] = SUPPORTED_MODES,
) -> dict[str, nx.MultiDiGraph]:
    """Carrega e reprojeta as redes modais configuradas."""

    expected_crs = config["study_area"]["crs"]
    graphs: dict[str, nx.MultiDiGraph] = {}

    for mode in modes:
        path = graph_path_for_mode(config, mode)

        if not path.exists():
            raise FileNotFoundError(
                f"Rede '{mode}' não encontrada: {path}"
            )

        graph = ox.load_graphml(path)

        graph_crs = graph.graph.get("crs")
        if graph_crs is None:
            raise ValueError(
                f"A rede '{mode}' não possui CRS registrado."
            )

        if str(graph_crs) != str(expected_crs):
            graph = ox.project_graph(
                graph,
                to_crs=expected_crs,
            )

        graphs[mode] = graph

    return graphs


def save_mode_graphs(
    graphs: Mapping[str, nx.MultiDiGraph],
    config: Mapping,
) -> None:
    """Salva redes modais usando os caminhos declarados na configuração."""

    for mode, graph in graphs.items():
        _validate_mode(mode)

        path = graph_path_for_mode(config, mode)
        path.parent.mkdir(parents=True, exist_ok=True)

        ox.save_graphml(
            graph,
            filepath=path,
        )


def assign_modal_nodes(
    data: gpd.GeoDataFrame,
    graphs: Mapping[str, nx.MultiDiGraph],
    *,
    prefix: str = "node_",
) -> gpd.GeoDataFrame:
    """Associa cada geometria ao nó mais próximo de cada rede modal."""

    _validate_points(data)

    result = data.copy()

    for mode, graph in graphs.items():
        _validate_mode(mode)

        graph_crs = graph.graph.get("crs")
        if graph_crs is None:
            raise ValueError(
                f"A rede '{mode}' não possui CRS registrado."
            )

        points = (
            result
            if str(result.crs) == str(graph_crs)
            else result.to_crs(graph_crs)
        )

        result[f"{prefix}{mode}"] = ox.distance.nearest_nodes(
            graph,
            X=points.geometry.x.to_numpy(),
            Y=points.geometry.y.to_numpy(),
        )

    return result


def _validate_mode(mode: str) -> None:
    if mode not in SUPPORTED_MODES:
        raise ValueError(
            f"Modo não suportado: {mode!r}. "
            f"Use um de {SUPPORTED_MODES}."
        )


def _validate_points(data: gpd.GeoDataFrame) -> None:
    if data.empty:
        raise ValueError(
            "GeoDataFrame vazio: não há pontos para associar à rede."
        )

    if data.crs is None:
        raise ValueError(
            "GeoDataFrame sem CRS: nearest_nodes não pode ser calculado."
        )

    if data.geometry.isna().any():
        raise ValueError(
            "Existem geometrias ausentes nos pontos de O/D."
        )

    invalid_types = ~data.geometry.geom_type.eq("Point")
    if invalid_types.any():
        raise ValueError(
            "assign_modal_nodes requer geometrias do tipo Point."
        )
