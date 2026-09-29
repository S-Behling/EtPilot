#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Pipeline de download e preparação dos dados do piloto EtPilot.

Este script unifica os antigos scripts/downloadData.py e scripts/downloads.py
e passa a usar a RENDA OFICIAL POR BAIRRO como atributo socioeconômico do
piloto, em vez de atribuir a renda do setor censitário aos recortes.

Fluxo:
1. Carrega a configuração do projeto.
2. Baixa e salva a rede viária de Porto Alegre e do bairro-piloto.
3. Baixa a malha de setores censitários.
4. Baixa a malha de bairros e a renda oficial por bairro.
5. Sobrepõe setores x bairros, atribuindo a renda do BAIRRO aos fragmentos.
6. Constrói o limite municipal.
7. Baixa e extrai o CNEFE do município.
8. Baixa e extrai os microdados públicos do RS.
9. Baixa e extrai as tabelas das áreas de ponderação.
10. Gera um GeoPackage consolidado.
11. Gera os três mapas finais do piloto.

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

# Permite importar "src" quando o arquivo é executado diretamente
# a partir da pasta scripts/.
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
    load_neighborhood_geometry,
    load_sector_geometry,
)
from src.downloads.downloadDataCNEFE import (
    download_cnefe,
    ler_renda_bairros,
)
from src.downloads.downloadNetwork import (
    download_neighborhood_network,
    download_network,
)
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
UF_CODE = MUNICIPALITY_CODE[:2]
MUNICIPALITY_CNEFE_NAME = (
    CITY.split(",")[0]
    .strip()
    .upper()
    .replace(" ", "_")
)

INCOME_VARIABLE = config["income_variable"]

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

MICRODATA_DIR = CENSUS_DIR / "microdados_publicos"
WEIGHTING_AREAS_DIR = CENSUS_DIR / "areas_ponderacao"
CNEFE_DIR = CENSUS_DIR / "cnefe"

for directory in [
    CENSUS_DIR,
    GRAPH_DIR,
    MICRODATA_DIR,
    WEIGHTING_AREAS_DIR,
    CNEFE_DIR,
]:
    directory.mkdir(parents=True, exist_ok=True)

OUTPUT_GPKG = CENSUS_DIR / "bairros_setores_renda.gpkg"
OUTPUT_DIR = PROJECT_ROOT / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# URLS — IBGE CENSO 2022
# ============================================================

URL_INCOME_NEIGHBORHOODS = (
    "https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/"
    "Agregados_por_Setores_Censitarios_Rendimento_do_Responsavel/"
    "Agregados_por_bairros_renda_responsavel_BR_20260508_csv.zip"
)

