"""Visualizações de diagnóstico do estado atual do pipeline EtPilot.

A cada avanço relevante do projeto, este módulo deve receber uma nova função
de visualização correspondente ao novo estado dos dados. As funções retornam
figura e eixo para permitir composição, testes e salvamento externo.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

import geopandas as gpd
import matplotlib.pyplot as plt
import networkx as nx
import osmnx as ox

from src.spatial.regional_data import RegionalData
from src.spatial.study_area import StudyArea
from src.spatial.transit_filter import RegionalTransitData



def apply_study_area_view(
    ax,
    study_area: StudyArea | None,
    *,
    margin_ratio: float = 0.03,
):
    """Aplica limite e contorno da região sem alterar os dados plotados."""

    if study_area is None:
        return ax

    boundary = gpd.GeoSeries(
        [study_area.geometry],
        crs=study_area.crs,
    ).boundary

    boundary.plot(
        ax=ax,
        linewidth=1.0,
    )

    minx, miny, maxx, maxy = study_area.geometry.bounds
    width = max(maxx - minx, 1.0)
    height = max(maxy - miny, 1.0)

    margin_x = width * margin_ratio
    margin_y = height * margin_ratio

    ax.set_xlim(
        minx - margin_x,
        maxx + margin_x,
    )
    ax.set_ylim(
        miny - margin_y,
        maxy + margin_y,
    )

    return ax

def plot_study_area(
    study_area: StudyArea,
    *,
    title: str | None = None,
):
    """Plota somente o limite da área de estudo."""

    fig, ax = plt.subplots()
    boundary = gpd.GeoSeries(
        [study_area.geometry],
        crs=study_area.crs,
    ).boundary

    boundary.plot(ax=ax)

    ax.set_title(
        title or f"Área de estudo — {study_area.label}"
    )
    ax.set_axis_off()

    return fig, ax


def plot_regional_points(
    *,
    study_area: StudyArea,
    origins: gpd.GeoDataFrame,
    destinations: gpd.GeoDataFrame,
    title: str | None = None,
):
    """Plota origens e destinos atualmente selecionados."""

    fig, ax = plt.subplots()

    gpd.GeoSeries(
        [study_area.geometry],
        crs=study_area.crs,
    ).boundary.plot(ax=ax)

    if not origins.empty:
        origins.to_crs(study_area.crs).plot(
            ax=ax,
            marker="o",
            markersize=8,
            label="Origens",
        )

    if not destinations.empty:
        destinations.to_crs(study_area.crs).plot(
            ax=ax,
            marker="^",
            markersize=8,
            label="Destinos",
        )

    ax.set_title(
        title or f"Origens e destinos — {study_area.label}"
    )
    ax.set_axis_off()
    ax.legend()

    return fig, ax


def plot_regional_networks(
    *,
    study_area: StudyArea,
    graphs: Mapping[str, nx.MultiDiGraph],
    title: str | None = None,
):
    """Plota as redes modais regionais disponíveis."""

    fig, ax = plt.subplots()

    gpd.GeoSeries(
        [study_area.geometry],
        crs=study_area.crs,
    ).boundary.plot(ax=ax)

    for mode, graph in graphs.items():
        _, edges = ox.graph_to_gdfs(
            graph,
            nodes=True,
            edges=True,
        )
        edges.to_crs(study_area.crs).plot(
            ax=ax,
            linewidth=0.7,
            label=mode,
        )

    ax.set_title(
        title or f"Redes modais — {study_area.label}"
    )
    ax.set_axis_off()
    ax.legend()

    return fig, ax


def plot_regional_data(
    data: RegionalData,
    *,
    title: str | None = None,
):
    """Plota área, origens, destinos e redes do estado regional integrado."""

    fig, ax = plot_regional_networks(
        study_area=data.study_area,
        graphs=data.graphs,
        title=title or f"Estado regional — {data.study_area.label}",
    )

    if not data.origins.empty:
        data.origins.to_crs(data.study_area.crs).plot(
            ax=ax,
            marker="o",
            markersize=8,
            label="Origens",
        )

    if not data.destinations.empty:
        data.destinations.to_crs(data.study_area.crs).plot(
            ax=ax,
            marker="^",
            markersize=8,
            label="Destinos",
        )

    ax.legend()
    return fig, ax


def plot_transit_state(
    *,
    study_area: StudyArea,
    transit: RegionalTransitData,
    title: str | None = None,
):
    """Plota paradas e arestas físicas do transporte coletivo regional."""

    fig, ax = plt.subplots()

    gpd.GeoSeries(
        [study_area.geometry],
        crs=study_area.crs,
    ).boundary.plot(ax=ax)

    if not transit.physical_edges.empty:
        transit.physical_edges.to_crs(
            study_area.crs
        ).plot(
            ax=ax,
            linewidth=0.8,
            label="Transit",
        )

    if not transit.stops.empty:
        transit.stops.to_crs(
            study_area.crs
        ).plot(
            ax=ax,
            marker="o",
            markersize=5,
            label="Paradas",
        )

    ax.set_title(
        title or f"Transporte coletivo — {study_area.label}"
    )
    ax.set_axis_off()
    ax.legend()

    return fig, ax



def plot_modal_snapping(
    *,
    study_area: StudyArea,
    points: gpd.GeoDataFrame,
    graphs: Mapping[str, nx.MultiDiGraph],
    sample_size: int = 100,
    title: str | None = None,
):
    """Plota pontos e os respectivos nós associados em cada rede modal."""

    if points.empty:
        raise ValueError("Não há pontos para visualizar o snapping.")

    if sample_size <= 0:
        raise ValueError("sample_size precisa ser maior que zero.")

    sample = points.head(sample_size).copy()

    fig, ax = plt.subplots()

    gpd.GeoSeries(
        [study_area.geometry],
        crs=study_area.crs,
    ).boundary.plot(ax=ax)

    sample.to_crs(study_area.crs).plot(
        ax=ax,
        marker="o",
        markersize=16,
        label="Pontos",
    )

    for mode, graph in graphs.items():
        column = f"node_{mode}"

        if column not in sample.columns:
            continue

        nodes, _ = ox.graph_to_gdfs(
            graph,
            nodes=True,
            edges=True,
        )
        nodes = nodes.to_crs(study_area.crs)

        selected_ids = [
            node_id
            for node_id in sample[column].dropna()
            if node_id in nodes.index
        ]

        if not selected_ids:
            continue

        selected_nodes = nodes.loc[selected_ids]
        selected_nodes.plot(
            ax=ax,
            marker="x",
            markersize=20,
            label=f"Nós {mode}",
        )

        sample_projected = sample.to_crs(study_area.crs)

        for row_index, row in sample_projected.iterrows():
            node_id = row.get(column)

            if node_id not in nodes.index:
                continue

            node_geometry = nodes.loc[node_id].geometry

            ax.plot(
                [row.geometry.x, node_geometry.x],
                [row.geometry.y, node_geometry.y],
                linewidth=0.5,
            )

    ax.set_title(
        title or f"Snapping modal — {study_area.label}"
    )
    ax.set_axis_off()
    ax.legend()

    return fig, ax


def plot_agent_routes(
    *,
    agents,
    graphs: Mapping[str, nx.MultiDiGraph],
    sample_size: int = 100,
    title: str = "Rotas dos agentes",
    study_area: StudyArea | None = None,
):
    """Plota as rotas OSM já calculadas para uma amostra de agentes."""

    from shapely.geometry import LineString

    if sample_size <= 0:
        raise ValueError("sample_size precisa ser maior que zero.")

    fig, ax = plt.subplots()

    plotted = 0

    for agent in agents:
        if plotted >= sample_size:
            break

        if not getattr(agent, "route_edges", None):
            continue

        mode = getattr(agent, "mode", None)

        if mode is None:
            continue

        mode_name = mode.value if hasattr(mode, "value") else str(mode)

        if mode_name not in graphs:
            continue

        graph = graphs[mode_name]
        route_geometries = []

        for u, v, key in agent.route_edges:
            attributes = graph.get_edge_data(
                int(u),
                int(v),
                int(key),
            )

            if not attributes:
                continue

            geometry = attributes.get("geometry")

            if geometry is None:
                origin = graph.nodes[int(u)]
                destination = graph.nodes[int(v)]
                geometry = LineString(
                    [
                        (origin["x"], origin["y"]),
                        (destination["x"], destination["y"]),
                    ]
                )

            route_geometries.append(geometry)

        if not route_geometries:
            continue

        gpd.GeoSeries(
            route_geometries,
            crs=graph.graph.get("crs"),
        ).plot(
            ax=ax,
            linewidth=0.9,
        )

        plotted += 1

    apply_study_area_view(
        ax,
        study_area,
    )
    ax.set_title(f"{title} — n={plotted}")
    ax.set_axis_off()

    return fig, ax


def plot_transit_agent_routes(
    *,
    agents,
    walk_graph: nx.MultiDiGraph,
    physical_edges: gpd.GeoDataFrame,
    connection_to_physical_edge,
    sample_size: int = 50,
    title: str = "Rotas de transporte coletivo",
    study_area: StudyArea | None = None,
):
    """Plota acesso/egresso a pé e trechos físicos GTFS dos agentes transit."""

    from shapely.geometry import LineString

    if sample_size <= 0:
        raise ValueError("sample_size precisa ser maior que zero.")

    fig, ax = plt.subplots()

    mapping = connection_to_physical_edge.copy()
    mapping["connection_id"] = mapping["connection_id"].astype(str)
    mapping["transit_physical_edge_id"] = (
        mapping["transit_physical_edge_id"].astype(str)
    )

    edges = physical_edges.copy()
    edges["transit_physical_edge_id"] = (
        edges["transit_physical_edge_id"].astype(str)
    )

    plotted = 0

    for agent in agents:
        if plotted >= sample_size:
            break

        mode = getattr(agent, "mode", None)
        mode_name = (
            mode.value
            if hasattr(mode, "value")
            else str(mode)
        )

        if mode_name != "transit":
            continue

        connection_ids = list(
            getattr(agent, "transit_connection_ids", [])
        )

        if not connection_ids:
            continue

        physical_ids = (
            mapping.loc[
                mapping["connection_id"].isin(
                    [str(value) for value in connection_ids]
                ),
                "transit_physical_edge_id",
            ]
            .dropna()
            .astype(str)
            .unique()
            .tolist()
        )

        route_edges = edges.loc[
            edges["transit_physical_edge_id"].isin(physical_ids)
        ]

        if not route_edges.empty:
            route_edges.plot(
                ax=ax,
                linewidth=1.1,
            )

        walk_segments = []

        for edge_list in (
            getattr(agent, "transit_access_walk_edges", []),
            getattr(agent, "transit_egress_walk_edges", []),
        ):
            for u, v, key in edge_list:
                attributes = walk_graph.get_edge_data(
                    int(u),
                    int(v),
                    int(key),
                )

                if not attributes:
                    continue

                geometry = attributes.get("geometry")

                if geometry is None:
                    origin = walk_graph.nodes[int(u)]
                    destination = walk_graph.nodes[int(v)]
                    geometry = LineString(
                        [
                            (origin["x"], origin["y"]),
                            (destination["x"], destination["y"]),
                        ]
                    )

                walk_segments.append(geometry)

        if walk_segments:
            gpd.GeoSeries(
                walk_segments,
                crs=walk_graph.graph.get("crs"),
            ).plot(
                ax=ax,
                linewidth=0.8,
            )

        plotted += 1

    apply_study_area_view(
        ax,
        study_area,
    )
    ax.set_title(f"{title} — n={plotted}")
    ax.set_axis_off()

    return fig, ax


def plot_edge_usage(
    *,
    edge_usage,
    graphs: Mapping[str, nx.MultiDiGraph],
    transit_physical_edges: gpd.GeoDataFrame,
    title: str = "Uso das redes",
    study_area: StudyArea | None = None,
):
    """Plota intensidade de uso das arestas por número de travessias."""

    if edge_usage.empty:
        raise ValueError("edge_usage está vazio.")

    fig, ax = plt.subplots()

    counts = (
        edge_usage.groupby(
            ["network_mode", "edge_id"],
            as_index=False,
        )
        .size()
        .rename(columns={"size": "n_traversals"})
    )

    for mode in ("walk", "bike", "car"):
        if mode not in graphs:
            continue

        mode_counts = counts.loc[
            counts["network_mode"] == mode
        ].copy()

        if mode_counts.empty:
            continue

        graph = graphs[mode]
        _, edges = ox.graph_to_gdfs(
            graph,
            nodes=True,
            edges=True,
        )

        edges = edges.reset_index()
        edges["edge_id"] = (
            mode
            + ":"
            + edges["u"].astype(str)
            + ":"
            + edges["v"].astype(str)
            + ":"
            + edges["key"].astype(str)
        )

        merged = edges.merge(
            mode_counts,
            on="edge_id",
            how="inner",
        )

        if merged.empty:
            continue

        max_count = max(
            float(merged["n_traversals"].max()),
            1.0,
        )
        linewidth = (
            0.4
            + 3.0
            * merged["n_traversals"].astype(float)
            / max_count
        )

        gpd.GeoDataFrame(
            merged,
            geometry="geometry",
            crs=edges.crs,
        ).plot(
            ax=ax,
            linewidth=linewidth,
            label=mode,
        )

    transit_counts = counts.loc[
        counts["network_mode"] == "transit"
    ].copy()

    if not transit_counts.empty:
        transit = transit_physical_edges.copy()
        transit["transit_physical_edge_id"] = (
            transit["transit_physical_edge_id"].astype(str)
        )
        transit["edge_id"] = (
            "transit:"
            + transit["transit_physical_edge_id"]
        )

        transit = transit.merge(
            transit_counts,
            on="edge_id",
            how="inner",
        )

        if not transit.empty:
            max_count = max(
                float(transit["n_traversals"].max()),
                1.0,
            )
            linewidth = (
                0.4
                + 3.0
                * transit["n_traversals"].astype(float)
                / max_count
            )

            transit.plot(
                ax=ax,
                linewidth=linewidth,
                label="transit",
            )

    apply_study_area_view(
        ax,
        study_area,
    )
    ax.set_title(title)
    ax.set_axis_off()
    ax.legend()

    return fig, ax

def save_plot(
    fig,
    path: str | Path,
    *,
    dpi: int = 200,
) -> Path:
    """Salva uma figura sem acoplar plots a um diretório específico."""

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)

    fig.savefig(
        output,
        dpi=dpi,
        bbox_inches="tight",
    )

    return output
