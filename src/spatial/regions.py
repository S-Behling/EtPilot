"""Construção de áreas de estudo a partir de definições territoriais.

Este módulo possui uma única responsabilidade: transformar uma definição
configurada de região em um StudyArea. O restante do pipeline trabalha
somente com a geometria resultante.
"""

from __future__ import annotations

from collections.abc import Mapping
import re
import unicodedata

import geopandas as gpd

from src.spatial.study_area import StudyArea


MUNICIPALITY_STRATEGY = "municipality"
NEIGHBORHOOD_GROUP_STRATEGY = "neighborhood_group"


def build_study_area(
    *,
    region_name: str,
    regions_config: Mapping,
    municipality_boundary: gpd.GeoDataFrame,
    neighborhoods: gpd.GeoDataFrame | None = None,
) -> StudyArea:
    """Constrói a área de estudo correspondente a region_name."""

    definitions = regions_config.get("regions", {})

    if region_name not in definitions:
        available = ", ".join(sorted(definitions))
        raise KeyError(
            f"Região '{region_name}' não configurada. "
            f"Disponíveis: {available}"
        )

    definition = definitions[region_name]

    if not definition.get("enabled", False):
        raise ValueError(
            f"A região '{region_name}' está desabilitada em config/regions.json."
        )

    strategy = definition.get("strategy")
    label = definition.get("label", region_name)

    if strategy == MUNICIPALITY_STRATEGY:
        geometry, crs = _union_geometry(
            municipality_boundary,
            source_name="limite municipal",
        )
        source_neighborhoods: tuple[str, ...] = ()

    elif strategy == NEIGHBORHOOD_GROUP_STRATEGY:
        if neighborhoods is None:
            raise ValueError(
                "Uma malha de bairros é obrigatória para regiões "
                "do tipo 'neighborhood_group'."
            )

        name_field = definition.get(
            "name_field",
            regions_config.get("name_field", "NM_BAIRRO"),
        )
        selected_names = tuple(definition.get("neighborhoods", ()))

        if not selected_names:
            raise ValueError(
                f"A região '{region_name}' não possui bairros configurados."
            )

        selected = select_neighborhoods(
            neighborhoods=neighborhoods,
            names=selected_names,
            name_field=name_field,
            aliases=definition.get(
                "aliases",
                {},
            ),
        )

        geometry, crs = _union_geometry(
            selected,
            source_name=f"bairros da região {region_name}",
        )
        source_neighborhoods = selected_names

    else:
        raise ValueError(
            f"Estratégia territorial não suportada: {strategy!r}"
        )

    return StudyArea(
        name=region_name,
        label=label,
        geometry=geometry,
        crs=crs,
        source_neighborhoods=source_neighborhoods,
    )


def select_neighborhoods(
    *,
    neighborhoods: gpd.GeoDataFrame,
    names: tuple[str, ...],
    name_field: str,
    aliases: Mapping[str, list[str]] | None = None,
) -> gpd.GeoDataFrame:
    """Seleciona bairros por nome usando comparação sem diferença de caixa."""

    _validate_geodataframe(
        neighborhoods,
        source_name="malha de bairros",
    )

    resolved_name_field = resolve_neighborhood_name_field(
        neighborhoods,
        requested_field=name_field,
    )

    requested = {
        _normalize_name(name)
        for name in names
    }

    alias_to_requested: dict[str, str] = {}

    for canonical_name, alias_values in (
        aliases or {}
    ).items():
        canonical = _normalize_name(
            canonical_name
        )

        if canonical not in requested:
            continue

        for alias in alias_values:
            alias_to_requested[
                _normalize_name(alias)
            ] = canonical

    normalized = (
        neighborhoods[resolved_name_field]
        .astype("string")
        .map(_normalize_name)
    )

    matched = normalized.map(
        lambda value: (
            value
            if value in requested
            else alias_to_requested.get(value)
        )
    )

    selected = neighborhoods.loc[
        matched.notna()
    ].copy()

    found = set(
        matched.dropna()
    )
    missing = sorted(requested - found)

    if missing:
        raise ValueError(
            "Bairros configurados não encontrados na malha: "
            + ", ".join(missing)
        )

    return selected



def resolve_neighborhood_name_field(
    neighborhoods: gpd.GeoDataFrame,
    *,
    requested_field: str,
) -> str:
    """Resolve automaticamente a coluna que contém o nome do bairro.

    A malha oficial pode chegar com nomes de coluna diferentes conforme a
    versão/exportação. Primeiro tenta o campo configurado e depois procura
    alternativas usuais de forma determinística.
    """

    if requested_field in neighborhoods.columns:
        return requested_field

    columns = [
        column
        for column in neighborhoods.columns
        if column != neighborhoods.geometry.name
    ]

    normalized = {
        _normalize_name(column): column
        for column in columns
    }

    preferred = (
        _normalize_name(requested_field),
        "nm bairro",
        "nome bairro",
        "bairro",
        "nome",
        "name",
    )

    for candidate in preferred:
        if candidate in normalized:
            return normalized[candidate]

    bairro_candidates = [
        original
        for normalized_name, original
        in normalized.items()
        if "bairro" in normalized_name
    ]

    if len(bairro_candidates) == 1:
        return bairro_candidates[0]

    available = ", ".join(
        str(column)
        for column in neighborhoods.columns
    )

    if bairro_candidates:
        candidates_text = ", ".join(
            bairro_candidates
        )
        raise KeyError(
            "Não foi possível decidir automaticamente qual coluna contém "
            "o nome do bairro. Candidatas: "
            f"{candidates_text}. Colunas disponíveis: {available}"
        )

    raise KeyError(
        f"Coluna '{requested_field}' ausente na malha de bairros e nenhuma "
        "alternativa reconhecível foi encontrada. "
        f"Colunas disponíveis: {available}"
    )

def _union_geometry(
    gdf: gpd.GeoDataFrame,
    *,
    source_name: str,
):
    _validate_geodataframe(
        gdf,
        source_name=source_name,
    )

    valid = gdf.loc[gdf.geometry.notna()].copy()

    invalid = ~valid.geometry.is_valid
    if invalid.any():
        valid.loc[invalid, "geometry"] = (
            valid.loc[invalid, "geometry"].make_valid()
        )

    geometry = valid.geometry.union_all()

    if geometry.is_empty:
        raise ValueError(
            f"A união geométrica de {source_name} resultou vazia."
        )

    return geometry, valid.crs


def _validate_geodataframe(
    gdf: gpd.GeoDataFrame,
    *,
    source_name: str,
) -> None:
    if gdf.empty:
        raise ValueError(f"{source_name} está vazio.")

    if gdf.crs is None:
        raise ValueError(f"{source_name} não possui CRS definido.")

    if gdf.geometry.isna().all():
        raise ValueError(
            f"{source_name} não possui geometrias válidas para processamento."
        )


def _normalize_name(value: object) -> str:
    text = unicodedata.normalize(
        "NFKD",
        str(value),
    )
    text = "".join(
        character
        for character in text
        if not unicodedata.combining(
            character
        )
    )
    text = text.casefold()
    text = re.sub(
        r"[^a-z0-9]+",
        " ",
        text,
    )
    return " ".join(
        text.split()
    )