CSV_INCOME_NEIGHBORHOODS = (
    "Agregados_por_bairros_renda_responsavel_BR.csv"
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

IBGE_CNEFE_BASE_URL = (
    "https://ftp.ibge.gov.br/"
    "Cadastro_Nacional_de_Enderecos_para_Fins_Estatisticos/"
    "Censo_Demografico_2022/"
    "Arquivos_CNEFE/CSV/Municipio"
)

URL_MICRODATA_UF = (
    "https://ftp.ibge.gov.br/"
    "Censos/Censo_Demografico_2022/"
    "Microdados_e_Areas_de_Ponderacao/"
    "Microdados_de_acesso_Publico/"
    "csv/"
    f"{UF_CODE}_{UF}.zip"
)

URL_WEIGHTING_AREAS_TABLES = (
    "https://ftp.ibge.gov.br/"
    "Censos/Censo_Demografico_2022/"
    "Microdados_e_Areas_de_Ponderacao/"
    "Areas_de_Ponderacao/"
    "tabelas_xlsx.zip"
)


# ============================================================
# FUNÇÕES AUXILIARES DO PIPELINE
# ============================================================

def download_if_missing(url: str, destination: Path) -> Path:
    """Baixa o arquivo apenas quando ele ainda não existe localmente."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    if destination.exists() and destination.stat().st_size > 0:
        print(f"[OK] Já existe: {destination}")
        return destination

    print(f"[DOWNLOAD] {destination.name}")
    download_file(url=url, destination=destination)
    print(f"[OK] Salvo em: {destination}")

    return destination


def normalize_code(series: pd.Series) -> pd.Series:
    """Normaliza códigos do IBGE como texto."""
    return (
        series.astype("string")
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )


def merge_neighborhood_income(
    neighborhoods: gpd.GeoDataFrame,
    income: pd.DataFrame,
) -> gpd.GeoDataFrame:
    """
    Associa o agregado oficial de renda por bairro à malha de bairros.

    A variável principal é definida em config.json por income_variable.
    Para o piloto atual, V06004 também fica disponível pelo alias
    RENDA_MED_BAIRRO.
    """
    neighborhoods = neighborhoods.copy()
    income = income.copy()

    neighborhoods["CD_BAIRRO"] = normalize_code(
        neighborhoods["CD_BAIRRO"]
    )
    income["CD_BAIRRO"] = normalize_code(income["CD_BAIRRO"])

    income_columns = [
        column
        for column in income.columns
        if column == "CD_BAIRRO"
        or column.startswith("V06")
        or column.startswith("RENDA_")
    ]

    # Evita duplicar o nome do bairro quando ele já existe na malha.
    if (
        "NM_BAIRRO" in income.columns
        and "NM_BAIRRO" not in neighborhoods.columns
        and "NM_BAIRRO" not in income_columns
    ):
        income_columns.append("NM_BAIRRO")

    neighborhoods = neighborhoods.merge(
        income[income_columns],
        on="CD_BAIRRO",
        how="left",
        validate="one_to_one",
    )

    if "RENDA_MED_BAIRRO" not in neighborhoods.columns:
        neighborhoods["RENDA_MED_BAIRRO"] = pd.to_numeric(
            neighborhoods[INCOME_VARIABLE],
            errors="coerce",
        )

    neighborhoods["AREA_BAIRRO_M2"] = neighborhoods.geometry.area

    missing = neighborhoods["RENDA_MED_BAIRRO"].isna().sum()

    if missing:
        print(
            f"[AVISO] {missing} bairro(s) sem valor de renda "
            "após a junção."
        )

    return neighborhoods


def overlay_sectors_neighborhoods(
    sectors: gpd.GeoDataFrame,
    neighborhoods: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """
    Recorta os setores pelos limites dos bairros.

    IMPORTANTE:
    a renda associada a cada fragmento é a renda oficial do BAIRRO.
    Não é feita interpolação da renda do setor pela proporção de área.
    """
    sectors = sectors.copy()
    neighborhoods = neighborhoods.copy()

    sectors["CD_SETOR"] = normalize_code(sectors["CD_SETOR"])
    sectors["AREA_SETOR_M2"] = sectors.geometry.area

    neighborhood_columns = [
        "CD_BAIRRO",
        "RENDA_MED_BAIRRO",
        "geometry",
    ]

    if "NM_BAIRRO" in neighborhoods.columns:
        neighborhood_columns.insert(1, "NM_BAIRRO")

    # Mantém as variáveis V060xx do agregado oficial por bairro.
    for column in neighborhoods.columns:
        if (
            column.startswith("V06")
            and column not in neighborhood_columns
        ):
            neighborhood_columns.insert(-1, column)

    sector_columns = [
        "CD_SETOR",
        "AREA_SETOR_M2",
        "geometry",
    ]

    print("[OVERLAY] Intersectando setores x bairros...")

    result = gpd.overlay(
        sectors[sector_columns],
        neighborhoods[neighborhood_columns],
        how="intersection",
        keep_geom_type=False,
    )

    # Contatos de borda podem gerar linhas ou pontos.
    result = result.loc[
        result.geometry.geom_type.isin(["Polygon", "MultiPolygon"])
    ].copy()

    result["AREA_FRAG_M2"] = result.geometry.area
    result["FRAC_AREA_SETOR"] = (
        result["AREA_FRAG_M2"] / result["AREA_SETOR_M2"]
    )

    # Remove apenas pequenos resíduos geométricos de borda.
    result = result.loc[result["AREA_FRAG_M2"] > 1.0].copy()

    return result


def save_individual_outputs(
    sectors: gpd.GeoDataFrame,
    neighborhoods_with_income: gpd.GeoDataFrame,
    municipal_boundary: gpd.GeoDataFrame,
) -> None:
    """Mantém arquivos individuais para uso nos notebooks."""
    sectors.to_file(
        CENSUS_DIR / "setores_poa.gpkg",
        layer="setores_poa",
        driver="GPKG",
    )

    neighborhoods_with_income.to_file(
        CENSUS_DIR / "bairros_poa.gpkg",
        layer="bairros_renda",
        driver="GPKG",
    )

    municipal_boundary.to_file(
        CENSUS_DIR / "limite_poa.gpkg",
        layer="limite_poa",
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
    print("\n[1/11] Rede viária")

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
    # 2. MALHA DE SETORES
    # --------------------------------------------------------
    print("\n[2/11] Malha de setores")

    sectors_dir = CENSUS_DIR / "setores"
    sectors_zip = sectors_dir / f"{UF.lower()}_setores.zip"

    download_if_missing(
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

    # --------------------------------------------------------
    # 3. MALHA + RENDA POR BAIRRO
    # --------------------------------------------------------
    print("\n[3/11] Bairros e renda oficial por bairro")

    neighborhoods_dir = CENSUS_DIR / "bairros"
    neighborhoods_zip = (
        neighborhoods_dir / f"{UF.lower()}_bairros.zip"
    )

    download_if_missing(
        URL_NEIGHBORHOODS,
        neighborhoods_zip,
    )

    neighborhoods = load_neighborhood_geometry(
        zip_path=neighborhoods_zip,
        municipality_code=MUNICIPALITY_CODE,
        target_crs=CRS,
    )

    income_neighborhoods_dir = CENSUS_DIR / "renda_bairros"
    income_neighborhoods_zip = (
        income_neighborhoods_dir / "renda_bairros.zip"
    )

    download_if_missing(
        URL_INCOME_NEIGHBORHOODS,
        income_neighborhoods_zip,
    )

    income_neighborhoods = ler_renda_bairros(
        zip_path=income_neighborhoods_zip,
        csv_renda_no_zip=CSV_INCOME_NEIGHBORHOODS,
        cod_city=MUNICIPALITY_CODE,
    )

    income_neighborhoods.to_csv(
        CENSUS_DIR / "renda_bairros_poa.csv",
        index=False,
        encoding="utf-8-sig",
    )

    neighborhoods_with_income = merge_neighborhood_income(
        neighborhoods,
        income_neighborhoods,
    )

    # --------------------------------------------------------
    # 4. SETORES x BAIRROS
    # --------------------------------------------------------
    print("\n[4/11] Sobreposição setores x bairros")

    sectors_neighborhood_income = overlay_sectors_neighborhoods(
        sectors,
        neighborhoods_with_income,
    )

    # --------------------------------------------------------
    # 5. LIMITE MUNICIPAL
    # --------------------------------------------------------
    print("\n[5/11] Limite municipal")

    municipal_boundary = build_municipal_boundary(
        sectors,
        municipality_code=MUNICIPALITY_CODE,
        municipality_name=CITY,
    )

    # --------------------------------------------------------
    # 6. AGREGADOS BÁSICOS
    # --------------------------------------------------------
    print("\n[6/11] Agregados básicos")

    basic_dir = CENSUS_DIR / "agregados_basicos"
    basic_zip = basic_dir / "agregados_basicos.zip"
    basic_extract = basic_dir / "extracted"

    download_if_missing(
        URL_BASIC_AGGREGATES,
        basic_zip,
    )

    extract_zip(
        basic_zip,
        basic_extract,
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
    # 7. CNEFE
    # --------------------------------------------------------
    print("\n[7/11] CNEFE")

    cnefe_csv_path = download_cnefe(
        url=IBGE_CNEFE_BASE_URL,
        cod_uf=UF_CODE,
        uf=UF,
        cod_municipio=MUNICIPALITY_CODE,
        municipio_nome=MUNICIPALITY_CNEFE_NAME,
        output_dir=CNEFE_DIR,
    )

    print(f"[OK] CNEFE extraído: {cnefe_csv_path}")

    # --------------------------------------------------------
    # 8. MICRODADOS PÚBLICOS DO RS
    # --------------------------------------------------------
    print("\n[8/11] Microdados públicos do RS")

    microdata_name = f"{UF_CODE}_{UF}"
    microdata_zip = MICRODATA_DIR / f"{microdata_name}.zip"
    microdata_extract = MICRODATA_DIR / microdata_name

    download_if_missing(
        URL_MICRODATA_UF,
        microdata_zip,
    )

    extract_zip(
        microdata_zip,
        microdata_extract,
    )

    microdata_files = sorted(
        path
        for path in microdata_extract.rglob("*")
        if path.is_file()
    )

    print(
        f"[OK] Microdados extraídos: "
        f"{len(microdata_files)} arquivo(s) em {microdata_extract}"
    )

    # --------------------------------------------------------
    # 9. ÁREAS DE PONDERAÇÃO
    # --------------------------------------------------------
    print("\n[9/11] Tabelas das áreas de ponderação")

    weighting_areas_zip = (
        WEIGHTING_AREAS_DIR / "tabelas_xlsx.zip"
    )
    weighting_areas_extract = (
        WEIGHTING_AREAS_DIR / "tabelas_xlsx"
    )

    download_if_missing(
        URL_WEIGHTING_AREAS_TABLES,
        weighting_areas_zip,
    )

    extract_zip(
        weighting_areas_zip,
        weighting_areas_extract,
    )

    weighting_area_files = sorted(
        path
        for path in weighting_areas_extract.rglob("*")
        if path.is_file()
    )

    print(
        f"[OK] Tabelas APOND extraídas: "
        f"{len(weighting_area_files)} arquivo(s) em "
        f"{weighting_areas_extract}"
    )

    # --------------------------------------------------------
    # 10. EXPORTAÇÃO
    # --------------------------------------------------------
    print("\n[10/11] Exportação")

    save_individual_outputs(
        sectors=sectors,
        neighborhoods_with_income=neighborhoods_with_income,
        municipal_boundary=municipal_boundary,
    )

    converters.export_gpkg(
        output_file=OUTPUT_GPKG,
        bairros=neighborhoods_with_income,
        setores=sectors,
        inter=sectors_neighborhood_income,
    )

    # --------------------------------------------------------
    # 11. MAPAS DO PILOTO
    # --------------------------------------------------------
    print("\n[11/11] Geração dos mapas")

    generated_maps = generate_pilot_maps(
        income_regions=neighborhoods_with_income,
        neighborhoods=neighborhoods_with_income,
        sectors=sectors,
        city_graph=network_graph,
        neighborhood_graph=neighborhood_graph,
        output_dir=OUTPUT_DIR,
        income_column="RENDA_MED_BAIRRO",
        boundary=municipal_boundary,
    )

    print("\nMapas gerados:")
    for map_name, map_path in generated_maps.items():
        print(f" - {map_name}: {map_path}")

    print("\n" + "=" * 70)
    print("PIPELINE FINALIZADO")
    print("=" * 70)
    print(f"GeoPackage consolidado: {OUTPUT_GPKG}")
    print(f"Setores: {len(sectors)}")
    print(f"Bairros: {len(neighborhoods_with_income)}")
    print(
        "Fragmentos setor-bairro: "
        f"{len(sectors_neighborhood_income)}"
    )
    print(f"Nós da rede municipal: {len(network_graph.nodes)}")
    print(f"Arestas da rede municipal: {len(network_graph.edges)}")
    print(f"CNEFE: {cnefe_csv_path}")
    print(f"Microdados RS: {microdata_extract}")
    print(f"Tabelas APOND: {weighting_areas_extract}")


if __name__ == "__main__":
    main()
