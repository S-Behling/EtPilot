"""Visualizações de diagnóstico do estado atual do pipeline EtPilot.

A cada avanço relevante do projeto, este módulo deve receber uma nova função
de visualização correspondente ao novo estado dos dados. As funções retornam
figura e eixo para permitir composição, testes e salvamento externo.
"""

from __future__ import annotations

from pathlib import Path
import re
import unicodedata
from typing import Mapping

import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, Patch
import networkx as nx
import osmnx as ox
import pandas as pd

from src.spatial.regional_data import RegionalData
from src.spatial.study_area import StudyArea
from src.spatial.transit_filter import RegionalTransitData
from src.spatial.streets import (
    normalize_street_names,
    street_mask,
)


INCOME_COLORS = {
    "low": "#CABAD7",
    "middle": "#4F364B",
    "high": "#DB3E1D",
}

INCOME_LABELS = {
    "low": "Baixa renda",
    "middle": "Média renda",
    "high": "Alta renda",
}

MODE_LINESTYLES = {
    "walk": (0, (1, 2)),
    "bike": (0, (6, 3)),
    "car": "solid",
    "transit": "solid",
}

MODE_LABELS = {
    "walk": "Walk",
    "bike": "Bike",
    "car": "Carro",
    "transit": "Ônibus",
}

# Todos os mapas finais usam fundo branco puro para facilitar leitura,
# impressão e comparação entre figuras.
MAP_BACKGROUND = "#FFFFFF"
MAP_NEUTRAL = "#2F2A2A"

# As redes aparecem sempre como contexto. Em quase todos os mapas elas ficam
# deliberadamente discretas; apenas o mapa obrigatório de redes usa tons fortes.
NETWORK_BASE_WEAK = "#D9D9D9"
NETWORK_BASE_STRONG = "#5F5F5F"

# Gradiente censitário construído com a mesma paleta das classes sociais.
CENSUS_INCOME_CMAP = LinearSegmentedColormap.from_list(
    "etpilot_income",
    [
        INCOME_COLORS["low"],
        INCOME_COLORS["middle"],
        INCOME_COLORS["high"],
    ],
)



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





def _agent_income_color(agent) -> str:
    income = getattr(
        agent,
        "income_group",
        None,
    )
    key = (
        income.value
        if hasattr(income, "value")
        else str(income)
    )

    return INCOME_COLORS.get(
        key,
        MAP_NEUTRAL,
    )


def _plot_agent_od_markers(
    ax,
    *,
    agent,
    graph: nx.MultiDiGraph,
    origin_node: int | None,
    destination_node: int | None,
) -> None:
    """Marca origem com X e destino com círculo, preservando a cor da renda."""

    color = _agent_income_color(
        agent
    )

    if (
        origin_node is not None
        and int(origin_node) in graph.nodes
    ):
        node = graph.nodes[
            int(origin_node)
        ]
        ax.scatter(
            [node["x"]],
            [node["y"]],
            marker="x",
            s=62,
            c=[color],
            linewidths=1.7,
            zorder=8,
        )

    if (
        destination_node is not None
        and int(destination_node) in graph.nodes
    ):
        node = graph.nodes[
            int(destination_node)
        ]
        ax.scatter(
            [node["x"]],
            [node["y"]],
            marker="o",
            s=48,
            facecolors="none",
            edgecolors=[color],
            linewidths=1.7,
            zorder=8,
        )


