"""Utilidades para redes OSM multimodais do EtPilot.

O piloto usa três redes de roteamento derivadas do OpenStreetMap:
- car  -> network_type="drive"
- walk -> network_type="walk"
- bike -> network_type="bike"

O transporte coletivo permanece fora desta primeira etapa e deverá ser
implementado posteriormente com GTFS.

As origens e destinos são entidades espaciais independentes da rede. Para
roteamento, cada ponto recebe um nó específico por modo:
``node_car``, ``node_walk`` e ``node_bike``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

import geopandas as gpd
import osmnx as ox


MODE_TO_NETWORK_TYPE = {
    "car": "drive",
    "walk": "walk",
    "bike": "bike",
}


def graph_path_for_mode(
    config: Mapping,
    project_root: Path,
    mode: str,
) -> Path:
    """Retorna o caminho configurado para o GraphML de um modo."""

    key = f"graph_{mode}"

    try:
        relative_path = config["paths"][key]
    except KeyError as exc:
        raise KeyError(
            f"Caminho ausente no config.json: paths.{key}"
        ) from exc

    return project_root / relative_path


def download_mode_graphs(
    *,
    place: str,
    crs: str,
    network_types: Mapping[str, str],
    output_paths: Mapping[str, Path],
) -> dict[str, object]:
    """Baixa, projeta e salva uma rede OSM para cada modo."""

    graphs: dict[str, object] = {}

    for mode, network_type in network_types.items():
        if mode not in MODE_TO_NETWORK_TYPE:
            raise ValueError(
                f"Modo de rede não suportado nesta etapa: {mode}"
            )

        output_path = Path(output_paths[mode])
        output_path.parent.mkdir(parents=True, exist_ok=True)

        print(
            f"Baixando rede '{mode}' de {place} "
            f"(network_type='{network_type}')..."
        )

        graph = ox.graph_from_place(
            place,
            network_type=network_type,
        )

        graph = ox.project_graph(
            graph,
            to_crs=crs,
        )

        ox.save_graphml(
            graph,
            output_path,
        )

        print(
            f"  {mode}: {len(graph.nodes):,} nós | "
            f"{len(graph.edges):,} arestas | "
            f"CRS={graph.graph.get('crs')}"
        )

        graphs[mode] = graph

    return graphs


def load_mode_graphs(
    *,
    config: Mapping,
    project_root: Path,
    modes: list[str] | tuple[str, ...] | None = None,
) -> dict[str, object]:
    """Carrega os GraphML configurados para os modos implementados."""

    if modes is None:
        modes = list(
            config["routing"]["implemented_modes"]
        )

    graphs: dict[str, object] = {}

    for mode in modes:
        path = graph_path_for_mode(
            config=config,
            project_root=project_root,
            mode=mode,
        )

        if not path.exists():
            raise FileNotFoundError(
                f"Rede '{mode}' não encontrada: {path}. "
                "Execute notebooks/01_download_network.ipynb."
            )

        graph = ox.load_graphml(path)

        expected_crs = config["study_area"]["crs"]
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


def assign_modal_nodes(
    gdf: gpd.GeoDataFrame,
    graphs: Mapping[str, object],
    *,
    prefix: str = "node_",
) -> gpd.GeoDataFrame:
    """Associa cada geometria ao nó mais próximo de cada rede modal."""

    if gdf.empty:
        raise ValueError(
            "GeoDataFrame vazio: não há geometrias para associar à rede."
        )

    if gdf.crs is None:
        raise ValueError(
            "GeoDataFrame sem CRS: não é possível calcular nearest_nodes."
        )

    if "geometry" not in gdf.columns:
        raise ValueError(
            "GeoDataFrame não possui coluna geometry."
        )

    result = gdf.copy()

    for mode, graph in graphs.items():
        graph_crs = graph.graph.get("crs")

        if graph_crs is None:
            raise ValueError(
                f"A rede '{mode}' não possui CRS registrado."
            )

        points = result

        if str(points.crs) != str(graph_crs):
            points = result.to_crs(graph_crs)

        column = f"{prefix}{mode}"

        result[column] = ox.distance.nearest_nodes(
            graph,
            X=points.geometry.x.to_numpy(),
            Y=points.geometry.y.to_numpy(),
        )

    return result


def modal_node_columns(
    modes: list[str] | tuple[str, ...],
    *,
    prefix: str = "node_",
) -> list[str]:
    """Retorna os nomes das colunas de nós esperadas para os modos."""

    return [
        f"{prefix}{mode}"
        for mode in modes
    ]
