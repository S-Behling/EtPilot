#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Pipeline de download e preparação dos dados do piloto EtPilot.

A variável socioeconômica principal é a renda por setor censitário.
Os bairros permanecem como camada territorial de apoio, enquanto a
renda é associada diretamente à unidade espacial mais detalhada.

Fluxo:
1. Carrega a configuração do projeto.
2. Baixa e salva a rede viária de Porto Alegre e do bairro-piloto.
3. Baixa a malha de setores censitários e a renda por setor.
4. Baixa a malha de bairros.
5. Sobrepõe setores x bairros preservando a renda do SETOR.
6. Constrói o limite municipal.
7. Baixa os agregados básicos do Censo 2022.
8. Gera tabelas estatísticas de renda por bairro e setor.
9. Gera GeoPackages e os três mapas do piloto.

Execute a partir de qualquer diretório:
    python scripts/downloads.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# ============================================================
# RAIZ DO PROJETO
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Imports locais devem vir depois da inclusão da raiz no sys.path.
import geopandas as gpd
import osmnx as ox
import pandas as pd

from src import converters
from src.data_utils import (
    build_municipal_boundary,
    download_file,
    extract_zip,
    load_basic_sector_data,
    load_income_sectors,
    load_neighborhood_geometry,
    load_sector_geometry,
)
from src.downloads.downloadNetwork import (
    download_neighborhood_network,
    download_network,
)
from src.income_statistics import export_neighborhood_income_tables
from src.visualization import generate_pilot_maps


# ============================================================
# CONFIGURAÇÃO
# ============================================================

CONFIG_PATH = PROJECT_ROOT / "config" / "config.json"

with CONFIG_PATH.open("r", encoding="utf-8") as config_file:
    config = json.load(config_file)

STUDY_AREA = config["study_area"]
MUNICIPALITY_CODE = str(
    config.get("study_area_code", STUDY_AREA["cod_municipio"])
)
UF = config["uf"]

CRS = STUDY_AREA["crs"]
CITY = STUDY_AREA["place"]
NETWORK_TYPE = STUDY_AREA.get("network_type", "drive")
NEIGHBORHOOD = STUDY_AREA["districts"][0]

INCOME_VARIABLE = config["income_variable"]
INCOME_WEIGHT = config["income_weight"]
RESIDENTS_VARIABLE = config["residents_variable"]

BASIC_POPULATION_VARIABLE = config["basic_population_variable"]
BASIC_AVG_HOUSEHOLD_SIZE_VARIABLE = (
    config["basic_avg_household_size_variable"]
)
BASIC_HOUSEHOLDS_VARIABLE = config["basic_households_variable"]


# ============================================================
# DIRETÓRIOS
# ============================================================

DATA_DIR = PROJECT_ROOT / config.get("paths", {}).get("data", "data")
CENSUS_DIR = DATA_DIR / "censo_2022"
GRAPH_DIR = PROJECT_ROOT / config.get("paths", {}).get(
    "graphs", "data/graph"
)
OUTPUT_DIR = PROJECT_ROOT / "outputs"
TABLES_DIR = OUTPUT_DIR / "tabelas"

for directory in [
    CENSUS_DIR,
    GRAPH_DIR,
    OUTPUT_DIR,
    TABLES_DIR,
]:
    directory.mkdir(parents=True, exist_ok=True)

OUTPUT_GPKG = CENSUS_DIR / "bairros_setores_renda.gpkg"


# ============================================================
# URLS — IBGE CENSO 2022
# ============================================================

URL_INCOME_SECTORS = (
    "https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/"
    "Agregados_por_Setores_Censitarios_Rendimento_do_Responsavel/"
    "Agregados_por_setores_renda_responsavel_BR_20260508_csv.zip"
)

URL_SECTORS = (
    "https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/"
    "Agregados_por_Setores_Censitarios/"
    f"malha_com_atributos/setores/shp/UF/{UF}/"
    f"{UF}_setores_CD2022.zip"
)

URL_NEIGHBORHOODS = (
    "https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/"
    "Agregados_por_Setores_Censitarios/"
    f"malha_com_atributos/bairros/shp/UF/{UF}/"
    f"{UF}_bairros_CD2022.zip"
)

URL_BASIC_AGGREGATES = (
    "https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/"
    "Agregados_por_Setores_Censitarios/"
    "Agregados_por_Setor_csv/"
    "Agregados_por_setores_basico_BR_20260520.zip"
)


