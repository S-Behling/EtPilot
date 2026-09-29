from __future__ import annotations

import io
import zipfile
from pathlib import Path
from urllib.request import urlretrieve
from zipfile import ZipFile

import pandas as pd


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


def download_cnefe(
    url: str,
    cod_uf: str,
    uf: str,
    cod_municipio: str,
    municipio_nome: str,
    output_dir: str | Path,
    overwrite: bool = False,
) -> Path:
    """
    Baixa e extrai o CNEFE 2022 para um município.

    Retorna o caminho do CSV extraído.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{cod_municipio}_{municipio_nome}.zip"

    final_url = (
        f"{url}/"
        f"{cod_uf}_{uf}/"
        f"{filename}"
    )

    zip_path = output_dir / filename

    if not zip_path.exists() or overwrite:
        print(f"Baixando CNEFE: {final_url}")
        urlretrieve(final_url, zip_path)
        print(f"Arquivo salvo em: {zip_path}")
    else:
        print(f"[OK] CNEFE já existe: {zip_path}")

    extract_dir = output_dir / cod_municipio
    extract_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    csv_existentes = list(
        extract_dir.rglob("*.csv")
    )

    if not csv_existentes or overwrite:
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
        print("Mais de um CSV encontrado no CNEFE:")
        for file in csv_files:
            print(f"  - {file}")

    csv_path = csv_files[0]
    print(f"CNEFE extraído: {csv_path}")

    return csv_path
