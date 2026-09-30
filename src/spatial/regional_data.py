"""Preparação dos dados espaciais de uma execução regional."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import geopandas as gpd
import networkx as nx

from src.spatial.filtering import filter_points_to_study_area
from src.spatial.network_clip import clip_modal_graphs
from src.spatial.study_area import StudyArea


@dataclass(frozen=True, slots=True)
class RegionalData:
    """Dados espaciais já recortados e prontos para etapas posteriores."""

    study_area: StudyArea
    origins: gpd.GeoDataFrame
    destinations: gpd.GeoDataFrame
    graphs: dict[str, nx.MultiDiGraph]


def prepare_regional_data(
    *,
    study_area: StudyArea,
    origins: gpd.GeoDataFrame,
    destinations: gpd.GeoDataFrame,
    graphs: Mapping[str, nx.MultiDiGraph],
    network_buffer_m: float = 0.0,
) -> RegionalData:
    """Filtra O/D e recorta redes modais de forma coordenada."""

    regional_origins = filter_points_to_study_area(
        origins,
        study_area,
    )
    regional_destinations = filter_points_to_study_area(
        destinations,
        study_area,
    )
    regional_graphs = clip_modal_graphs(
        graphs,
        study_area,
        buffer_m=network_buffer_m,
    )

    if regional_origins.empty:
        raise ValueError(
            f"Nenhuma origem encontrada na região '{study_area.name}'."
        )

    if regional_destinations.empty:
        raise ValueError(
            f"Nenhum destino encontrado na região '{study_area.name}'."
        )

    return RegionalData(
        study_area=study_area,
        origins=regional_origins,
        destinations=regional_destinations,
        graphs=regional_graphs,
    )
