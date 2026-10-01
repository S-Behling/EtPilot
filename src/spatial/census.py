"""Carregamento dos setores censitários com informação de renda.

Este módulo dá suporte aos mapas obrigatórios do piloto que usam os setores
do Censo 2022 como base espacial. A leitura, a classificação e o recorte
ficam aqui para manter a lógica censitária fora de plot.py.

A classificação de renda reutiliza classify_income_2022 porque esse foi o
mesmo critério usado no notebook que produziu a base de origens com
income_group. Assim, setores e agentes permanecem coerentes.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import geopandas as gpd
import pandas as pd

from src.classification import classify_income_2022
from src.core.config import project_path
from src.spatial.study_area import StudyArea


def load_census_income_sectors(
    config: Mapping,
    *,
    study_area: StudyArea | None = None,
) -> gpd.GeoDataFrame:
    """Carrega setores de Porto Alegre com renda e classe social."""

    census_config = config.get("census")

    if not census_config:
        raise KeyError(
            "Seção 'census' ausente em config/config.json."
        )

    sector_geometry_path = project_path(
        census_config["sector_geometry"]
    )
    income_directory = project_path(
        census_config["income_directory"]
    )

    _require_path(
        sector_geometry_path,
        label="geometria dos setores censitários",
    )
    _require_path(
        income_directory,
        label="diretório de renda do Censo",
    )

    income_file = _find_income_csv(
        income_directory
    )

    sector_id_column = census_config.get(
        "sector_id_column",
        "CD_SETOR",
    )
    income_column = census_config.get(
        "income_column",
        "V06004",
    )
    municipality_code = str(
        census_config.get(
            "municipality_code",
            config["study_area"]["cod_municipio"],
        )
    )
    target_income_column = census_config.get(
        "target_income_column",
        "renda_media_responsavel",
    )
    group_column = census_config.get(
        "income_group_column",
        "income_group",
    )

    # O GeoPandas lê diretamente o ZIP do IBGE com o prefixo zip://.
    sectors = gpd.read_file(
        f"zip://{sector_geometry_path}"
    )

    if sector_id_column not in sectors.columns:
        raise KeyError(
            f"Coluna '{sector_id_column}' ausente na geometria dos setores."
        )

    sectors = sectors.copy()
    sectors[sector_id_column] = (
        sectors[sector_id_column]
        .astype("string")
        .str.strip()
    )

    # Filtra Porto Alegre antes do merge para reduzir memória e tempo.
    sectors = sectors.loc[
        sectors[sector_id_column].str.startswith(
            municipality_code,
            na=False,
        )
    ].copy()

    income = pd.read_csv(
        income_file,
        sep=";",
        dtype={
            sector_id_column: "string",
        },
        low_memory=False,
    )

    missing_income_columns = {
        sector_id_column,
        income_column,
    } - set(income.columns)

    if missing_income_columns:
        raise KeyError(
            "Colunas ausentes na tabela de renda censitária: "
            f"{sorted(missing_income_columns)}"
        )

    income = income[
        [
            sector_id_column,
            income_column,
        ]
    ].copy()

    income[sector_id_column] = (
        income[sector_id_column]
        .astype("string")
        .str.strip()
    )

    income = income.loc[
        income[sector_id_column].str.startswith(
            municipality_code,
            na=False,
        )
    ].copy()

    income[target_income_column] = pd.to_numeric(
        income[income_column],
        errors="coerce",
    )

    income[group_column] = (
        income[target_income_column]
        .apply(classify_income_2022)
        .astype("string")
    )

    sectors = sectors.merge(
        income[
            [
                sector_id_column,
                target_income_column,
                group_column,
            ]
        ],
        on=sector_id_column,
        how="left",
        validate="one_to_one",
    )

    if study_area is not None:
        sectors = sectors.to_crs(
            study_area.crs
        )

        # Intersects preserva setores que cruzam a borda da região. O limite
        # visual continua sendo a StudyArea, mas o setor não é artificialmente
        # partido apenas para produzir o mapa.
        sectors = sectors.loc[
            sectors.geometry.intersects(
                study_area.geometry
            )
        ].copy()

    return sectors


def _find_income_csv(
    directory: Path,
) -> Path:
    """Encontra de forma determinística o CSV de renda por setor."""

    preferred = directory / (
        "Agregados_por_setores_renda_responsavel_BR.csv"
    )

    if preferred.exists():
        return preferred

    csv_files = sorted(
        directory.glob("*.csv")
    )

    if len(csv_files) == 1:
        return csv_files[0]

    if not csv_files:
        raise FileNotFoundError(
            "Nenhum CSV de renda foi encontrado em "
            f"{directory}."
        )

    raise FileNotFoundError(
        "Mais de um CSV de renda foi encontrado em "
        f"{directory}. Normalize o diretório antes de executar."
    )


def _require_path(
    path: Path,
    *,
    label: str,
) -> None:
    if not path.exists():
        raise FileNotFoundError(
            f"{label} não encontrado: {path}"
        )
