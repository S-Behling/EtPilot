from __future__ import annotations

import io
import shutil
import urllib.request
import zipfile
from pathlib import Path
from urllib.request import urlretrieve
from zipfile import ZipFile

import geopandas as gpd
import pandas as pd


def download(url: str, destino: Path) -> Path:
    """Baixa um arquivo apenas se ele ainda não existir."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)

    if destino.exists() and destino.stat().st_size > 0:
        print(f"[OK] Já existe: {destino.name}")
        return destino

    print(f"[DOWNLOAD] {destino.name}")

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
    )

    with urllib.request.urlopen(req, timeout=180) as resposta:
        with destino.open("wb") as arquivo:
            shutil.copyfileobj(resposta, arquivo)

    print(f"[OK] Baixado: {destino}")
    return destino


def normalizar_codigo(serie: pd.Series) -> pd.Series:
    """Converte códigos lidos como string/float para texto limpo."""
    return (
        serie.astype("string")
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )


def numero_br(serie: pd.Series) -> pd.Series:
    """Converte números no padrão brasileiro para float."""
    s = serie.astype("string").str.strip()

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


def achar_coluna(
    dataframe: pd.DataFrame,
    candidatas: list[str],
) -> str:
    """Retorna a primeira coluna existente entre as candidatas."""
    mapa = {coluna.upper(): coluna for coluna in dataframe.columns}

    for candidata in candidatas:
        if candidata.upper() in mapa:
            return mapa[candidata.upper()]

    raise KeyError(
        f"Nenhuma das colunas esperadas foi encontrada: {candidatas}\n"
        f"Colunas disponíveis: {list(dataframe.columns)}"
    )


def filtrar_municipio(
    gdf: gpd.GeoDataFrame,
    tipo: str,
    cod_city: str,
) -> gpd.GeoDataFrame:
    """Filtra um GeoDataFrame para o município informado."""
    cod_city = str(cod_city)

    if "CD_MUN" in gdf.columns:
        codigos = normalizar_codigo(gdf["CD_MUN"])
        return gdf.loc[codigos.eq(cod_city)].copy()

    if tipo == "bairro":
        coluna = achar_coluna(gdf, ["CD_BAIRRO"])
        codigos = normalizar_codigo(gdf[coluna])
        return gdf.loc[
            codigos.str.startswith(cod_city, na=False)
        ].copy()

    if tipo == "setor":
        coluna = achar_coluna(gdf, ["CD_SETOR"])
        codigos = normalizar_codigo(gdf[coluna])
        return gdf.loc[
            codigos.str.startswith(cod_city, na=False)
        ].copy()

    raise ValueError("tipo deve ser 'bairro' ou 'setor'")


def ler_renda_bairros(
    zip_path: Path,
    csv_renda_no_zip: str,
    cod_city: str,
) -> pd.DataFrame:
    """Lê os agregados oficiais de renda por bairro do IBGE."""
    zip_path = Path(zip_path)

    with zipfile.ZipFile(zip_path) as zip_file:
        nomes = zip_file.namelist()

        csv_name = csv_renda_no_zip

        if csv_name not in nomes:
            csvs = [
                nome
                for nome in nomes
                if nome.lower().endswith(".csv")
            ]

            if not csvs:
                raise FileNotFoundError(
                    f"Nenhum CSV encontrado dentro de {zip_path.name}"
                )

            csv_name = csvs[0]

        with zip_file.open(csv_name) as arquivo:
            texto = io.TextIOWrapper(
                arquivo,
                encoding="latin-1",
            )

            renda = pd.read_csv(
                texto,
                sep=";",
                dtype="string",
                low_memory=False,
            )

    renda.columns = [
        coluna.strip()
        for coluna in renda.columns
    ]

    coluna_bairro = achar_coluna(
        renda,
        ["CD_BAIRRO"],
    )

    renda[coluna_bairro] = normalizar_codigo(
        renda[coluna_bairro]
    )

    renda = renda.loc[
        renda[coluna_bairro].str.startswith(
            str(cod_city),
            na=False,
        )
    ].copy()

    renda["RENDA_MED_BAIRRO"] = numero_br(
        renda["V06004"]
    )

    if coluna_bairro != "CD_BAIRRO":
        renda = renda.rename(
            columns={coluna_bairro: "CD_BAIRRO"}
        )

    renda["CD_BAIRRO"] = normalizar_codigo(
        renda["CD_BAIRRO"]
    )

    return renda


def preparar_bairros(
    income: pd.DataFrame,
    crs: str,
    arq_bairros: str | Path,
    cod_city: str,
) -> gpd.GeoDataFrame:
    """Carrega a malha, filtra o município e associa renda por bairro."""
    print("[LEITURA] Malha de bairros...")

    bairros = gpd.read_file(arq_bairros)
    bairros = filtrar_municipio(
        bairros,
        "bairro",
        cod_city,
    )

    if bairros.empty:
        raise RuntimeError(
            f"Nenhum bairro encontrado para {cod_city}."
        )

    coluna_bairro = achar_coluna(
        bairros,
        ["CD_BAIRRO"],
    )

    bairros[coluna_bairro] = normalizar_codigo(
        bairros[coluna_bairro]
    )

    if coluna_bairro != "CD_BAIRRO":
        bairros = bairros.rename(
            columns={coluna_bairro: "CD_BAIRRO"}
        )

    income = income.copy()
    income["CD_BAIRRO"] = normalizar_codigo(
        income["CD_BAIRRO"]
    )

    cols_renda = [
        coluna
        for coluna in income.columns
        if coluna == "CD_BAIRRO"
        or coluna.startswith("V06")
        or coluna.startswith("RENDA_")
    ]

    bairros = bairros.merge(
        income[cols_renda],
        on="CD_BAIRRO",
        how="left",
        validate="one_to_one",
    )

    bairros = bairros.to_crs(crs)
    bairros["AREA_BAIRRO_M2"] = bairros.geometry.area

    return bairros


def preparar_setores(
    crs: str,
    arq_setores: str | Path,
    cod_city: str,
) -> gpd.GeoDataFrame:
    """Carrega a malha, filtra o município e prepara áreas dos setores."""
    print("[LEITURA] Malha de setores censitários...")

    setores = gpd.read_file(arq_setores)
    setores = filtrar_municipio(
        setores,
        "setor",
        cod_city,
    )

    if setores.empty:
        raise RuntimeError(
            f"Nenhum setor encontrado para {cod_city}."
        )

    coluna_setor = achar_coluna(
        setores,
        ["CD_SETOR"],
    )

    setores[coluna_setor] = normalizar_codigo(
        setores[coluna_setor]
    )

    if coluna_setor != "CD_SETOR":
        setores = setores.rename(
            columns={coluna_setor: "CD_SETOR"}
        )

    setores = setores.to_crs(crs)
    setores["AREA_SETOR_M2"] = setores.geometry.area

    return setores


def sobrepor_setores_bairros(
    setores: gpd.GeoDataFrame,
    bairros: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """Recorta setores pelos bairros e anexa a renda do bairro."""
    print("[OVERLAY] Intersectando setores x bairros...")

    cols_bairro = [
        "CD_BAIRRO",
        "RENDA_MED_BAIRRO",
        "geometry",
    ]

    if "NM_BAIRRO" in bairros.columns:
        cols_bairro.insert(1, "NM_BAIRRO")

    cols_setor = [
        "CD_SETOR",
        "AREA_SETOR_M2",
        "geometry",
    ]

    inter = gpd.overlay(
        setores[cols_setor],
        bairros[cols_bairro],
        how="intersection",
        keep_geom_type=False,
    )

    inter = inter.loc[
        inter.geometry.geom_type.isin(
            ["Polygon", "MultiPolygon"]
        )
    ].copy()

    inter["AREA_FRAG_M2"] = inter.geometry.area
    inter["FRAC_AREA_SETOR"] = (
        inter["AREA_FRAG_M2"]
        / inter["AREA_SETOR_M2"]
    )

    return inter.loc[
        inter["AREA_FRAG_M2"] > 1.0
    ].copy()


def download_cnefe(
    url: str,
    cod_uf: str = "43",
    cod_municipio: str = "4314902",
    municipio_nome: str = "PORTO_ALEGRE",
    output_dir: str | Path = "data/cnefe",
    overwrite: bool = False,
) -> Path:
    """Baixa e extrai o CNEFE 2022 para um município."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{cod_municipio}_{municipio_nome}.zip"

    final_url = (
        f"{url}/"
        f"{cod_uf}_RS/"
        f"{filename}"
    )

    zip_path = output_dir / filename

    if not zip_path.exists() or overwrite:
        print(f"Baixando CNEFE: {final_url}")
        urlretrieve(final_url, zip_path)
        print(f"Arquivo salvo em: {zip_path}")
    else:
        print(f"Arquivo já existente: {zip_path}")

    extract_dir = output_dir / cod_municipio
    extract_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    with ZipFile(zip_path, "r") as zip_file:
        zip_file.extractall(extract_dir)

    csv_files = list(
        extract_dir.rglob("*.csv")
    )

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
