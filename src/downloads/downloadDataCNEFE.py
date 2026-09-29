from pathlib import Path
from urllib.request import urlretrieve
from zipfile import ZipFile
import urllib.request
import shutil
import zipfile
import pandas as pd
import geopandas as gpd
import io

def download(url: str, destino: Path) -> None:
    """Baixa um arquivo apenas se ele ainda não existir."""
    destino.parent.mkdir(parents=True, exist_ok=True)

    if destino.exists() and destino.stat().st_size > 0:
        print(f"[OK] Já existe: {destino.name}")
        return

    print(f"[DOWNLOAD] {destino.name}")
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
    )

    with urllib.request.urlopen(req, timeout=180) as resposta:
        with open(destino, "wb") as f:
            shutil.copyfileobj(resposta, f)

    print(f"[OK] Baixado: {destino}")

def normalizar_codigo(serie: pd.Series) -> pd.Series:
    """
    Converte códigos lidos como string/float para texto limpo.
    Ex.: '4314902001.0' -> '4314902001'
    """
    return (
        serie.astype("string")
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )

def numero_br(serie: pd.Series) -> pd.Series:
    """
    Converte número no padrão brasileiro para float.
    Ex.: '2.157,56' -> 2157.56
    """
    s = serie.astype("string").str.strip()

    # valores suprimidos/vazios permanecem como NaN
    s = s.replace(
        {
            "": pd.NA,
            "-": pd.NA,
            "X": pd.NA,
            "x": pd.NA,
            "NA": pd.NA,
            "N/A": pd.NA,
            "nan": pd.NA,
        }
    )

    s = (
        s.str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
    )

    return pd.to_numeric(s, errors="coerce")

def achar_coluna(gdf: pd.DataFrame, candidatas: list[str]) -> str:
    """Retorna a primeira coluna existente entre as candidatas."""
    mapa = {c.upper(): c for c in gdf.columns}

    for candidata in candidatas:
        if candidata.upper() in mapa:
            return mapa[candidata.upper()]

    raise KeyError(
        f"Nenhuma das colunas esperadas foi encontrada: {candidatas}\n"
        f"Colunas disponíveis: {list(gdf.columns)}"
    )

def filtrar_municipio(
    gdf: gpd.GeoDataFrame,
    tipo: str,
    cod_city,
) -> gpd.GeoDataFrame:
    """
    Filtra Porto Alegre.

    Tenta primeiro CD_MUN.
    Se não existir, usa o prefixo do código do bairro/setor.
    """
    if "CD_MUN" in gdf.columns:
        cod = normalizar_codigo(gdf["CD_MUN"])
        return gdf.loc[cod.eq(cod_city)].copy()

    if tipo == "bairro":
        col = achar_coluna(gdf, ["CD_BAIRRO"])
        cod = normalizar_codigo(gdf[col])
        return gdf.loc[cod.str.startswith(cod_city, na=False)].copy()

    if tipo == "setor":
        col = achar_coluna(gdf, ["CD_SETOR"])
        cod = normalizar_codigo(gdf[col])
        return gdf.loc[cod.str.startswith(cod_city, na=False)].copy()

    raise ValueError("tipo deve ser 'bairro' ou 'setor'")

# ============================================================
# LEITURA DA RENDA OFICIAL POR BAIRRO
# ============================================================

def ler_renda_bairros(zip_path: Path, CSV_RENDA_NO_ZIP: str, cod_city: str) -> pd.DataFrame:
    """
    Lê os agregados do IBGE já publicados por bairro.

    Colunas do arquivo:
        CD_BAIRRO
        NM_BAIRRO
        V06001
        V06002
        V06003
        V06004
        V06005
        V06006

    Para este release:
        V06004 = rendimento nominal médio mensal das pessoas responsáveis
                  com rendimentos por domicílios particulares permanentes ocupados

    As demais variáveis V060xx são preservadas no arquivo de bairros para consulta.
    """

    with zipfile.ZipFile(zip_path) as zf:
        nomes = zf.namelist()

        csv_name = CSV_RENDA_NO_ZIP
        if csv_name not in nomes:
            # fallback caso o IBGE altere o nome interno do arquivo
            csvs = [n for n in nomes if n.lower().endswith(".csv")]
            if not csvs:
                raise FileNotFoundError(
                    f"Nenhum CSV encontrado dentro de {zip_path.name}"
                )
            csv_name = csvs[0]

        with zf.open(csv_name) as f:
            texto = io.TextIOWrapper(f, encoding="latin-1")
            renda = pd.read_csv(
                texto,
                sep=";",
                dtype="string",
                low_memory=False,
            )

    renda.columns = [c.strip() for c in renda.columns]

    col_bairro = achar_coluna(renda, ["CD_BAIRRO"])
    renda[col_bairro] = normalizar_codigo(renda[col_bairro])

    # Porto Alegre: códigos de bairro começam pelo código municipal
    renda = renda.loc[
        renda[col_bairro].str.startswith(cod_city, na=False)
    ].copy()

    # Mantemos as variáveis originais e criamos aliases claros
    renda["RENDA_MED_BAIRRO"] = numero_br(renda["V06004"])

    # Garante nomes consistentes para o merge
    if col_bairro != "CD_BAIRRO":
        renda = renda.rename(columns={col_bairro: "CD_BAIRRO"})

    renda["CD_BAIRRO"] = normalizar_codigo(renda["CD_BAIRRO"])

    return renda


# ============================================================
# PROCESSAMENTO ESPACIAL
# ============================================================