# ============================================================
# FUNÇÕES AUXILIARES DO PIPELINE
# ============================================================

def download_overwrite(url: str, destination: Path) -> Path:
    """
    Baixa o arquivo sempre e sobrescreve a cópia local existente.

    O download é feito em um arquivo temporário e só depois substitui
    o destino, reduzindo o risco de deixar um arquivo parcial.
    """
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    temporary = destination.with_suffix(
        destination.suffix + ".download"
    )

    if temporary.exists():
        temporary.unlink()

    if destination.exists():
        print(f"[OVERWRITE] Atualizando: {destination.name}")
    else:
        print(f"[DOWNLOAD] {destination.name}")

    try:
        download_file(
            url=url,
            destination=temporary,
        )
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()

    print(f"[OK] Salvo em: {destination}")
    return destination


def normalize_code(series: pd.Series) -> pd.Series:
    """Normaliza códigos do IBGE como texto."""
    return (
        series.astype("string")
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )


def merge_sector_income(
    sectors: gpd.GeoDataFrame,
    income: pd.DataFrame,
) -> gpd.GeoDataFrame:
    """
    Associa a renda oficial por setor censitário à malha de setores.

    A variável definida em config.json por income_variable recebe também
    o alias RENDA_MED_SETOR para deixar explícita a unidade espacial.
    """
    sectors = sectors.copy()
    income = income.copy()

    sectors["CD_SETOR"] = normalize_code(
        sectors["CD_SETOR"]
    )
    income["CD_SETOR"] = normalize_code(
        income["CD_SETOR"]
    )

    income_columns = [
        column
        for column in income.columns
        if column == "CD_SETOR"
        or column.startswith("V06")
    ]

    sectors = sectors.merge(
        income[income_columns],
        on="CD_SETOR",
        how="left",
        validate="one_to_one",
    )

    sectors["RENDA_MED_SETOR"] = pd.to_numeric(
        sectors[INCOME_VARIABLE],
        errors="coerce",
    )

    sectors["AREA_SETOR_M2"] = sectors.geometry.area

    missing = sectors["RENDA_MED_SETOR"].isna().sum()

    if missing:
        print(
            f"[AVISO] {missing} setor(es) sem valor de renda "
            "após a junção."
        )

    return sectors


