"""Catálogo de ruas para seleção na interface do EtPilot.

Este módulo concentra toda a lógica de leitura e normalização de nomes de vias
vindos do OSM. A GUI usa essas funções apenas para listar ruas válidas dentro da
região escolhida; a análise continua independente da interface.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Mapping
from pathlib import Path

import geopandas as gpd
import networkx as nx
import osmnx as ox

from src.core.config import project_path
from src.network.multimodal import graph_path_for_mode
from src.spatial.area_loader import load_study_area


def normalize_street_names(value) -> list[str]:
    """Converte diferentes representações OSM de `name` em lista de textos.

    OSMnx pode entregar o atributo name como string, lista real ou string que
    representa uma lista após serialização em GraphML. Esta função trata os
    três casos e remove nomes vazios/duplicados.
    """

    if value is None:
        return []

    if isinstance(
        value,
        (list, tuple, set),
    ):
        raw_values = list(
            value
        )
    elif isinstance(
        value,
        str,
    ):
        text = value.strip()

        if not text:
            return []

        raw_values = [
            text
        ]

        if (
            text.startswith("[")
            and text.endswith("]")
        ):
            try:
                parsed = ast.literal_eval(
                    text
                )
            except (
                ValueError,
                SyntaxError,
            ):
                parsed = None

            if isinstance(
                parsed,
                (list, tuple, set),
            ):
                raw_values = list(
                    parsed
                )
    else:
        raw_values = [
            value
        ]

    result = []

    for item in raw_values:
        name = str(
            item
        ).strip()

        if (
            name
            and name.lower()
            not in {
                "none",
                "nan",
                "<na>",
            }
            and name not in result
        ):
            result.append(
                name
            )

    return result


def list_street_names_from_graphs(
    graphs: Mapping[str, nx.MultiDiGraph],
) -> list[str]:
    """Retorna nomes únicos de ruas presentes nas redes multimodais."""

    names: set[str] = set()

    for graph in graphs.values():
        for _, _, _, data in graph.edges(
            keys=True,
            data=True,
        ):
            for name in normalize_street_names(
                data.get("name")
            ):
                names.add(
                    name
                )

    return sorted(
        names,
        key=str.casefold,
    )


def load_region_street_names(
    config: Mapping,
    region_name: str,
) -> list[str]:
    """Lista ruas da região selecionada para uso na GUI.

    Estratégia:
    1. tenta usar o cache regional já preparado;
    2. se o cache ainda não existir, usa a rede urbana de carro e filtra
       espacialmente as arestas pela StudyArea selecionada.

    O fallback evita exigir que o usuário execute manualmente a preparação da
    região antes de conseguir escolher uma rua na interface.
    """

    cache_dir = (
        project_path(
            config["paths"]["regional_cache"]
        )
        / region_name
    )

    cached_graphs: dict[
        str,
        nx.MultiDiGraph,
    ] = {}

    for mode in (
        "car",
        "walk",
        "bike",
    ):
        graph_path = (
            cache_dir
            / f"graph_{mode}.graphml"
        )

        if graph_path.exists():
            cached_graphs[
                mode
            ] = ox.load_graphml(
                graph_path
            )

    if cached_graphs:
        return list_street_names_from_graphs(
            cached_graphs
        )

    # Fallback: usa a rede municipal de carro, que é suficiente para montar o
    # catálogo de nomes de vias sem carregar três grafos completos.
    city_graph_path = graph_path_for_mode(
        config,
        "car",
    )

    if not city_graph_path.exists():
        raise FileNotFoundError(
            "Nenhuma rede regional ou municipal de carro foi encontrada. "
            "Prepare as redes OSM antes de carregar as ruas."
        )

    graph = ox.load_graphml(
        city_graph_path
    )
    study_area = load_study_area(
        region_name,
        config=dict(config),
    )

    _, edges = ox.graph_to_gdfs(
        graph,
        nodes=True,
        edges=True,
    )

    if edges.crs != study_area.crs:
        edges = edges.to_crs(
            study_area.crs
        )

    regional_edges = edges.loc[
        edges.geometry.intersects(
            study_area.geometry
        )
    ].copy()

    names: set[str] = set()

    if "name" in regional_edges.columns:
        for value in regional_edges[
            "name"
        ]:
            names.update(
                normalize_street_names(
                    value
                )
            )

    return sorted(
        names,
        key=str.casefold,
    )


def street_mask(
    data,
    *,
    street_name: str,
    name_column: str = "name",
):
    """Retorna máscara booleana indicando geometrias da rua escolhida."""

    if name_column not in data.columns:
        return [
            False
            for _ in range(
                len(data)
            )
        ]

    target = street_name.casefold()

    return [
        any(
            name.casefold()
            == target
            for name in normalize_street_names(
                value
            )
        )
        for value in data[
            name_column
        ]
    ]
