"""Filtros espaciais reutilizáveis para recortes regionais.

As funções deste módulo não conhecem nomes de regiões. Elas recebem apenas
uma StudyArea, mantendo o restante do pipeline desacoplado das regras
territoriais.
"""

from __future__ import annotations

import geopandas as gpd

from src.spatial.study_area import StudyArea


def filter_points_to_study_area(
    data: gpd.GeoDataFrame,
    study_area: StudyArea,
) -> gpd.GeoDataFrame:
    """Retorna somente pontos contidos ou sobre o limite da área de estudo."""

    _validate_geodataframe(data, source_name="dados espaciais")

    projected = _match_crs(data, study_area)
    mask = projected.geometry.map(study_area.geometry.covers)

    return projected.loc[mask].copy()


def _match_crs(
    data: gpd.GeoDataFrame,
    study_area: StudyArea,
) -> gpd.GeoDataFrame:
    if data.crs == study_area.crs:
        return data.copy()

    return data.to_crs(study_area.crs)


def _validate_geodataframe(
    data: gpd.GeoDataFrame,
    *,
    source_name: str,
) -> None:
    if data.empty:
        raise ValueError(f"{source_name} está vazio.")

    if data.crs is None:
        raise ValueError(f"{source_name} não possui CRS definido.")

    if data.geometry.isna().all():
        raise ValueError(
            f"{source_name} não possui geometrias válidas."
        )