def _add_od_marker_legend(
    ax,
) -> None:
    handles = [
        Line2D(
            [0],
            [0],
            marker="x",
            linestyle="none",
            color=MAP_NEUTRAL,
            markersize=7,
            markeredgewidth=1.5,
            label="Origem",
        ),
        Line2D(
            [0],
            [0],
            marker="o",
            linestyle="none",
            markerfacecolor="none",
            markeredgecolor=MAP_NEUTRAL,
            color=MAP_NEUTRAL,
            markersize=7,
            markeredgewidth=1.5,
            label="Destino",
        ),
    ]

    ax.legend(
        handles=handles,
        title="O/D",
        loc="lower left",
        frameon=True,
    )


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
    show_od_markers = len(agents) < 20

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

        if show_od_markers:
            _plot_agent_od_markers(
                ax,
                agent=agent,
                graph=graph,
                origin_node=getattr(
                    agent,
                    "origin_node",
                    None,
                ),
                destination_node=getattr(
                    agent,
                    "destination_node",
                    None,
                ),
            )

        plotted += 1

    apply_study_area_view(
        ax,
        study_area,
    )
    if show_od_markers and plotted:
        _add_od_marker_legend(
            ax
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
    show_od_markers = len(agents) < 20

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

        if show_od_markers:
            _plot_agent_od_markers(
                ax,
                agent=agent,
                graph=walk_graph,
                origin_node=getattr(
                    agent,
                    "origin_nodes",
                    {},
                ).get("walk"),
                destination_node=getattr(
                    agent,
                    "destination_nodes",
                    {},
                ).get("walk"),
            )

        plotted += 1

    apply_study_area_view(
        ax,
        study_area,
    )
    if show_od_markers and plotted:
        _add_od_marker_legend(
            ax
        )

    ax.set_title(f"{title} — n={plotted}")
    ax.set_axis_off()

    return fig, ax


def _set_map_background(
    fig,
    ax,
) -> None:
    fig.patch.set_facecolor(
        MAP_BACKGROUND
    )
    ax.set_facecolor(
        MAP_BACKGROUND
    )


def _plot_transit_arrows(
    ax,
    geometry,
    *,
    color: str,
    linewidth: float,
) -> None:
    """Adiciona uma seta central seguindo a orientação da geometria."""

    if geometry is None or geometry.is_empty:
        return

    parts = (
        list(geometry.geoms)
        if hasattr(geometry, "geoms")
        else [geometry]
    )

    for part in parts:
        if (
            part.is_empty
            or part.length <= 0
            or not hasattr(
                part,
                "interpolate",
            )
        ):
            continue

        start = part.interpolate(
            0.44,
            normalized=True,
        )
        end = part.interpolate(
            0.56,
            normalized=True,
        )

        arrow = FancyArrowPatch(
            (start.x, start.y),
            (end.x, end.y),
            arrowstyle="-|>",
            mutation_scale=(
                8.0
                + 2.0 * linewidth
            ),
            color=color,
            linewidth=max(
                0.7,
                linewidth * 0.7,
            ),
            shrinkA=0,
            shrinkB=0,
            zorder=5,
        )
        ax.add_patch(
            arrow
        )


def _plot_styled_edge_usage(
    ax,
    usage_geometry: gpd.GeoDataFrame,
    *,
    force_solid: bool = False,
) -> None:
    """Plota uso de arestas usando cor por renda e linha por modo.

    Quando force_solid=True, todos os trechos ficam contínuos. Isso atende à
    regra cartográfica de simplificar mapas que já mostram apenas um único
    modo de viagem.
    """

    if usage_geometry.empty:
        return

    grouped = (
        usage_geometry.groupby(
            [
                "income_group",
                "network_mode",
                "edge_id",
            ],
            dropna=False,
            as_index=False,
        )
        .agg(
            n_traversals=("agent_id", "size"),
            geometry=("geometry", "first"),
        )
    )

    grouped = gpd.GeoDataFrame(
        grouped,
        geometry="geometry",
        crs=usage_geometry.crs,
    )

    max_count = max(
        float(
            grouped[
                "n_traversals"
            ].max()
        ),
        1.0,
    )

    for (
        income_group,
        network_mode,
    ), subset in grouped.groupby(
        [
            "income_group",
            "network_mode",
        ],
        dropna=False,
    ):
        income_key = str(
            income_group
        )
        mode_key = str(
            network_mode
        )

        color = INCOME_COLORS.get(
            income_key,
            MAP_NEUTRAL,
        )
        linestyle = (
            "solid"
            if force_solid
            else MODE_LINESTYLES.get(
                mode_key,
                "solid",
            )
        )

        linewidths = (
            0.7
            + 3.3
            * subset[
                "n_traversals"
            ].astype(float)
            / max_count
        )

        subset.plot(
            ax=ax,
            color=color,
            linewidth=linewidths,
            linestyle=linestyle,
            alpha=0.95,
            zorder=3,
        )

        if mode_key == "transit":
            for geometry, linewidth in zip(
                subset.geometry,
                linewidths,
            ):
                _plot_transit_arrows(
                    ax,
                    geometry,
                    color=color,
                    linewidth=float(
                        linewidth
                    ),
                )


def _add_usage_legends(
    ax,
    usage_geometry: gpd.GeoDataFrame,
    *,
    force_solid: bool = False,
) -> None:
    present_incomes = [
        income
        for income in (
            "low",
            "middle",
            "high",
        )
        if income in set(
            usage_geometry[
                "income_group"
            ].astype(str)
        )
    ]

    present_modes = [
        mode
        for mode in (
            "walk",
            "bike",
            "car",
            "transit",
        )
        if mode in set(
            usage_geometry[
                "network_mode"
            ].astype(str)
        )
    ]

    income_handles = [
        Line2D(
            [0],
            [0],
            color=INCOME_COLORS[
                income
            ],
            linewidth=3,
            label=INCOME_LABELS[
                income
            ],
        )
        for income in present_incomes
    ]

    mode_handles = []

    for mode in present_modes:
        kwargs = {
            "color": MAP_NEUTRAL,
            "linewidth": 2,
            "linestyle": (
                "solid"
                if force_solid
                else MODE_LINESTYLES[
                    mode
                ]
            ),
            "label": MODE_LABELS[
                mode
            ],
        }

        if mode == "transit":
            kwargs.update(
                marker=">",
                markersize=6,
                markevery=[1],
            )

        mode_handles.append(
            Line2D(
                [0, 1],
                [0, 0],
                **kwargs,
            )
        )

    if income_handles:
        income_legend = ax.legend(
            handles=income_handles,
            title="Classe social",
            loc="upper left",
            frameon=True,
        )
        ax.add_artist(
            income_legend
        )

    if mode_handles:
        ax.legend(
            handles=mode_handles,
            title="Modo",
            loc="upper right",
            frameon=True,
        )


def plot_edge_usage(
    *,
    edge_usage,
    graphs: Mapping[str, nx.MultiDiGraph],
    transit_physical_edges: gpd.GeoDataFrame,
    title: str = "Uso das redes",
    study_area: StudyArea | None = None,
):
    """Plota uso das redes com cor por renda e linha por modo."""

    if edge_usage.empty:
        raise ValueError(
            "edge_usage está vazio."
        )

    usage_geometry = _edge_usage_geometry(
        edge_usage=edge_usage,
        graphs=graphs,
        transit_physical_edges=transit_physical_edges,
    )

    if usage_geometry.empty:
        raise ValueError(
            "Nenhuma geometria pôde ser associada aos registros de uso."
        )

    fig, ax = plt.subplots(
        figsize=(10, 9)
    )
    _set_map_background(
        fig,
        ax,
    )

    _plot_styled_edge_usage(
        ax,
        usage_geometry,
    )

    apply_study_area_view(
        ax,
        study_area,
    )
    _add_usage_legends(
        ax,
        usage_geometry,
    )

    ax.set_title(
        title
    )
    ax.set_axis_off()

    return fig, ax


def _edge_usage_geometry(
    *,
    edge_usage,
    graphs: Mapping[str, nx.MultiDiGraph],
    transit_physical_edges: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """Associa os registros de uso às geometrias das respectivas redes."""

    frames = []

    for mode in ("walk", "bike", "car"):
        mode_usage = edge_usage.loc[
            edge_usage["network_mode"] == mode
        ].copy()

        if mode_usage.empty or mode not in graphs:
            continue

        _, edges = ox.graph_to_gdfs(
            graphs[mode],
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

        edges["street_names"] = (
            edges["name"].apply(
                normalize_street_names
            )
            if "name" in edges.columns
            else [
                []
                for _ in range(
                    len(edges)
                )
            ]
        )

        merged = mode_usage.merge(
            edges[
                [
                    "edge_id",
                    "street_names",
                    "geometry",
                ]
            ],
            on="edge_id",
            how="inner",
        )

        if not merged.empty:
            frames.append(
                gpd.GeoDataFrame(
                    merged,
                    geometry="geometry",
                    crs=edges.crs,
                )
            )

    transit_usage = edge_usage.loc[
        edge_usage["network_mode"] == "transit"
    ].copy()

    if not transit_usage.empty:
        transit = transit_physical_edges.copy()
        transit["transit_physical_edge_id"] = (
            transit["transit_physical_edge_id"].astype(str)
        )
        transit["edge_id"] = (
            "transit:"
            + transit["transit_physical_edge_id"]
        )

        # Arestas de transporte coletivo nem sempre possuem nome de rua.
        # Elas serão associadas à rua selecionada por sobreposição espacial.
        transit["street_names"] = [
            []
            for _ in range(
                len(transit)
            )
        ]

        merged = transit_usage.merge(
            transit[
                [
                    "edge_id",
                    "street_names",
                    "geometry",
                ]
            ],
            on="edge_id",
            how="inner",
        )

        if not merged.empty:
            frames.append(
                gpd.GeoDataFrame(
                    merged,
                    geometry="geometry",
                    crs=transit.crs,
                )
            )

    if not frames:
        return gpd.GeoDataFrame(
            columns=[
                *edge_usage.columns,
                "geometry",
            ],
            geometry="geometry",
        )

    target_crs = frames[0].crs

    normalized = [
        frame.to_crs(target_crs)
        if frame.crs != target_crs
        else frame
        for frame in frames
    ]

    return gpd.GeoDataFrame(
        pd.concat(
            normalized,
            ignore_index=True,
        ),
        geometry="geometry",
        crs=target_crs,
    )


def plot_edge_usage_by_category(
    *,
    edge_usage,
    graphs: Mapping[str, nx.MultiDiGraph],
    transit_physical_edges: gpd.GeoDataFrame,
    category: str,
    study_area: StudyArea | None = None,
    title: str | None = None,
):
    """Plota painéis mantendo cor por renda e linha por modo em todos eles."""

    if edge_usage.empty:
        raise ValueError(
            "edge_usage está vazio."
        )

    if category not in edge_usage.columns:
        raise KeyError(
            f"Categoria '{category}' não existe em edge_usage."
        )

    usage_geometry = _edge_usage_geometry(
        edge_usage=edge_usage,
        graphs=graphs,
        transit_physical_edges=transit_physical_edges,
    )

    if usage_geometry.empty:
        raise ValueError(
            "Nenhuma geometria pôde ser associada aos registros de uso."
        )

    categories = sorted(
        str(value)
        for value in usage_geometry[
            category
        ]
        .dropna()
        .unique()
    )

    if not categories:
        raise ValueError(
            f"Nenhum valor válido encontrado em '{category}'."
        )

    ncols = min(
        2,
        len(categories),
    )
    nrows = (
        len(categories)
        + ncols
        - 1
    ) // ncols

    fig, axes = plt.subplots(
        nrows=nrows,
        ncols=ncols,
        figsize=(
            8 * ncols,
            7 * nrows,
        ),
        squeeze=False,
    )
    fig.patch.set_facecolor(
        MAP_BACKGROUND
    )

    flat_axes = axes.ravel()

    for ax, value in zip(
        flat_axes,
        categories,
    ):
        ax.set_facecolor(
            MAP_BACKGROUND
        )

        subset = usage_geometry.loc[
            usage_geometry[
                category
            ].astype(str)
            == value
        ].copy()

        # Se o painel contém apenas um modo de viagem, a diferenciação
        # por tracejado deixa de ser necessária e todas as linhas ficam contínuas.
        single_trip_mode = (
            subset["trip_mode"]
            .astype(str)
            .nunique()
            <= 1
        )

        _plot_styled_edge_usage(
            ax,
            subset,
            force_solid=single_trip_mode,
        )

        apply_study_area_view(
            ax,
            study_area,
        )

        _add_usage_legends(
            ax,
            subset,
            force_solid=single_trip_mode,
        )

        ax.set_title(
            (
                f"{value} — "
                f"{len(subset):,} registros de uso"
            )
        )
        ax.set_axis_off()

    for ax in flat_axes[
        len(categories):
    ]:
        ax.set_visible(
            False
        )

    fig.suptitle(
        title
        or f"Uso dos trechos por {category}",
        fontsize=14,
    )
    fig.tight_layout()

    return fig, axes



# ============================================================================
# MAPAS OBRIGATÓRIOS DO PILOTO
# ============================================================================
#
# Os mapas abaixo formam o conjunto mínimo que deve existir em toda execução.
# Eles são separados dos mapas opcionais da GUI: mesmo que o usuário não
# selecione nenhum mapa extra, estes produtos continuam sendo gerados.
#
# Regras visuais comuns:
# - fundo branco;
# - redes de referência sempre visíveis em cinza claro;
# - no mapa exclusivo de redes, o cinza é propositalmente mais forte;
# - classe social é codificada por cor;
# - quando um mapa contém somente um modo de viagem, as rotas são contínuas;
# - a espessura representa intensidade relativa de travessias.


def _network_edges_for_plot(
    graphs: Mapping[str, nx.MultiDiGraph],
) -> dict[str, gpd.GeoDataFrame]:
    """Converte cada grafo modal em GeoDataFrame uma única vez.

    A geração obrigatória cria muitas figuras. Fazer graph_to_gdfs em cada
    figura seria desnecessariamente caro; por isso a conversão é preparada uma
    única vez e reutilizada por todos os mapas da mesma rodada.
    """

    result: dict[str, gpd.GeoDataFrame] = {}

    for mode in ("walk", "bike", "car"):
        graph = graphs.get(mode)

        if graph is None:
            continue

        _, edges = ox.graph_to_gdfs(
            graph,
            nodes=True,
            edges=True,
        )

        result[mode] = edges

    return result


def _plot_network_context(
    ax,
    *,
    network_edges: Mapping[str, gpd.GeoDataFrame],
    transit_physical_edges: gpd.GeoDataFrame,
    strong: bool = False,
    add_legend: bool = False,
) -> None:
    """Desenha as redes de referência por baixo dos dados simulados.

    Em praticamente todos os mapas as redes devem funcionar apenas como
    contexto espacial, portanto recebem cinza claro, baixa espessura e baixa
    prioridade visual. O mapa obrigatório 8 chama esta função com strong=True
    para transformar as redes no assunto principal da figura.
    """

    if strong:
        # No mapa de redes usamos tons fortes e estilos distintos para que as
        # quatro infraestruturas possam ser identificadas sem depender de cor.
        styles = {
            "walk": {
                "color": "#777777",
                "linewidth": 0.8,
                "linestyle": (0, (1, 2)),
                "label": "Walk",
            },
            "bike": {
                "color": "#666666",
                "linewidth": 0.9,
                "linestyle": (0, (6, 3)),
                "label": "Bike",
            },
            "car": {
                "color": "#444444",
                "linewidth": 1.0,
                "linestyle": "solid",
                "label": "Carro",
            },
        }
        transit_color = "#222222"
        transit_width = 1.2
        alpha = 0.92
    else:
        # Nas demais figuras todas as redes aparecem discretamente para não
        # competir com trajetórias, classes sociais ou setores censitários.
        styles = {
            mode: {
                "color": NETWORK_BASE_WEAK,
                "linewidth": 0.35,
                "linestyle": "solid",
                "label": MODE_LABELS.get(mode, mode),
            }
            for mode in ("walk", "bike", "car")
        }
        transit_color = NETWORK_BASE_WEAK
        transit_width = 0.45
        alpha = 0.65

    legend_handles = []

    for mode in ("walk", "bike", "car"):
        edges = network_edges.get(mode)

        if edges is None or edges.empty:
            continue

        style = styles[mode]

        edges.plot(
            ax=ax,
            color=style["color"],
            linewidth=style["linewidth"],
            linestyle=style["linestyle"],
            alpha=alpha,
            zorder=1,
        )

        if strong and add_legend:
            legend_handles.append(
                Line2D(
                    [0],
                    [0],
                    color=style["color"],
                    linewidth=2,
                    linestyle=style["linestyle"],
                    label=style["label"],
                )
            )

    if (
        transit_physical_edges is not None
        and not transit_physical_edges.empty
    ):
        transit_physical_edges.plot(
            ax=ax,
            color=transit_color,
            linewidth=transit_width,
            linestyle="solid",
            alpha=alpha,
            zorder=1,
        )

        if strong and add_legend:
            legend_handles.append(
                Line2D(
                    [0],
                    [0],
                    color=transit_color,
                    linewidth=2,
                    linestyle="solid",
                    marker=">",
                    markevery=[1],
                    label="Ônibus",
                )
            )

    if legend_handles:
        ax.legend(
            handles=legend_handles,
            title="Redes",
            loc="upper right",
            frameon=True,
        )


def _annotate_no_simulated_routes(
    ax,
    message: str = "Sem trajetos simulados para este filtro",
) -> None:
    """Mantém o mapa obrigatório legível mesmo quando o filtro fica vazio."""

    ax.text(
        0.5,
        0.04,
        message,
        transform=ax.transAxes,
        ha="center",
        va="bottom",
        fontsize=9,
        color="#666666",
        bbox={
            "facecolor": "#FFFFFF",
            "edgecolor": "#CCCCCC",
            "alpha": 0.9,
            "pad": 4,
        },
        zorder=20,
    )


def _income_offset_geometry(
    geometry,
    income_group: str,
    *,
    offset_m: float = 4.0,
):
    """Desloca levemente classes paralelas para evitar sobreposição total.

    O CRS operacional do projeto é métrico (EPSG:31982). Portanto o pequeno
    deslocamento lateral abaixo é medido em metros. Ele não altera a rota
    analítica; serve somente à representação cartográfica.
    """

    if geometry is None or geometry.is_empty:
        return geometry

    offsets = {
        "low": -offset_m,
        "middle": 0.0,
        "high": offset_m,
    }

    distance = offsets.get(
        str(income_group),
        0.0,
    )

    if distance == 0:
        return geometry

    # parallel_offset é confiável para LineString. Para geometrias compostas
    # mantemos a geometria original em vez de arriscar uma transformação
    # cartograficamente incorreta.
    if geometry.geom_type != "LineString":
        return geometry

    try:
        return geometry.parallel_offset(
            abs(distance),
            side=(
                "left"
                if distance > 0
                else "right"
            ),
            join_style=2,
        )
    except Exception:
        # O mapa nunca deve derrubar o pipeline apenas porque uma geometria
        # específica não aceitou o offset visual.
        return geometry


def _plot_continuous_usage_by_income(
    ax,
    usage_geometry: gpd.GeoDataFrame,
    *,
    offset_classes: bool,
) -> None:
    """Plota classes por cor usando somente linhas contínuas.

    Esta função é utilizada nos mapas obrigatórios em que o modo já está
    filtrado ou em que o usuário pediu explicitamente todos os modos em linha
    contínua. A agregação por aresta preserva a intensidade de uso.
    """

    if usage_geometry.empty:
        return

    grouped = (
        usage_geometry.groupby(
            [
                "income_group",
                "edge_id",
            ],
            dropna=False,
            as_index=False,
        )
        .agg(
            n_traversals=("agent_id", "size"),
            geometry=("geometry", "first"),
        )
    )

    grouped = gpd.GeoDataFrame(
        grouped,
        geometry="geometry",
        crs=usage_geometry.crs,
    )

    max_count = max(
        float(
            grouped["n_traversals"].max()
        ),
        1.0,
    )

    for income_group, subset in grouped.groupby(
        "income_group",
        dropna=False,
    ):
        income_key = str(
            income_group
        )
        color = INCOME_COLORS.get(
            income_key,
            MAP_NEUTRAL,
        )

        subset = subset.copy()

        if offset_classes:
            subset["geometry"] = [
                _income_offset_geometry(
                    geometry,
                    income_key,
                )
                for geometry in subset.geometry
            ]

        linewidths = (
            0.8
            + 3.2
            * subset[
                "n_traversals"
            ].astype(float)
            / max_count
        )

        subset.plot(
            ax=ax,
            color=color,
            linewidth=linewidths,
            linestyle="solid",
            alpha=0.96,
            zorder=4,
        )


def _add_income_only_legend(
    ax,
    *,
    income_groups: list[str] | None = None,
) -> None:
    """Adiciona legenda padronizada das classes sociais."""

    groups = income_groups or [
        "low",
        "middle",
        "high",
    ]

    handles = [
        Line2D(
            [0],
            [0],
            color=INCOME_COLORS[group],
            linewidth=3,
            label=INCOME_LABELS[group],
        )
        for group in groups
        if group in INCOME_COLORS
    ]

    if handles:
        ax.legend(
            handles=handles,
            title="Classe social",
            loc="upper right",
            frameon=True,
        )


def plot_mandatory_mode_all_incomes(
    *,
    usage_geometry: gpd.GeoDataFrame,
    network_edges: Mapping[str, gpd.GeoDataFrame],
    transit_physical_edges: gpd.GeoDataFrame,
    trip_mode: str,
    study_area: StudyArea | None,
):
    """Mapa obrigatório 1: um modo de viagem com todas as classes sociais."""

    fig, ax = plt.subplots(
        figsize=(10, 9)
    )
    _set_map_background(
        fig,
        ax,
    )

    _plot_network_context(
        ax,
        network_edges=network_edges,
        transit_physical_edges=transit_physical_edges,
        strong=False,
    )

    subset = usage_geometry.loc[
        usage_geometry[
            "trip_mode"
        ].astype(str)
        == trip_mode
    ].copy()

    # Como a figura mostra somente um modo de viagem, todas as trajetórias são
    # desenhadas com linha contínua. As classes permanecem diferenciadas por cor.
    _plot_continuous_usage_by_income(
        ax,
        subset,
        offset_classes=True,
    )

    if subset.empty:
        _annotate_no_simulated_routes(
            ax
        )

    apply_study_area_view(
        ax,
        study_area,
    )
    _add_income_only_legend(
        ax
    )

    ax.set_title(
        f"{MODE_LABELS.get(trip_mode, trip_mode)} — todas as classes"
    )
    ax.set_axis_off()

    return fig, ax


def plot_mandatory_mode_income(
    *,
    usage_geometry: gpd.GeoDataFrame,
    network_edges: Mapping[str, gpd.GeoDataFrame],
    transit_physical_edges: gpd.GeoDataFrame,
    trip_mode: str,
    income_group: str,
    study_area: StudyArea | None,
):
    """Mapas obrigatórios 2–5: uma classe social e um modo por figura."""

    fig, ax = plt.subplots(
        figsize=(10, 9)
    )
    _set_map_background(
        fig,
        ax,
    )

    _plot_network_context(
        ax,
        network_edges=network_edges,
        transit_physical_edges=transit_physical_edges,
        strong=False,
    )

    subset = usage_geometry.loc[
        (
            usage_geometry[
                "trip_mode"
            ].astype(str)
            == trip_mode
        )
        & (
            usage_geometry[
                "income_group"
            ].astype(str)
            == income_group
        )
    ].copy()

    _plot_continuous_usage_by_income(
        ax,
        subset,
        offset_classes=False,
    )

    if subset.empty:
        _annotate_no_simulated_routes(
            ax
        )

    apply_study_area_view(
        ax,
        study_area,
    )

    color = INCOME_COLORS.get(
        income_group,
        MAP_NEUTRAL,
    )

    ax.legend(
        handles=[
            Line2D(
                [0],
                [0],
                color=color,
                linewidth=3,
                linestyle="solid",
                label=(
                    f"{INCOME_LABELS.get(income_group, income_group)}"
                    f" — {MODE_LABELS.get(trip_mode, trip_mode)}"
                ),
            )
        ],
        loc="upper right",
        frameon=True,
    )

    ax.set_title(
        (
            f"{MODE_LABELS.get(trip_mode, trip_mode)} — "
            f"{INCOME_LABELS.get(income_group, income_group)}"
        )
    )
    ax.set_axis_off()

    return fig, ax


def plot_census_income_gradient(
    *,
    census_sectors: gpd.GeoDataFrame,
    network_edges: Mapping[str, gpd.GeoDataFrame],
    transit_physical_edges: gpd.GeoDataFrame,
    study_area: StudyArea | None,
    income_column: str = "renda_media_responsavel",
):
    """Mapa obrigatório 6: setores censitários em gradiente de renda."""

    if income_column not in census_sectors.columns:
        raise KeyError(
            f"Coluna de renda '{income_column}' ausente nos setores censitários."
        )

    fig, ax = plt.subplots(
        figsize=(10, 9)
    )
    _set_map_background(
        fig,
        ax,
    )

    sectors = census_sectors.copy()
    sectors[income_column] = pd.to_numeric(
        sectors[income_column],
        errors="coerce",
    )

    valid = sectors.loc[
        sectors[income_column].notna()
    ].copy()
    missing = sectors.loc[
        sectors[income_column].isna()
    ].copy()

    if not missing.empty:
        missing.plot(
            ax=ax,
            color="#F2F2F2",
            edgecolor="#D0D0D0",
            linewidth=0.2,
            zorder=1,
        )

    if not valid.empty:
        valid.plot(
            ax=ax,
            column=income_column,
            cmap=CENSUS_INCOME_CMAP,
            edgecolor="#BDBDBD",
            linewidth=0.25,
            legend=True,
            legend_kwds={
                "label": "Renda média do responsável (R$)",
                "shrink": 0.72,
            },
            zorder=2,
        )

    # Mesmo no mapa censitário a infraestrutura urbana continua visível, mas
    # apenas como referência em cinza claro.
    _plot_network_context(
        ax,
        network_edges=network_edges,
        transit_physical_edges=transit_physical_edges,
        strong=False,
    )

    apply_study_area_view(
        ax,
        study_area,
    )

    # A barra contínua mostra a variação de renda dentro das classes. A legenda
    # abaixo mantém explícita a associação das três cores-base às classes
    # socioeconômicas usadas em todo o restante do projeto.
    ax.legend(
        handles=[
            Patch(
                facecolor=INCOME_COLORS["low"],
                edgecolor="none",
                label=INCOME_LABELS["low"],
            ),
            Patch(
                facecolor=INCOME_COLORS["middle"],
                edgecolor="none",
                label=INCOME_LABELS["middle"],
            ),
            Patch(
                facecolor=INCOME_COLORS["high"],
                edgecolor="none",
                label=INCOME_LABELS["high"],
            ),
        ],
        title="Classes de renda",
        loc="upper right",
        frameon=True,
    )

    ax.set_title(
        "Setores censitários — gradiente de renda"
    )
    ax.set_axis_off()

    return fig, ax


def plot_census_plus_all_modes(
    *,
    census_sectors: gpd.GeoDataFrame,
    usage_geometry: gpd.GeoDataFrame,
    network_edges: Mapping[str, gpd.GeoDataFrame],
    transit_physical_edges: gpd.GeoDataFrame,
    study_area: StudyArea | None,
    income_column: str = "renda_media_responsavel",
):
    """Mapa obrigatório 7: setores censitários + todos os modos simulados.

    Todos os modos são representados por linha contínua. A classe social é
    identificada exclusivamente pela cor, e classes que compartilham a mesma
    aresta recebem pequeno deslocamento lateral para melhorar a leitura.
    """

    fig, ax = plt.subplots(
        figsize=(10, 9)
    )
    _set_map_background(
        fig,
        ax,
    )

    sectors = census_sectors.copy()
    sectors[income_column] = pd.to_numeric(
        sectors[income_column],
        errors="coerce",
    )

    valid = sectors.loc[
        sectors[income_column].notna()
    ].copy()

    if not valid.empty:
        valid.plot(
            ax=ax,
            column=income_column,
            cmap=CENSUS_INCOME_CMAP,
            edgecolor="#C6C6C6",
            linewidth=0.2,
            alpha=0.55,
            zorder=1,
        )

    _plot_network_context(
        ax,
        network_edges=network_edges,
        transit_physical_edges=transit_physical_edges,
        strong=False,
    )

    _plot_continuous_usage_by_income(
        ax,
        usage_geometry,
        offset_classes=True,
    )

    if usage_geometry.empty:
        _annotate_no_simulated_routes(
            ax
        )

    apply_study_area_view(
        ax,
        study_area,
    )
    _add_income_only_legend(
        ax
    )

    ax.set_title(
        "Setores censitários + todos os modos por classe social"
    )
    ax.set_axis_off()

    return fig, ax


def plot_all_networks(
    *,
    network_edges: Mapping[str, gpd.GeoDataFrame],
    transit_physical_edges: gpd.GeoDataFrame,
    study_area: StudyArea | None,
):
    """Mapa obrigatório 8: todas as redes em cinza forte."""

    fig, ax = plt.subplots(
        figsize=(10, 9)
    )
    _set_map_background(
        fig,
        ax,
    )

    _plot_network_context(
        ax,
        network_edges=network_edges,
        transit_physical_edges=transit_physical_edges,
        strong=True,
        add_legend=True,
    )

    apply_study_area_view(
        ax,
        study_area,
    )

    ax.set_title(
        "Todas as redes de mobilidade"
    )
    ax.set_axis_off()

    return fig, ax


def _route_edge_geometries(
    graph: nx.MultiDiGraph,
    edge_list,
):
    """Recupera as geometrias de uma sequência de arestas de um agente."""

    from shapely.geometry import LineString

    geometries = []

    for u, v, key in edge_list:
        attributes = graph.get_edge_data(
            int(u),
            int(v),
            int(key),
        )

        if not attributes:
            continue

        geometry = attributes.get(
            "geometry"
        )

        if geometry is None:
            origin = graph.nodes[
                int(u)
            ]
            destination = graph.nodes[
                int(v)
            ]
            geometry = LineString(
                [
                    (
                        origin["x"],
                        origin["y"],
                    ),
                    (
                        destination["x"],
                        destination["y"],
                    ),
                ]
            )

        geometries.append(
            geometry
        )

    return geometries


def plot_agent_routes_unique_colors(
    *,
    agents,
    graphs: Mapping[str, nx.MultiDiGraph],
    network_edges: Mapping[str, gpd.GeoDataFrame],
    transit_physical_edges: gpd.GeoDataFrame,
    connection_to_physical_edge,
    study_area: StudyArea | None,
):
    """Mapa obrigatório 9: cada agente recebe uma cor exclusiva.

    Por regra de legibilidade este mapa só é gerado quando existem menos de
    40 agentes. Quando há menos de 20, origem e destino também são marcados
    com X e círculo, respectivamente.
    """

    if len(agents) >= 40:
        return None, None

    fig, ax = plt.subplots(
        figsize=(10, 9)
    )
    _set_map_background(
        fig,
        ax,
    )

    _plot_network_context(
        ax,
        network_edges=network_edges,
        transit_physical_edges=transit_physical_edges,
        strong=False,
    )

    mapping = (
        connection_to_physical_edge.copy()
    )
    mapping[
        "connection_id"
    ] = mapping[
        "connection_id"
    ].astype(str)
    mapping[
        "transit_physical_edge_id"
    ] = mapping[
        "transit_physical_edge_id"
    ].astype(str)

    transit_edges = (
        transit_physical_edges.copy()
    )
    transit_edges[
        "transit_physical_edge_id"
    ] = transit_edges[
        "transit_physical_edge_id"
    ].astype(str)

    # turbo oferece cores suficientemente separadas para amostras pequenas sem
    # impor significado ordinal às cores dos agentes.
    cmap = plt.get_cmap(
        "turbo",
        max(
            len(agents),
            1,
        ),
    )

    show_od = len(agents) < 20

    for index, agent in enumerate(
        agents
    ):
        color = cmap(
            index
        )
        mode = getattr(
            agent,
            "mode",
            None,
        )
        mode_name = (
            mode.value
            if hasattr(
                mode,
                "value",
            )
            else str(mode)
        )

        if mode_name in {
            "walk",
            "bike",
            "car",
        }:
            graph = graphs.get(
                mode_name
            )

            if graph is None:
                continue

            geometries = (
                _route_edge_geometries(
                    graph,
                    getattr(
                        agent,
                        "route_edges",
                        [],
                    ),
                )
            )

            if geometries:
                gpd.GeoSeries(
                    geometries,
                    crs=graph.graph.get(
                        "crs"
                    ),
                ).plot(
                    ax=ax,
                    color=color,
                    linewidth=1.8,
                    linestyle="solid",
                    alpha=0.95,
                    zorder=5,
                )

            if show_od:
                origin_node = getattr(
                    agent,
                    "origin_node",
                    None,
                )
                destination_node = getattr(
                    agent,
                    "destination_node",
                    None,
                )

                if (
                    origin_node is not None
                    and int(origin_node)
                    in graph.nodes
                ):
                    node = graph.nodes[
                        int(origin_node)
                    ]
                    ax.scatter(
                        [node["x"]],
                        [node["y"]],
                        marker="x",
                        s=65,
                        color=[color],
                        linewidths=1.8,
                        zorder=8,
                    )

                if (
                    destination_node
                    is not None
                    and int(
                        destination_node
                    )
                    in graph.nodes
                ):
                    node = graph.nodes[
                        int(
                            destination_node
                        )
                    ]
                    ax.scatter(
                        [node["x"]],
                        [node["y"]],
                        marker="o",
                        s=50,
                        facecolors="none",
                        edgecolors=[color],
                        linewidths=1.8,
                        zorder=8,
                    )

        elif mode_name == "transit":
            walk_graph = graphs.get(
                "walk"
            )

            if walk_graph is None:
                continue

            # Acesso e egresso a pé recebem a mesma cor do agente para que a
            # trajetória completa possa ser seguida visualmente.
            walk_geometries = []

            for edge_list in (
                getattr(
                    agent,
                    "transit_access_walk_edges",
                    [],
                ),
                getattr(
                    agent,
                    "transit_egress_walk_edges",
                    [],
                ),
            ):
                walk_geometries.extend(
                    _route_edge_geometries(
                        walk_graph,
                        edge_list,
                    )
                )

            if walk_geometries:
                gpd.GeoSeries(
                    walk_geometries,
                    crs=walk_graph.graph.get(
                        "crs"
                    ),
                ).plot(
                    ax=ax,
                    color=color,
                    linewidth=1.8,
                    linestyle="solid",
                    alpha=0.95,
                    zorder=5,
                )

            connection_ids = [
                str(value)
                for value in getattr(
                    agent,
                    "transit_connection_ids",
                    [],
                )
            ]

            physical_ids = (
                mapping.loc[
                    mapping[
                        "connection_id"
                    ].isin(
                        connection_ids
                    ),
                    "transit_physical_edge_id",
                ]
                .dropna()
                .astype(str)
                .unique()
                .tolist()
            )

            vehicle_edges = (
                transit_edges.loc[
                    transit_edges[
                        "transit_physical_edge_id"
                    ].isin(
                        physical_ids
                    )
                ]
            )

            if not vehicle_edges.empty:
                vehicle_edges.plot(
                    ax=ax,
                    color=color,
                    linewidth=2.0,
                    linestyle="solid",
                    alpha=0.96,
                    zorder=6,
                )

            if show_od:
                origin_node = getattr(
                    agent,
                    "origin_nodes",
                    {},
                ).get("walk")
                destination_node = getattr(
                    agent,
                    "destination_nodes",
                    {},
                ).get("walk")

                if (
                    origin_node is not None
                    and int(origin_node)
                    in walk_graph.nodes
                ):
                    node = walk_graph.nodes[
                        int(origin_node)
                    ]
                    ax.scatter(
                        [node["x"]],
                        [node["y"]],
                        marker="x",
                        s=65,
                        color=[color],
                        linewidths=1.8,
                        zorder=8,
                    )

                if (
                    destination_node
                    is not None
                    and int(
                        destination_node
                    )
                    in walk_graph.nodes
                ):
                    node = walk_graph.nodes[
                        int(
                            destination_node
                        )
                    ]
                    ax.scatter(
                        [node["x"]],
                        [node["y"]],
                        marker="o",
                        s=50,
                        facecolors="none",
                        edgecolors=[color],
                        linewidths=1.8,
                        zorder=8,
                    )

    apply_study_area_view(
        ax,
        study_area,
    )

    if show_od:
        _add_od_marker_legend(
            ax
        )

    ax.set_title(
        f"Trajetória individual dos agentes — n={len(agents)}"
    )
    ax.set_axis_off()

    return fig, ax


def plot_mode_frequency_by_income(
    *,
    choice_summary: pd.DataFrame,
):
    """Gráfico de barras da frequência modal por classe social.

    O eixo X representa os modos de viagem. Para cada modo são mostradas
    barras lado a lado para baixa, média e alta renda. As cores seguem a mesma
    paleta usada nos mapas.
    """

    required_columns = {
        "income_group",
        "mode",
    }

    missing = (
        required_columns
        - set(choice_summary.columns)
    )

    if missing:
        raise KeyError(
            "Colunas ausentes para o gráfico modal: "
            f"{sorted(missing)}"
        )

    # Reindexação explícita mantém as mesmas categorias entre rodadas,
    # inclusive quando uma combinação classe x modo não aparece.
    modes = [
        "walk",
        "bike",
        "car",
        "transit",
    ]
    incomes = [
        "low",
        "middle",
        "high",
    ]

    counts = (
        choice_summary.groupby(
            [
                "mode",
                "income_group",
            ]
        )
        .size()
        .unstack(
            fill_value=0
        )
        .reindex(
            index=modes,
            columns=incomes,
            fill_value=0,
        )
    )

    fig, ax = plt.subplots(
        figsize=(10, 6)
    )
    _set_map_background(
        fig,
        ax,
    )

    x = list(
        range(
            len(modes)
        )
    )
    width = 0.24
    offsets = {
        "low": -width,
        "middle": 0.0,
        "high": width,
    }

    for income in incomes:
        values = counts[
            income
        ].tolist()

        ax.bar(
            [
                value
                + offsets[income]
                for value in x
            ],
            values,
            width=width,
            color=INCOME_COLORS[
                income
            ],
            label=INCOME_LABELS[
                income
            ],
        )

    ax.set_xticks(
        x,
        [
            MODE_LABELS[
                mode
            ]
            for mode in modes
        ],
    )
    ax.set_ylabel(
        "Número de agentes"
    )
    ax.set_xlabel(
        "Modo de viagem"
    )
    ax.set_title(
        "Frequência dos modos de viagem por classe social"
    )
    ax.legend(
        title="Classe social",
        frameon=True,
    )
    ax.grid(
        axis="y",
        color="#E6E6E6",
        linewidth=0.8,
        alpha=0.8,
    )
    ax.set_axisbelow(
        True
    )

    fig.tight_layout()

    return fig, ax


def _selected_street_geometry(
    *,
    network_edges: Mapping[str, gpd.GeoDataFrame],
    selected_street: str,
):
    """Constrói a geometria de referência da rua escolhida.

    São combinados segmentos com o mesmo nome em walk, bike e car. Essa união
    ajuda a representar ruas que aparecem de forma ligeiramente diferente nas
    redes modais do OSM.
    """

    pieces = []

    for edges in network_edges.values():
        if (
            edges is None
            or edges.empty
            or "name" not in edges.columns
        ):
            continue

        mask = street_mask(
            edges,
            street_name=selected_street,
            name_column="name",
        )

        selected = edges.loc[
            mask
        ]

        if not selected.empty:
            pieces.extend(
                selected.geometry.tolist()
            )

    if not pieces:
        raise ValueError(
            f"A rua '{selected_street}' não foi encontrada nas redes da região."
        )

    return gpd.GeoSeries(
        pieces,
        crs=next(
            edges.crs
            for edges in network_edges.values()
            if edges is not None
            and not edges.empty
        ),
    ).unary_union


def _transit_overlaps_selected_street(
    geometry,
    *,
    street_corridor,
) -> bool:
    """Identifica trechos de ônibus que percorrem a rua, não apenas a cruzam."""

    if (
        geometry is None
        or geometry.is_empty
        or geometry.length <= 0
    ):
        return False

    overlap = geometry.intersection(
        street_corridor
    )

    if overlap.is_empty:
        return False

    overlap_length = float(
        overlap.length
    )
    ratio = (
        overlap_length
        / float(geometry.length)
    )

    # O critério combinado evita classificar como uso da rua uma linha de
    # ônibus que apenas a cruza perpendicularmente em um ponto.
    return (
        overlap_length >= 8.0
        and ratio >= 0.25
    )


def _street_usage_subset(
    *,
    usage_geometry: gpd.GeoDataFrame,
    selected_street: str,
    street_geometry,
) -> gpd.GeoDataFrame:
    """Filtra os registros de uso efetivamente associados à rua escolhida."""

    if usage_geometry.empty:
        return usage_geometry.copy()

    target = selected_street.casefold()

    road_mask = usage_geometry.apply(
        lambda row: (
            str(
                row.get(
                    "network_mode",
                    "",
                )
            )
            != "transit"
            and any(
                name.casefold()
                == target
                for name in (
                    row.get(
                        "street_names",
                        [],
                    )
                    or []
                )
            )
        ),
        axis=1,
    )

    # O buffer é apenas um corredor cartográfico para reconhecer ônibus que
    # percorrem a rua. Como o CRS do piloto é métrico, 12 significa 12 metros.
    street_corridor = street_geometry.buffer(
        12.0
    )

    transit_mask = usage_geometry.apply(
        lambda row: (
            str(
                row.get(
                    "network_mode",
                    "",
                )
            )
            == "transit"
            and _transit_overlaps_selected_street(
                row.geometry,
                street_corridor=street_corridor,
            )
        ),
        axis=1,
    )

    return usage_geometry.loc[
        road_mask
        | transit_mask
    ].copy()


def _plot_selected_street_legend(
    ax,
    counts: pd.DataFrame,
) -> None:
    """Legenda classe x modo com número de agentes únicos que usaram a rua."""

    handles = []

    for row in counts.itertuples(
        index=False
    ):
        income = str(
            row.income_group
        )
        mode = str(
            row.network_mode
        )
        n_agents = int(
            row.n_agents
        )

        kwargs = {
            "color": INCOME_COLORS.get(
                income,
                MAP_NEUTRAL,
            ),
            "linewidth": 2.5,
            "linestyle": MODE_LINESTYLES.get(
                mode,
                "solid",
            ),
            "label": (
                f"{INCOME_LABELS.get(income, income)} · "
                f"{MODE_LABELS.get(mode, mode)} — "
                f"{n_agents} agente"
                f"{'s' if n_agents != 1 else ''}"
            ),
        }

        if mode == "transit":
            kwargs.update(
                marker=">",
                markersize=6,
                markevery=[1],
            )

        handles.append(
            Line2D(
                [0, 1],
                [0, 0],
                **kwargs,
            )
        )

    if handles:
        ax.legend(
            handles=handles,
            title="Classe · modo · agentes",
            loc="upper right",
            frameon=True,
        )


def plot_selected_street_usage(
    *,
    selected_street: str,
    usage_geometry: gpd.GeoDataFrame,
    network_edges: Mapping[str, gpd.GeoDataFrame],
    transit_physical_edges: gpd.GeoDataFrame,
    study_area: StudyArea | None,
):
    """Mapa da rua selecionada com classe, modo e contagem de agentes.

    Cor identifica a classe social. O tipo de linha identifica o modo:
    contínua=carro, pontilhada=walk, tracejada=bike e contínua com pequenas
    setas=transporte público.
    """

    street_geometry = (
        _selected_street_geometry(
            network_edges=network_edges,
            selected_street=selected_street,
        )
    )

    street_usage = (
        _street_usage_subset(
            usage_geometry=usage_geometry,
            selected_street=selected_street,
            street_geometry=street_geometry,
        )
    )

    fig, ax = plt.subplots(
        figsize=(11, 8)
    )
    _set_map_background(
        fig,
        ax,
    )

    # Mantém as redes como contexto espacial fraco.
    _plot_network_context(
        ax,
        network_edges=network_edges,
        transit_physical_edges=transit_physical_edges,
        strong=False,
    )

    # A rua escolhida recebe um traço neutro um pouco mais espesso para que seu
    # percurso completo seja reconhecível mesmo nos trechos sem agentes.
    gpd.GeoSeries(
        [street_geometry],
        crs=usage_geometry.crs
        if usage_geometry.crs is not None
        else study_area.crs,
    ).plot(
        ax=ax,
        color="#8A8A8A",
        linewidth=2.2,
        alpha=0.75,
        zorder=2,
    )

    if not street_usage.empty:
        _plot_styled_edge_usage(
            ax,
            street_usage,
            force_solid=False,
        )

        counts = (
            street_usage.groupby(
                [
                    "income_group",
                    "network_mode",
                ],
                dropna=False,
            )["agent_id"]
            .nunique()
            .reset_index(
                name="n_agents"
            )
            .sort_values(
                [
                    "income_group",
                    "network_mode",
                ]
            )
        )

        _plot_selected_street_legend(
            ax,
            counts,
        )
    else:
        _annotate_no_simulated_routes(
            ax,
            message=(
                "Nenhum agente da rodada utilizou esta rua."
            ),
        )

    # O enquadramento usa a própria rua, não a região inteira, para dar escala
    # suficiente à leitura dos trechos e estilos de linha.
    minx, miny, maxx, maxy = (
        street_geometry.bounds
    )
    width = max(
        maxx - minx,
        100.0,
    )
    height = max(
        maxy - miny,
        100.0,
    )
    margin = max(
        width,
        height,
    ) * 0.12

    ax.set_xlim(
        minx - margin,
        maxx + margin,
    )
    ax.set_ylim(
        miny - margin,
        maxy + margin,
    )

    ax.set_title(
        f"Uso da rua — {selected_street}"
    )
    ax.set_axis_off()

    return fig, ax


def _safe_street_filename(
    street_name: str,
) -> str:
    """Cria nome de arquivo legível e seguro a partir do nome da rua."""

    normalized = unicodedata.normalize(
        "NFKD",
        street_name,
    ).encode(
        "ascii",
        "ignore",
    ).decode(
        "ascii"
    )

    slug = re.sub(
        r"[^A-Za-z0-9]+",
        "_",
        normalized,
    ).strip(
        "_"
    ).lower()

    return (
        slug
        or "rua"
    )


def generate_selected_plots(
    *,
    output_dir: str | Path,
    selected_plots: tuple[str, ...],
    agents,
    graphs: Mapping[str, nx.MultiDiGraph],
    edge_usage: pd.DataFrame,
    choice_summary: pd.DataFrame,
    transit_physical_edges: gpd.GeoDataFrame,
    connection_to_physical_edge,
    census_sectors: gpd.GeoDataFrame,
    study_area: StudyArea | None,
    selected_street: str | None = None,
) -> dict[str, Path]:
    """Gera somente os produtos selecionados pelo usuário na interface.

    Alguns itens da GUI representam grupos de arquivos. Por exemplo,
    mode_all_incomes produz quatro mapas, um para cada modo.
    """

    plots_dir = (
        Path(output_dir)
        / "plots"
    )
    plots_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    selected = set(
        selected_plots
    )

    # Estas conversões são custosas e por isso são feitas uma única vez.
    network_edges = (
        _network_edges_for_plot(
            graphs
        )
    )

    usage_geometry = (
        _edge_usage_geometry(
            edge_usage=edge_usage,
            graphs=graphs,
            transit_physical_edges=transit_physical_edges,
        )
        if not edge_usage.empty
        else gpd.GeoDataFrame(
            columns=[
                "agent_id",
                "income_group",
                "trip_mode",
                "network_mode",
                "edge_id",
                "geometry",
            ],
            geometry="geometry",
            crs=(
                study_area.crs
                if study_area is not None
                else None
            ),
        )
    )

    generated: dict[str, Path] = {}

    # 1. Um mapa para cada modo, com todas as classes sociais por cor.
    if "mode_all_incomes" in selected:
        for trip_mode in (
            "walk",
            "bike",
            "car",
            "transit",
        ):
            fig, _ = (
                plot_mandatory_mode_all_incomes(
                    usage_geometry=usage_geometry,
                    network_edges=network_edges,
                    transit_physical_edges=transit_physical_edges,
                    trip_mode=trip_mode,
                    study_area=study_area,
                )
            )
            path = (
                plots_dir
                / f"01_mode_{trip_mode}_all_incomes.png"
            )
            save_plot(
                fig,
                path,
            )
            plt.close(
                fig
            )
            generated[
                f"mode_{trip_mode}_all_incomes"
            ] = path

    # 2–5. Um mapa para cada classe dentro de um modo específico.
    grouped_modes = {
        "bike_by_income": (
            "02",
            "bike",
        ),
        "walk_by_income": (
            "03",
            "walk",
        ),
        "car_by_income": (
            "04",
            "car",
        ),
        "transit_by_income": (
            "05",
            "transit",
        ),
    }

    for selection_name, (
        order,
        trip_mode,
    ) in grouped_modes.items():
        if selection_name not in selected:
            continue

        for income_group in (
            "low",
            "middle",
            "high",
        ):
            fig, _ = (
                plot_mandatory_mode_income(
                    usage_geometry=usage_geometry,
                    network_edges=network_edges,
                    transit_physical_edges=transit_physical_edges,
                    trip_mode=trip_mode,
                    income_group=income_group,
                    study_area=study_area,
                )
            )
            path = (
                plots_dir
                / (
                    f"{order}_{trip_mode}_"
                    f"{income_group}.png"
                )
            )
            save_plot(
                fig,
                path,
            )
            plt.close(
                fig
            )
            generated[
                f"{trip_mode}_{income_group}"
            ] = path

    # 6. Região com setores censitários em gradiente de renda.
    if "census_income" in selected:
        fig, _ = (
            plot_census_income_gradient(
                census_sectors=census_sectors,
                network_edges=network_edges,
                transit_physical_edges=transit_physical_edges,
                study_area=study_area,
            )
        )
        path = (
            plots_dir
            / "06_census_income_gradient.png"
        )
        save_plot(
            fig,
            path,
        )
        plt.close(
            fig
        )
        generated[
            "census_income_gradient"
        ] = path

    # 7. Censo + todos os modos contínuos com classe social por cor.
    if "census_all_modes" in selected:
        fig, _ = (
            plot_census_plus_all_modes(
                census_sectors=census_sectors,
                usage_geometry=usage_geometry,
                network_edges=network_edges,
                transit_physical_edges=transit_physical_edges,
                study_area=study_area,
            )
        )
        path = (
            plots_dir
            / "07_census_plus_all_modes.png"
        )
        save_plot(
            fig,
            path,
        )
        plt.close(
            fig
        )
        generated[
            "census_plus_all_modes"
        ] = path

    # 8. Todas as redes em cinza forte.
    if "all_networks" in selected:
        fig, _ = plot_all_networks(
            network_edges=network_edges,
            transit_physical_edges=transit_physical_edges,
            study_area=study_area,
        )
        path = (
            plots_dir
            / "08_all_networks.png"
        )
        save_plot(
            fig,
            path,
        )
        plt.close(
            fig
        )
        generated[
            "all_networks"
        ] = path

    # 9. Uma cor distinta por agente. Este item só é gerado quando n < 40.
    if (
        "agent_unique" in selected
        and len(agents) < 40
    ):
        fig, _ = (
            plot_agent_routes_unique_colors(
                agents=agents,
                graphs=graphs,
                network_edges=network_edges,
                transit_physical_edges=transit_physical_edges,
                connection_to_physical_edge=(
                    connection_to_physical_edge
                ),
                study_area=study_area,
            )
        )

        if fig is not None:
            path = (
                plots_dir
                / "09_agent_routes_unique_colors.png"
            )
            save_plot(
                fig,
                path,
            )
            plt.close(
                fig
            )
            generated[
                "agent_routes_unique_colors"
            ] = path

    # 10. Gráfico de barras: frequência de cada modo por classe social.
    if "mode_frequency_by_income" in selected:
        fig, _ = (
            plot_mode_frequency_by_income(
                choice_summary=choice_summary,
            )
        )
        path = (
            plots_dir
            / "10_mode_frequency_by_income.png"
        )
        save_plot(
            fig,
            path,
        )
        plt.close(
            fig
        )
        generated[
            "mode_frequency_by_income"
        ] = path

    # 11. Rua selecionada: classe social, modo e contagem de agentes.
    if "selected_street_usage" in selected:
        if not selected_street:
            raise ValueError(
                "O mapa 11 foi selecionado, mas nenhuma rua foi informada."
            )

        fig, _ = plot_selected_street_usage(
            selected_street=selected_street,
            usage_geometry=usage_geometry,
            network_edges=network_edges,
            transit_physical_edges=transit_physical_edges,
            study_area=study_area,
        )

        path = (
            plots_dir
            / (
                "11_selected_street_"
                + _safe_street_filename(
                    selected_street
                )
                + ".png"
            )
        )
        save_plot(
            fig,
            path,
        )
        plt.close(
            fig
        )
        generated[
            "selected_street_usage"
        ] = path

    return generated

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
