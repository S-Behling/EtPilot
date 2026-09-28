"""Constrói destinos do CNEFE 2022 para o EtPilot.

Entrada:
  data/o-d/destinos_cnefe_porto_alegre.gpkg
  layer = destinations_cnefe

Saída:
  data/o-d/destinos_cnefe_classificados_porto_alegre.gpkg
  layers = establishments, destinations

Regras:
- education e health vêm do COD_ESPECIE;
- work inclui todos os estabelecimentos ativos;
- shopping e leisure são inferidos por palavras-chave;
- categorias não são mutuamente exclusivas;
- destinos finais são agregados pelo nó de referência da rede de carro e categoria;
- cada destino final recebe nós específicos para carro, caminhada e bicicleta.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

import geopandas as gpd
import pandas as pd

from src.network.multimodal import (
    assign_modal_nodes,
    load_mode_graphs,
)


# -----------------------------------------------------------------------------
# Caminhos
# -----------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]

INPUT_PATH = PROJECT_ROOT / "data" / "o-d" / "destinos_cnefe_porto_alegre.gpkg"
INPUT_LAYER = "destinations_cnefe"
CONFIG_PATH = PROJECT_ROOT / "config" / "config.json"
OUTPUT_PATH = (
    PROJECT_ROOT / "data" / "o-d" / "destinos_cnefe_classificados_porto_alegre.gpkg"
)
TARGET_CRS = "EPSG:31982"


# -----------------------------------------------------------------------------
# Regras de limpeza
# -----------------------------------------------------------------------------

INACTIVE_PATTERN = (
    r"\bVAGO\b|\bVAGA\b|\bVAZIO\b|\bVAZIA\b|"
    r"\bDESOCUPADO\b|\bDESOCUPADA\b|\bDEDOCUPADA\b|"
    r"\bDESATIVADO\b|\bDESATIVADA\b|\bINATIVO\b|\bINATIVA\b|"
    r"\bABANDONADO\b|\bABANDONADA\b|\bDEMOLIDO\b|\bDEMOLIDA\b|"
    r"\bFECHADO\b|\bFECHADA\b|\bFECHADOS\b|\bFECHADAS\b|"
    r"\bPARA\s+ALUGAR\b|\bP\s+ALUGAR\b|\bP\s*/\s*ALUGAR\b|"
    r"\bALUGA[\s-]*SE\b|\bEM\s+REFORMA\b"
)

NO_INFORMATION_EXACT = {
    "SEM NOME", "SN", "S N", "SEM IDENTIFICACAO", "SEM INFORMACAO",
    "NAO IDENTIFICADO", "NAO IDENTIFICADA", "NAO INFORMADO",
    "NAO INFORMADA", "DESCONHECIDO", "DESCONHECIDA", "IGNORADO", "IGNORADA",
}

PROPERTY_TYPES_PATTERN = (
    r"LOJA|LOJAS|SALA|SALAS|SALA COMERCIAL|SALAS COMERCIAIS|PREDIO|GARAGEM|"
    r"IMOVEL|ESTABELECIMENTO|ESPACO COMERCIAL|PONTO COMERCIAL|DEPOSITO|"
    r"ESCRITORIO|GALPAO|PAVILHAO|CENTRO PROFISSIONAL"
)

PROPERTY_AVAILABLE_PATTERN = (
    rf"\b(?:{PROPERTY_TYPES_PATTERN})\b.*\b(?:A VENDA|PARA VENDA|PARA LOCACAO)\b"
)


# -----------------------------------------------------------------------------
# Regras de shopping
# -----------------------------------------------------------------------------

SHOPPING_STRONG = [
    r"\bMERCADO\b", r"\bMINI MERCADO\b", r"\bMINIMERCADO\b",
    r"\bMERCADINHO\b", r"\bSUPERMERCADO\b", r"\bSUPER MERCADO\b",
    r"\bHIPERMERCADO\b", r"\bMERCEARIA\b", r"\bARMAZEM\b",
    r"\bPADARIA\b", r"\bACOUGUE\b", r"\bHORTIFRUTI\b", r"\bFRUTEIRA\b",
    r"\bBRECHO\b", r"\bBAZAR\b", r"\bARMARINHO\b", r"\bARMARINHOS\b",
    r"\bFERRAGEM\b", r"\bFERRAGENS\b", r"\bLIVRARIA\b", r"\bPAPELARIA\b",
    r"\bFLORICULTURA\b", r"\bSAPATARIA\b", r"\bCALCADOS\b",
    r"\bROUPA\b", r"\bROUPAS\b", r"\bVESTUARIO\b",
    r"\bCONFECCAO\b", r"\bCONFECCOES\b", r"\bMOVEIS\b", r"\bCOLCHOES\b",
    r"\bELETRODOMESTICOS\b", r"\bELETRONICOS\b",
    r"\bMATERIAL DE CONSTRUCAO\b", r"\bMATERIAIS DE CONSTRUCAO\b",
    r"\bPET SHOP\b", r"\bCOSMETICOS\b", r"\bPERFUMARIA\b", r"\bTINTAS\b",
    r"\bAUTO PECAS\b", r"\bAUTOPECAS\b", r"\bBICICLETA\b", r"\bBICICLETAS\b",
    r"\bCELULAR\b", r"\bCELULARES\b", r"\bINFORMATICA\b",
    r"\bPRESENTES\b", r"\bVARIEDADES\b", r"\bANTIGUIDADES\b",
    r"\bTECIDOS\b", r"\bAVIAMENTOS\b", r"\bCONVENIENCIA\b",
    r"\bTABACARIA\b", r"\bJOALHERIA\b", r"\bBIJUTERIA\b",
    r"\bFARMACIA\b", r"\bDROGARIA\b",
]

SHOPPING_SERVICE = [
    r"\bOFICINA\b", r"\bFABRICA\b", r"\bFABRICACAO\b", r"\bINDUSTRIA\b",
    r"\bINDUSTRIAL\b", r"\bMANUTENCAO\b", r"\bCONSERTO\b", r"\bCONSERTOS\b",
    r"\bASSISTENCIA TECNICA\b", r"\bSERVICO\b", r"\bSERVICOS\b",
    r"\bPRODUCAO\b", r"\bMARCENARIA\b",
]

SHOPPING_SALE_EVIDENCE = [
    r"\bCOMERCIO\b", r"\bVENDA\b", r"\bVENDAS\b", r"\bPECAS\b",
    r"\bPRODUTO\b", r"\bPRODUTOS\b", r"\bACESSORIO\b", r"\bACESSORIOS\b",
    r"\bBRECHO\b",
]

STORE_SUSPICIOUS = [
    *SHOPPING_SERVICE,
    r"\bSEGURO\b", r"\bSEGUROS\b", r"\bCREDITO\b", r"\bFINANCEIRA\b",
    r"\bCOSTURA\b", r"\bBARBEARIA\b", r"\bSALAO DE BELEZA\b",
    r"\bDEPOSITO\b", r"\bBANHO E TOSA\b", r"\bTOSA\b", r"\bBELEZA\b",
    r"\bESTETICA\b", r"\bCABELEIREIRO\b", r"\bCABELEREIRO\b",
    r"\bMECANICA\b", r"\bLAVAGEM\b", r"\bLAVANDERIA\b",
    r"\bIMOBILIARIA\b", r"\bADVOCACIA\b", r"\bCONTABILIDADE\b",
    r"\bCONSULTORIA\b", r"\bDESPACHANTE\b", r"\bXEROX\b", r"\bCOPIAS\b",
    r"\bLOCADORA\b", r"\bALUGUEL\b", r"\bLOCACAO\b", r"\bESTACIONAMENTO\b",
    r"\bSEM USO\b", r"\bEM CONSTRUCAO\b",
]

STORE_EXCEPTIONS = {"LOJA DE MATERIAL FOTOGRAFICO"}


# -----------------------------------------------------------------------------
# Regras de leisure
# -----------------------------------------------------------------------------

LEISURE = [
    r"\bRESTAURANTE\b", r"\bBAR\b", r"\bBARZINHO\b", r"\bBOTECO\b",
    r"\bBUTECO\b", r"\bLANCHERIA\b", r"\bLANCHES\b", r"\bCAFETERIA\b",
    r"\bCAFE\b", r"\bPIZZARIA\b", r"\bCHURRASCARIA\b", r"\bSORVETERIA\b",
    r"\bPUB\b", r"\bBOATE\b", r"\bCASA NOTURNA\b", r"\bCINEMA\b",
    r"\bTEATRO\b", r"\bMUSEU\b", r"\bCLUBE\b", r"\bACADEMIA\b",
    r"\bSALAO DE FESTAS\b", r"\bCASA DE FESTAS\b", r"\bBUFFET\b",
    r"\bBOLICHE\b", r"\bBILHAR\b", r"\bSINUCA\b", r"\bLAN HOUSE\b",
    r"\bPARQUE DE DIVERSOES\b", r"\bCASA DE SHOW\b", r"\bCASA DE SHOWS\b",
]


def _pattern(items: list[str]) -> str:
    return "|".join(items)


def normalize_description(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).upper().strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^A-Z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def sample_descriptions(series: pd.Series, max_items: int = 20) -> str:
    values = sorted({str(v).strip() for v in series.dropna() if str(v).strip()})
    return json.dumps(values[:max_items], ensure_ascii=False)


def load_cnefe() -> gpd.GeoDataFrame:
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {INPUT_PATH}")

    gdf = gpd.read_file(INPUT_PATH, layer=INPUT_LAYER, engine="pyogrio")

    required = {"COD_UNICO_ENDERECO", "COD_ESPECIE", "DSC_ESTABELECIMENTO", "geometry"}
    missing = required - set(gdf.columns)
    if missing:
        raise ValueError(f"Colunas obrigatórias ausentes: {sorted(missing)}")

    if gdf.crs is None:
        raise ValueError("O CNEFE não possui CRS.")
    if str(gdf.crs) != TARGET_CRS:
        gdf = gdf.to_crs(TARGET_CRS)

    gdf["COD_ESPECIE"] = pd.to_numeric(gdf["COD_ESPECIE"], errors="coerce")
    return gdf


def prepare_establishments(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    result = gdf.copy()
    result["description_norm"] = result["DSC_ESTABELECIMENTO"].apply(normalize_description)

    is_other = result["COD_ESPECIE"].eq(6)
    desc = result["description_norm"]

    inactive = desc.str.contains(INACTIVE_PATTERN, regex=True, na=False)
    no_info = desc.isin(NO_INFORMATION_EXACT)
    property_available = (
        desc.str.contains(PROPERTY_AVAILABLE_PATTERN, regex=True, na=False)
        | desc.str.contains(r"^(?:A VENDA|PARA VENDA|PARA LOCACAO)$", regex=True, na=False)
        | desc.str.contains(
            r"^(?:NAO IDENTIFICADO.*PARA LOCACAO|NAO TEM NOME.*A VENDA)$",
            regex=True,
            na=False,
        )
    )

    result["inactive"] = is_other & (inactive | no_info | property_available)
    result["active"] = ~result["inactive"]
    return result


def classify_shopping(gdf: gpd.GeoDataFrame) -> pd.Series:
    desc = gdf["description_norm"]

    strong = desc.str.contains(_pattern(SHOPPING_STRONG), regex=True, na=False)
    service = desc.str.contains(_pattern(SHOPPING_SERVICE), regex=True, na=False)
    sale = desc.str.contains(_pattern(SHOPPING_SALE_EVIDENCE), regex=True, na=False)
    strong_refined = strong & (~service | sale)

    contains_store = desc.str.contains(r"\bLOJA\b", regex=True, na=False)
    suspicious_store = desc.str.contains(_pattern(STORE_SUSPICIOUS), regex=True, na=False)
    generic_store = contains_store & (~suspicious_store | desc.isin(STORE_EXCEPTIONS))

    return gdf["active"] & gdf["COD_ESPECIE"].eq(6) & (strong_refined | generic_store)


def classify_establishments(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    result = gdf.copy()
    result["work"] = result["active"]
    result["education"] = result["active"] & result["COD_ESPECIE"].eq(4)
    result["health"] = result["active"] & result["COD_ESPECIE"].eq(5)
    result["shopping"] = classify_shopping(result)
    result["leisure"] = (
        result["active"]
        & result["COD_ESPECIE"].eq(6)
        & result["description_norm"].str.contains(_pattern(LEISURE), regex=True, na=False)
    )
    result["n_functions"] = result[["work", "education", "health", "shopping", "leisure"]].sum(axis=1).astype(int)
    return result


def load_project_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Configuração não encontrada: {CONFIG_PATH}")

    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_networks() -> dict[str, object]:
    config = load_project_config()
    return load_mode_graphs(
        config=config,
        project_root=PROJECT_ROOT,
    )


def to_long_format(establishments: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    active = establishments[establishments["active"]].copy()
    functions = ["work", "education", "health", "shopping", "leisure"]

    long_df = active.melt(
        id_vars=[
            "COD_UNICO_ENDERECO",
            "DSC_ESTABELECIMENTO",
            "description_norm",
            "COD_ESPECIE",
            "node_car",
            "node_walk",
            "node_bike",
            "geometry",
        ],
        value_vars=functions,
        var_name="category",
        value_name="is_destination",
    )

    long_df = long_df[long_df["is_destination"]].drop(columns="is_destination")
    return gpd.GeoDataFrame(long_df, geometry="geometry", crs=establishments.crs)


def aggregate_destinations(
    long_destinations: gpd.GeoDataFrame,
    graphs: dict[str, object],
) -> gpd.GeoDataFrame:
    """
    Agrega destinos usando a rede de carro apenas como âncora espacial.

    O nó de carro define a consolidação inicial dos estabelecimentos, mas não
    é tratado como nó universal. Depois da agregação, o mesmo ponto recebe
    `node_car`, `node_walk` e `node_bike` para roteamento modal.
    """

    if "car" not in graphs:
        raise ValueError(
            "A rede 'car' é necessária como âncora de agregação dos destinos."
        )

    summary = (
        long_destinations
        .groupby(["node_car", "category"], as_index=False)
        .agg(
            destination_weight=("COD_UNICO_ENDERECO", "size"),
            n_addresses=("COD_UNICO_ENDERECO", "nunique"),
            n_subcategories=("description_norm", "nunique"),
            subcategories=("DSC_ESTABELECIMENTO", sample_descriptions),
            geometry=("geometry", "first"),
        )
    )

    if summary["geometry"].isna().any():
        raise ValueError(
            "Há destinos agregados sem geometria representativa."
        )

    # A geometria continua sendo derivada do CNEFE. O node_car é apenas
    # a chave de consolidação para reduzir destinos muito próximos.
    summary = gpd.GeoDataFrame(
        summary,
        geometry="geometry",
        crs=long_destinations.crs,
    )

    summary = assign_modal_nodes(
        summary,
        graphs,
    )

    summary = (
        summary
        .sort_values(["category", "node_car"])
        .reset_index(drop=True)
    )

    summary["destination_id"] = [
        f"D_{i:07d}"
        for i in range(len(summary))
    ]

    cols = [
        "destination_id",
        "category",
        "node_car",
        "node_walk",
        "node_bike",
        "destination_weight",
        "n_addresses",
        "n_subcategories",
        "subcategories",
        "geometry",
    ]

    return gpd.GeoDataFrame(
        summary[cols],
        geometry="geometry",
        crs=summary.crs,
    )


def save_outputs(establishments: gpd.GeoDataFrame, destinations: gpd.GeoDataFrame) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT_PATH.exists():
        OUTPUT_PATH.unlink()

    establishments.to_file(
        OUTPUT_PATH,
        layer="establishments",
        driver="GPKG",
        engine="pyogrio",
    )
    destinations.to_file(
        OUTPUT_PATH,
        layer="destinations",
        driver="GPKG",
        engine="pyogrio",
    )


def print_report(establishments: gpd.GeoDataFrame, destinations: gpd.GeoDataFrame) -> None:
    print("\n" + "=" * 68)
    print("CNEFE — RESUMO")
    print("=" * 68)
    print(f"Registros CNEFE: {len(establishments):,}")
    print(f"Ativos: {int(establishments['active'].sum()):,}")
    print(f"Inativos/sem informação: {int(establishments['inactive'].sum()):,}")

    print("\nEstabelecimentos por finalidade:")
    for category in ["work", "education", "health", "shopping", "leisure"]:
        print(f"  {category:10s}: {int(establishments[category].sum()):,}")

    print("\nDestinos agregados por nó de referência (car):")
    counts = destinations["category"].value_counts()
    for category in ["work", "education", "health", "shopping", "leisure"]:
        print(f"  {category:10s}: {int(counts.get(category, 0)):,}")

    print(f"\nArquivo: {OUTPUT_PATH.resolve()}")
    print("=" * 68)


def build_destinations_cnefe() -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    print("1/6 — Lendo CNEFE...")
    establishments = load_cnefe()

    print("2/6 — Limpando descrições...")
    establishments = prepare_establishments(establishments)

    print("3/6 — Classificando funções...")
    establishments = classify_establishments(establishments)

    print("4/6 — Associando estabelecimentos às redes modais...")
    graphs = load_networks()
    establishments = assign_modal_nodes(
        establishments,
        graphs,
    )

    print("5/6 — Agregando destinos e atribuindo nós por modo...")
    long_destinations = to_long_format(establishments)
    destinations = aggregate_destinations(
        long_destinations,
        graphs,
    )

    print("6/6 — Salvando GeoPackage...")
    save_outputs(establishments, destinations)
    print_report(establishments, destinations)

    return establishments, destinations


def main() -> None:
    build_destinations_cnefe()


if __name__ == "__main__":
    main()