def overlay_sectors_neighborhoods(
    sectors_with_income: gpd.GeoDataFrame,
    neighborhoods: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """
    Recorta os setores pelos limites dos bairros.

    A renda permanece vinculada ao setor censitário. Quando um setor
    cruza um limite de bairro, seus fragmentos mantêm o mesmo valor
    RENDA_MED_SETOR; nenhuma renda de bairro é atribuída.
    """
    setores = sectors_with_income.copy()
    bairros = neighborhoods.copy()

    setores["CD_SETOR"] = normalize_code(
        setores["CD_SETOR"]
    )

    if "CD_BAIRRO" in bairros.columns:
        bairros["CD_BAIRRO"] = normalize_code(
            bairros["CD_BAIRRO"]
        )

    sector_columns = [
        "CD_SETOR",
        "RENDA_MED_SETOR",
        "AREA_SETOR_M2",
        "geometry",
    ]

    for column in setores.columns:
        if (
            column.startswith("V06")
            and column not in sector_columns
        ):
            sector_columns.insert(-1, column)

    neighborhood_columns = [
        column
        for column in [
            "CD_BAIRRO",
            "NM_BAIRRO",
            "geometry",
        ]
        if column in bairros.columns
    ]

    print("[OVERLAY] Intersectando setores x bairros...")

    result = gpd.overlay(
        setores[sector_columns],
        bairros[neighborhood_columns],
        how="intersection",
        keep_geom_type=False,
    )

    result = result.loc[
        result.geometry.geom_type.isin(
            ["Polygon", "MultiPolygon"]
        )
    ].copy()

    result["AREA_FRAG_M2"] = result.geometry.area
    result["FRAC_AREA_SETOR"] = (
        result["AREA_FRAG_M2"]
        / result["AREA_SETOR_M2"]
    )

    result = result.loc[
        result["AREA_FRAG_M2"] > 1.0
    ].copy()

    return result


def save_individual_outputs(
    sectors_with_income: gpd.GeoDataFrame,
    neighborhoods: gpd.GeoDataFrame,
    municipal_boundary: gpd.GeoDataFrame,
) -> None:
    """Sobrescreve os GeoPackages individuais usados nos notebooks."""
    output_specs = [
        (
            CENSUS_DIR / "setores_poa.gpkg",
            sectors_with_income,
            "setores_renda",
        ),
        (
            CENSUS_DIR / "bairros_poa.gpkg",
            neighborhoods,
            "bairros",
        ),
        (
            CENSUS_DIR / "limite_poa.gpkg",
            municipal_boundary,
            "limite_poa",
        ),
    ]

    for output_path, gdf, layer in output_specs:
        if output_path.exists():
            output_path.unlink()

        gdf.to_file(
            output_path,
            layer=layer,
            driver="GPKG",
        )


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    print("=" * 70)
    print("ETPILOT | DOWNLOAD E PREPARAÇÃO DOS DADOS")
    print("=" * 70)
    print(f"Área de estudo: {CITY}")
    print(f"Código IBGE: {MUNICIPALITY_CODE}")
    print(f"Bairro-piloto: {NEIGHBORHOOD}")
    print(f"CRS: {CRS}")
    print()

    # --------------------------------------------------------
    # 1. REDE VIÁRIA
    # --------------------------------------------------------
    print("\n[1/9] Rede viária")

    network_graph = download_network(
        crs=CRS,
        city=CITY,
        network_type=NETWORK_TYPE,
    )

    neighborhood_graph = download_neighborhood_network(
        neighborhood=NEIGHBORHOOD,
        crs=CRS,
        city=CITY,
        network_type=NETWORK_TYPE,
    )

    city_graph_path = GRAPH_DIR / "rede-poa.graphml"
    neighborhood_graph_path = GRAPH_DIR / "rede-bomFim.graphml"

    for graph_path in [
        city_graph_path,
        neighborhood_graph_path,
    ]:
        if graph_path.exists():
            graph_path.unlink()

    ox.save_graphml(
        network_graph,
        filepath=city_graph_path,
    )
    ox.save_graphml(
        neighborhood_graph,
        filepath=neighborhood_graph_path,
    )

    print(f"[OK] Grafo municipal: {city_graph_path}")
    print(f"[OK] Grafo do bairro: {neighborhood_graph_path}")

    # --------------------------------------------------------
    # 2. MALHA DE SETORES + RENDA POR SETOR
    # --------------------------------------------------------
    print("\n[2/9] Malha de setores + renda por setor")

    sectors_dir = CENSUS_DIR / "setores"
    sectors_zip = sectors_dir / f"{UF.lower()}_setores.zip"

    download_overwrite(
        URL_SECTORS,
        sectors_zip,
    )

    sectors = load_sector_geometry(
        zip_path=sectors_zip,
        municipality_code=MUNICIPALITY_CODE,
        target_crs=CRS,
    )

    sectors["CD_SETOR"] = normalize_code(
        sectors["CD_SETOR"]
    )

    income_sectors_dir = CENSUS_DIR / "renda_setores"
    income_sectors_zip = (
        income_sectors_dir / "renda_setores.zip"
    )
    income_sectors_extract = (
        income_sectors_dir / "extracted"
    )

    download_overwrite(
        URL_INCOME_SECTORS,
        income_sectors_zip,
    )

    extract_zip(
        income_sectors_zip,
        income_sectors_extract,
        overwrite=True,
    )

    income_sectors = load_income_sectors(
        source_dir=income_sectors_extract,
        municipality_code=MUNICIPALITY_CODE,
        income_variable=INCOME_VARIABLE,
        income_weight=INCOME_WEIGHT,
        residents_variable=RESIDENTS_VARIABLE,
    )

    income_sectors.to_csv(
        CENSUS_DIR / "renda_setores_poa.csv",
        index=False,
        encoding="utf-8-sig",
    )

    sectors_with_income = merge_sector_income(
        sectors,
        income_sectors,
    )

    # --------------------------------------------------------
    # 3. MALHA DE BAIRROS
    # --------------------------------------------------------
    print("\n[3/9] Malha de bairros")

    neighborhoods_dir = CENSUS_DIR / "bairros"
    neighborhoods_zip = (
        neighborhoods_dir / f"{UF.lower()}_bairros.zip"
    )

    download_overwrite(
        URL_NEIGHBORHOODS,
        neighborhoods_zip,
    )

    neighborhoods = load_neighborhood_geometry(
        zip_path=neighborhoods_zip,
        municipality_code=MUNICIPALITY_CODE,
        target_crs=CRS,
    )

    # --------------------------------------------------------
    # 4. SETORES x BAIRROS
    # --------------------------------------------------------
    print("\n[4/9] Sobreposição setores x bairros")

    sectors_neighborhood_income = overlay_sectors_neighborhoods(
        sectors_with_income,
        neighborhoods,
    )

    # --------------------------------------------------------
    # 5. LIMITE MUNICIPAL
    # --------------------------------------------------------
    print("\n[5/9] Limite municipal")

    municipal_boundary = build_municipal_boundary(
        sectors_with_income,
        municipality_code=MUNICIPALITY_CODE,
        municipality_name=CITY,
    )

    # --------------------------------------------------------
    # 6. AGREGADOS BÁSICOS
    # --------------------------------------------------------
    print("\n[6/9] Agregados básicos")

    basic_dir = CENSUS_DIR / "agregados_basicos"
    basic_zip = basic_dir / "agregados_basicos.zip"
    basic_extract = basic_dir / "extracted"

    download_overwrite(
        URL_BASIC_AGGREGATES,
        basic_zip,
    )

    extract_zip(
        basic_zip,
        basic_extract,
        overwrite=True,
    )

    basic = load_basic_sector_data(
        source_dir=basic_extract,
        municipality_code=MUNICIPALITY_CODE,
        population_variable=BASIC_POPULATION_VARIABLE,
        avg_household_size_variable=(
            BASIC_AVG_HOUSEHOLD_SIZE_VARIABLE
        ),
        households_variable=BASIC_HOUSEHOLDS_VARIABLE,
    )

    basic.to_csv(
        CENSUS_DIR / "agregados_basicos_poa.csv",
        index=False,
        encoding="utf-8-sig",
    )

    # --------------------------------------------------------
    # 7. EXPORTAÇÃO
    # --------------------------------------------------------
    print("\n[7/9] Exportação")

    save_individual_outputs(
        sectors_with_income=sectors_with_income,
        neighborhoods=neighborhoods,
        municipal_boundary=municipal_boundary,
    )

    converters.export_gpkg(
        output_file=OUTPUT_GPKG,
        bairros=neighborhoods,
        setores=sectors_with_income,
        inter=sectors_neighborhood_income,
    )

    # --------------------------------------------------------
    # 8. TABELAS ESTATÍSTICAS
    # --------------------------------------------------------
    print("\n[8/9] Tabelas de renda por bairro e setor")

    generated_tables = export_neighborhood_income_tables(
        sector_neighborhood_fragments=sectors_neighborhood_income,
        output_dir=TABLES_DIR,
    )

    print("\nTabelas geradas/atualizadas:")
    for table_name, table_path in generated_tables.items():
        print(f" - {table_name}: {table_path}")

    # --------------------------------------------------------
    # 9. MAPAS DO PILOTO
    # --------------------------------------------------------
    print("\n[9/9] Geração dos mapas")

    generated_maps = generate_pilot_maps(
        income_regions=sectors_with_income,
        neighborhoods=neighborhoods,
        sectors=sectors_with_income,
        city_graph=network_graph,
        output_dir=OUTPUT_DIR,
        income_column="RENDA_MED_SETOR",
        boundary=municipal_boundary,
    )

    print("\nMapas gerados/atualizados:")
    for map_name, map_path in generated_maps.items():
        print(f" - {map_name}: {map_path}")

    print("\n" + "=" * 70)
    print("PIPELINE FINALIZADO")
    print("=" * 70)
    print(f"GeoPackage consolidado: {OUTPUT_GPKG}")
    print(f"Setores com renda: {len(sectors_with_income)}")
    print(f"Bairros: {len(neighborhoods)}")
    print(
        "Fragmentos setor-bairro: "
        f"{len(sectors_neighborhood_income)}"
    )
    print(
        "Setores sem renda: "
        f"{sectors_with_income['RENDA_MED_SETOR'].isna().sum()}"
    )
    print(f"Nós da rede municipal: {len(network_graph.nodes)}")
    print(f"Arestas da rede municipal: {len(network_graph.edges)}")


if __name__ == "__main__":
    main()