def preparar_bairros(city, income: pd.DataFrame, crs, ARQ_BAIRROS: str) -> gpd.GeoDataFrame:
    print("[LEITURA] Malha de bairros...")
    bairros = gpd.read_file(ARQ_BAIRROS)

    bairros = filtrar_municipio(city, bairros, "bairro")

    if bairros.empty:
        raise RuntimeError("Nenhum bairro de Porto Alegre foi encontrado.")

    col_cd_bairro = achar_coluna(bairros, ["CD_BAIRRO"])
    bairros[col_cd_bairro] = normalizar_codigo(bairros[col_cd_bairro])

    if col_cd_bairro != "CD_BAIRRO":
        bairros = bairros.rename(columns={col_cd_bairro: "CD_BAIRRO"})

    bairros["CD_BAIRRO"] = normalizar_codigo(bairros["CD_BAIRRO"])

    # Evita duplicar o nome do bairro na junção
    cols_renda = [
        c for c in income.columns
        if c == "CD_BAIRRO"
        or c.startswith("V06")
        or c.startswith("RENDA_")
    ]

    bairros = bairros.merge(
        income[cols_renda],
        on="CD_BAIRRO",
        how="left",
        validate="1:1",
    )

    bairros = bairros.to_crs(crs)
    bairros["AREA_BAIRRO_M2"] = bairros.geometry.area

    sem_renda = bairros["RENDA_MED_BAIRRO"].isna().sum()
    if sem_renda:
        print(
            f"[AVISO] {sem_renda} bairro(s) ficaram sem renda "
            "após a junção."
        )

    return bairros

def preparar_setores(crs, ARQ_SETORES: str) -> gpd.GeoDataFrame:
    print("[LEITURA] Malha de setores censitários...")
    setores = gpd.read_file(ARQ_SETORES)

    setores = filtrar_municipio(setores, "setor")

    if setores.empty:
        raise RuntimeError(
            "Nenhum setor censitário de Porto Alegre foi encontrado."
        )

    col_cd_setor = achar_coluna(setores, ["CD_SETOR"])
    setores[col_cd_setor] = normalizar_codigo(setores[col_cd_setor])

    if col_cd_setor != "CD_SETOR":
        setores = setores.rename(columns={col_cd_setor: "CD_SETOR"})

    setores = setores.to_crs(crs)

    # Área original do setor, antes do recorte por bairro
    setores["AREA_SETOR_M2"] = setores.geometry.area

    return setores


def sobrepor_setores_bairros(
    setores: gpd.GeoDataFrame,
    bairros: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """
    Intersecta setores e bairros.

    A geometria do setor é recortada pelo limite do bairro.
    A renda anexada é a renda OFICIAL DO BAIRRO, não a do setor.
    """
    print("[OVERLAY] Intersectando setores x bairros...")

    # seleciona somente atributos necessários dos bairros
    cols_bairro = [
        "CD_BAIRRO",
        "RENDA_MED_BAIRRO",
        "geometry",
    ]

    if "NM_BAIRRO" in bairros.columns:
        cols_bairro.insert(1, "NM_BAIRRO")

    # somente atributos essenciais do setor
    cols_setor = ["CD_SETOR", "AREA_SETOR_M2", "geometry"]

    inter = gpd.overlay(
        setores[cols_setor],
        bairros[cols_bairro],
        how="intersection",
        keep_geom_type=False,
    )

    # Em overlay podem surgir linhas/pontos por simples contato de bordas.
    # Para este piloto queremos apenas áreas.
    inter = inter.loc[
        inter.geometry.geom_type.isin(["Polygon", "MultiPolygon"])
    ].copy()

    inter["AREA_FRAG_M2"] = inter.geometry.area

    inter["FRAC_AREA_SETOR"] = (
        inter["AREA_FRAG_M2"] / inter["AREA_SETOR_M2"]
    )

    # Remove resíduos geométricos muito pequenos
    inter = inter.loc[inter["AREA_FRAG_M2"] > 1.0].copy()

    return inter



def download_cnefe(url,
    cod_uf: str = "43",
    cod_municipio: str = "4314902",
    municipio_nome: str = "PORTO_ALEGRE",
    output_dir: str | Path = "data/cnefe",
    overwrite: bool = False,
) -> Path:
    """
    Baixa e extrai os dados do CNEFE 2022 para um município.

    Parameters
    ----------
    cod_uf
        Código IBGE da UF.
    cod_municipio
        Código IBGE do município.
    municipio_nome
        Nome utilizado pelo IBGE no arquivo ZIP.
    output_dir
        Diretório de saída.
    overwrite
        Se True, baixa novamente mesmo que o arquivo já exista.

    Returns
    -------
    Path
        Caminho para o arquivo CSV extraído.
    """

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{cod_municipio}_{municipio_nome}.zip"

    url = (
        f"{url}/"
        f"{cod_uf}_RS/"
        f"{filename}"
    )

    zip_path = output_dir / filename

    if not zip_path.exists() or overwrite:
        print(f"Baixando CNEFE: {url}")
        urlretrieve(url, zip_path)
        print(f"Arquivo salvo em: {zip_path}")
    else:
        print(f"Arquivo já existente: {zip_path}")

    extract_dir = output_dir / cod_municipio
    extract_dir.mkdir(parents=True, exist_ok=True)

    with ZipFile(zip_path, "r") as zip_file:
        zip_file.extractall(extract_dir)

    csv_files = list(extract_dir.rglob("*.csv"))

    if not csv_files:
        raise FileNotFoundError(
            f"Nenhum CSV encontrado após extrair {zip_path}"
        )

    if len(csv_files) > 1:
        print("Mais de um CSV encontrado:")
        for file in csv_files:
            print(f"  - {file}")

    csv_path = csv_files[0]

    print(f"CNEFE extraído: {csv_path}")

    return csv_path


if __name__ == "__main__":
    download_cnefe()