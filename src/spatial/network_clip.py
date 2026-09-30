"""Recorte de grafos multimodais para uma área de estudo.

O módulo opera somente sobre um grafo e uma StudyArea. Ele não contém regras
específicas para Centro, Norte, Sul ou Leste.
"""

from __future__ import annotations

from collections.abc import Mapping

import networkx as nx
import osmnx as ox
from shapely.geometry.base import BaseGeometry

from src.spatial.study_area import StudyArea


def clip_graph_to_study_area(
    graph: nx.MultiDiGraph,
    study_area: StudyArea,
    *,
    buffer_m: float = 0.0,
    retain_largest_component: bool = True,
) -> nx.MultiDiGraph:
    """Recorta um grafo OSM para a área de estudo.

    O buffer existe apenas para reduzir cortes artificiais na borda da rede.
    A geometria oficial da análise continua sendo a StudyArea.
    """

    _validate_graph(graph)

    projected_graph = _project_graph_if_needed(
        graph=graph,
        target_crs=study_area.crs,
    )

    clipping_geometry = _build_clipping_geometry(
        study_area.geometry,
        buffer_m=buffer_m,
    )

    _, edges = ox.graph_to_gdfs(
        projected_graph,
        nodes=True,
        edges=True,
    )

    selected_edges = edges.loc[
        edges.geometry.intersects(clipping_geometry)
    ]

    if selected_edges.empty:
        raise ValueError(
            f"Nenhuma aresta encontrada para a região '{study_area.name}'."
        )

    edge_ids = list(selected_edges.index)
    regional_graph = projected_graph.edge_subgraph(edge_ids).copy()

    if retain_largest_component:
        regional_graph = _largest_weakly_connected_component(
            regional_graph
        )

    regional_graph.graph["study_area"] = study_area.name
    regional_graph.graph["study_area_label"] = study_area.label
    regional_graph.graph["regional_buffer_m"] = float(buffer_m)

    return regional_graph


def clip_modal_graphs(
    graphs: Mapping[str, nx.MultiDiGraph],
    study_area: StudyArea,
    *,
    buffer_m: float = 0.0,
    retain_largest_component: bool = True,
) -> dict[str, nx.MultiDiGraph]:
    """Recorta um conjunto de grafos modais usando a mesma área de estudo."""

    if not graphs:
        raise ValueError("Nenhum grafo modal foi informado.")

    return {
        mode: clip_graph_to_study_area(
            graph,
            study_area,
            buffer_m=buffer_m,
            retain_largest_component=retain_largest_component,
        )
        for mode, graph in graphs.items()
    }


def _project_graph_if_needed(
    *,
    graph: nx.MultiDiGraph,
    target_crs,
) -> nx.MultiDiGraph:
    graph_crs = graph.graph.get("crs")

    if graph_crs is None:
        raise ValueError("O grafo não possui CRS definido.")

    if str(graph_crs) == str(target_crs):
        return graph.copy()

    return ox.project_graph(
        graph,
        to_crs=target_crs,
    )


def _build_clipping_geometry(
    geometry: BaseGeometry,
    *,
    buffer_m: float,
) -> BaseGeometry:
    if buffer_m < 0:
        raise ValueError("buffer_m não pode ser negativo.")

    if buffer_m == 0:
        return geometry

    return geometry.buffer(buffer_m)


def _largest_weakly_connected_component(
    graph: nx.MultiDiGraph,
) -> nx.MultiDiGraph:
    if graph.number_of_nodes() == 0:
        raise ValueError("O grafo regional não possui nós.")

    components = list(nx.weakly_connected_components(graph))

    if not components:
        raise ValueError(
            "Não foi possível identificar componentes conectados."
        )

    largest = max(components, key=len)
    return graph.subgraph(largest).copy()


def _validate_graph(graph: nx.MultiDiGraph) -> None:
    if graph.number_of_nodes() == 0:
        raise ValueError("O grafo informado não possui nós.")

    if graph.number_of_edges() == 0:
        raise ValueError("O grafo informado não possui arestas.")
