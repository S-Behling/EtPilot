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
