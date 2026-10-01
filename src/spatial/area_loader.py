"""Carregamento de uma StudyArea a partir da configuração do projeto."""

from __future__ import annotations

import geopandas as gpd

from src.core.config import (
    load_project_config,
    load_regions_config,
    project_path,
)
from src.spatial.regions import build_study_area
from src.spatial.study_area import StudyArea


def load_study_area(
    region_name: str,
    *,
    config: dict | None = None,
) -> StudyArea:
    """Constrói a região configurada usando a malha de bairros do projeto."""

    config = (
        config
        if config is not None
        else load_project_config()
    )
    regions_config = load_regions_config(config)

    neighborhoods = gpd.read_file(
        project_path(config["paths"]["neighborhoods"]),
        engine="pyogrio",
    )

    municipality_boundary = neighborhoods[
        ["geometry"]
    ].copy()

    return build_study_area(
        region_name=region_name,
        regions_config=regions_config,
        municipality_boundary=municipality_boundary,
        neighborhoods=neighborhoods,
    )
