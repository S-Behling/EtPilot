from pathlib import Path
from urllib.request import urlretrieve
from zipfile import ZipFile


IBGE_CNEFE_BASE_URL = (
    "https://ftp.ibge.gov.br/"
    "Cadastro_Nacional_de_Enderecos_para_Fins_Estatisticos/"
    "Censo_Demografico_2022/"
    "Arquivos_CNEFE/CSV/Municipio"
)


def download_cnefe(
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
        f"{IBGE_CNEFE_BASE_URL}/"
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