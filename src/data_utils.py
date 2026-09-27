import pandas as pd
import geopandas as gpd
from pathlib import Path
from zipfile import ZipFile, BadZipFile
import requests

# Funcao de download
def baixar_arquivo(url, destino, chunk_size=1024 * 1024):

    destino = Path(destino)

    # Eu evito baixar novamente arquivos
    # que já existem no projeto.
    if destino.exists():

        print(
            f"Arquivo já existe: {destino.name}"
        )

        return destino


    print(
        f"Baixando: {destino.name}"
    )


    resposta = requests.get(
        url,
        stream=True,
        timeout=120
    )

    resposta.raise_for_status()


    tamanho_total = int(
        resposta.headers.get(
            "content-length",
            0
        )
    )


    baixado = 0


    with open(destino, "wb") as arquivo:

        for bloco in resposta.iter_content(
            chunk_size=chunk_size
        ):

            if not bloco:
                continue

            arquivo.write(
                bloco
            )

            baixado += len(bloco)


            if tamanho_total > 0:

                percentual = (
                    baixado
                    / tamanho_total
                    * 100
                )

                print(
                    f"\r{percentual:6.2f}%",
                    end=""
                )


    print(
        f"\nConcluído: {destino}"
    )

    return destino

# ==========
## Funcao generica de download
def download_file(url, destination):
    if not url:
        raise ValueError(
            "URL de download não definida."
        )

    response = requests.get(
        url,
        stream=True,
        timeout=120
    )

    response.raise_for_status()

    destination.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(destination, "wb") as f:
        for chunk in response.iter_content(
            chunk_size=1024 * 1024
        ):
            if chunk:
                f.write(chunk)

# ==========
# Download setores censitarios
def load_income_sectors(
    source_dir,
    municipality_code,
    income_variable,
    income_weight,
    residents_variable,
    ):
    csv_files = list(
        source_dir.rglob("*.csv")
    )

    if not csv_files:
        raise FileNotFoundError(
            "Nenhum CSV encontrado."
        )

    csv_path = csv_files[0]

    df = pd.read_csv(
        csv_path,
        sep=";",
        quotechar='"',
        encoding="utf-8-sig",
        dtype={
            "CD_SETOR": str
        },
        low_memory=False
    )

    required = [
        "CD_SETOR",
        income_variable,
        income_weight,
        residents_variable,
    ]

    missing = [
        col
        for col in required
        if col not in df.columns
    ]

    if missing:
        raise KeyError(
            f"Colunas ausentes: {missing}"
        )

    poa = df.loc[
        df["CD_SETOR"].str.startswith(
            str(municipality_code),
            na=False
        ),
        required
    ].copy()

    numeric_columns = [
        income_variable,
        income_weight,
        residents_variable,
    ]

    for col in numeric_columns:
        poa[col] = pd.to_numeric(
            poa[col],
            errors="coerce"
        )

    return poa

# ==========
# Extracao de arquivos zip
def extract_zip(
    zip_path: Path,
    extract_dir: Path,
    overwrite: bool = False,
    ) -> Path:
    """
    Extrai um arquivo ZIP para uma pasta de destino.

    Parameters
    ----------
    zip_path : Path
        Caminho para o arquivo .zip.

    extract_dir : Path
        Pasta onde os arquivos serão extraídos.

    overwrite : bool, default=False
        Se False e a pasta já contiver arquivos,
        a extração é ignorada.
        Se True, o conteúdo do ZIP é extraído novamente.

    Returns
    -------
    Path
        Caminho da pasta de extração.
    """

    zip_path = Path(zip_path)
    extract_dir = Path(extract_dir)

    # --------------------------------------------------
    # VALIDAÇÕES
    # --------------------------------------------------

    if not zip_path.exists():
        raise FileNotFoundError(
            f"Arquivo ZIP não encontrado: {zip_path}"
        )

    if zip_path.suffix.lower() != ".zip":
        raise ValueError(
            f"O arquivo informado não é um ZIP: {zip_path}"
        )

    # Cria diretório de destino
    extract_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    # --------------------------------------------------
    # EVITA EXTRAÇÃO REPETIDA
    # --------------------------------------------------

    if not overwrite:

        arquivos_existentes = list(
            extract_dir.iterdir()
        )

        if arquivos_existentes:

            print(
                f"Arquivos já extraídos em: "
                f"{extract_dir}"
            )

            return extract_dir

    # --------------------------------------------------
    # EXTRAÇÃO
    # --------------------------------------------------

    print(
        f"Extraindo: {zip_path.name}"
    )

    try:

        with ZipFile(zip_path, "r") as zip_ref:

            # Testa se o ZIP está íntegro
            arquivo_corrompido = (
                zip_ref.testzip()
            )

            if arquivo_corrompido is not None:

                raise BadZipFile(
                    "Arquivo corrompido dentro "
                    f"do ZIP: {arquivo_corrompido}"
                )

            zip_ref.extractall(
                extract_dir
            )

    except BadZipFile as e:

        raise BadZipFile(
            f"Erro ao extrair {zip_path}: {e}"
        )

    print(
        f"Extração concluída: "
        f"{extract_dir}"
    )

    return extract_dir

# ==========
# Download bairros
def load_income_neighborhoods(
    source_dir: Path,
    municipality_code: str,
    income_variable: str,
    income_weight: str,
    residents_variable: str,
    ):
    """
    Carrega a base de rendimento por bairro do IBGE,
    filtra o município desejado e retorna as variáveis
    necessárias para a análise.

    Parameters
    ----------
    source_dir : Path
        Diretório onde o ZIP da renda por bairro foi extraído.

    municipality_code : str
        Código IBGE do município.
        Ex.: "4314902" para Porto Alegre.

    income_variable : str
        Variável principal de rendimento.
        Ex.: "V06004".

    income_weight : str
        Variável utilizada como peso.
        Ex.: "V06001".

    residents_variable : str
        Número de moradores em domicílios particulares
        permanentes ocupados.
        Ex.: "V06002".

    Returns
    -------
    pd.DataFrame
        DataFrame contendo os bairros do município e
        as variáveis selecionadas.
    """

    source_dir = Path(source_dir)

    # --------------------------------------------------
    # LOCALIZA CSV
    # --------------------------------------------------

    csv_files = list(
        source_dir.rglob("*.csv")
    )

    if not csv_files:
        raise FileNotFoundError(
            f"Nenhum CSV encontrado em: {source_dir}"
        )

    print(
        "\nArquivos CSV encontrados para renda por bairro:"
    )

    for file in csv_files:
        print(" -", file.name)

    # Prioriza arquivo com "bairro" no nome
    bairro_files = [
        file
        for file in csv_files
        if "bairro" in file.name.lower()
    ]

    if bairro_files:
        csv_path = bairro_files[0]
    else:
        csv_path = csv_files[0]

    print(
        "\nArquivo de renda por bairro utilizado:"
    )
    print(csv_path)

    # --------------------------------------------------
    # LEITURA COM FALLBACK DE ENCODING
    # --------------------------------------------------

    encodings = [
        "utf-8-sig",
        "cp1252",
        "latin-1",
    ]

    df = None
    used_encoding = None

    for encoding in encodings:

        try:
            df = pd.read_csv(
                csv_path,
                sep=";",
                quotechar='"',
                encoding=encoding,
                dtype=str,
                low_memory=False
            )

            used_encoding = encoding
            break

        except UnicodeDecodeError:
            continue

    if df is None:
        raise UnicodeError(
            "Não foi possível ler o arquivo usando "
            "utf-8-sig, cp1252 ou latin-1."
        )

    print(
        f"\nEncoding utilizado: {used_encoding}"
    )

    # Limpa possíveis espaços ou BOM nos nomes
    df.columns = (
        df.columns
        .str.replace("\ufeff", "", regex=False)
        .str.strip()
    )

    print("\nColunas encontradas:")

    for col in df.columns:
        print(" -", repr(col))

    # --------------------------------------------------
    # IDENTIFICA COLUNA DO MUNICÍPIO
    # --------------------------------------------------

    municipality_candidates = [
        "CD_MUN",
        "CD_MUNICIPIO",
        "CD_MUNICÍPIO",
        "COD_MUN",
        "COD_MUNICIPIO",
        "COD_MUNICÍPIO",
    ]

    municipality_column = next(
        (
            col
            for col in municipality_candidates
            if col in df.columns
        ),
        None
    )

    # --------------------------------------------------
    # IDENTIFICA COLUNAS DO BAIRRO
    # --------------------------------------------------

    neighborhood_code_candidates = [
        "CD_BAIRRO",
        "CD_BAIRRO_SUBDISTRITO",
        "COD_BAIRRO",
    ]

    neighborhood_name_candidates = [
        "NM_BAIRRO",
        "NOME_BAIRRO",
        "BAIRRO",
    ]

    neighborhood_code_column = next(
        (
            col
            for col in neighborhood_code_candidates
            if col in df.columns
        ),
        None
    )

    neighborhood_name_column = next(
        (
            col
            for col in neighborhood_name_candidates
            if col in df.columns
        ),
        None
    )

    # --------------------------------------------------
    # VALIDAÇÕES
    # --------------------------------------------------

    required_variables = [
        income_variable,
        income_weight,
        residents_variable,
    ]

    missing_variables = [
        col
        for col in required_variables
        if col not in df.columns
    ]

    if missing_variables:
        raise KeyError(
            "Variáveis não encontradas na base de "
            f"rendimento por bairro: {missing_variables}"
        )

    if neighborhood_code_column is None:
        raise KeyError(
            "Não foi possível identificar a coluna "
            "do código do bairro."
        )

    # --------------------------------------------------
    # FILTRO DO MUNICÍPIO
    # --------------------------------------------------

    municipality_code = str(
        municipality_code
    )

    if municipality_column is not None:

        df_filtered = df[
            df[municipality_column]
            .astype(str)
            .str.strip()
            .eq(municipality_code)
        ].copy()

    else:

        # Fallback caso não exista coluna CD_MUN
        df_filtered = df[
            df[neighborhood_code_column]
            .astype(str)
            .str.strip()
            .str.startswith(
                municipality_code,
                na=False
            )
        ].copy()

    if df_filtered.empty:
        raise ValueError(
            "Nenhum bairro encontrado para o município "
            f"{municipality_code}."
        )

    # --------------------------------------------------
    # SELEÇÃO DAS COLUNAS
    # --------------------------------------------------

    selected_columns = [
        neighborhood_code_column
    ]

    if neighborhood_name_column is not None:
        selected_columns.append(
            neighborhood_name_column
        )

    selected_columns.extend(
        [
            income_variable,
            income_weight,
            residents_variable,
        ]
    )

    renda_bairros = df_filtered[
        selected_columns
    ].copy()

    # --------------------------------------------------
    # RENOMEIA CHAVES
    # --------------------------------------------------

    rename_columns = {
        neighborhood_code_column: "CD_BAIRRO"
    }

    if neighborhood_name_column is not None:
        rename_columns[
            neighborhood_name_column
        ] = "NM_BAIRRO"

    renda_bairros = renda_bairros.rename(
        columns=rename_columns
    )

    # Mantém código como string
    renda_bairros["CD_BAIRRO"] = (
        renda_bairros["CD_BAIRRO"]
        .astype(str)
        .str.strip()
    )

    # --------------------------------------------------
    # CONVERSÃO NUMÉRICA
    # --------------------------------------------------

    numeric_columns = [
        income_variable,
        income_weight,
        residents_variable,
    ]

    for col in numeric_columns:

        renda_bairros[col] = (
            renda_bairros[col]
            .astype(str)
            .str.replace(",", ".", regex=False)
        )

        renda_bairros[col] = pd.to_numeric(
            renda_bairros[col],
            errors="coerce"
        )

    # --------------------------------------------------
    # DUPLICIDADES
    # --------------------------------------------------

    duplicated = (
        renda_bairros["CD_BAIRRO"]
        .duplicated()
        .sum()
    )

    if duplicated > 0:
        raise ValueError(
            f"Foram encontrados {duplicated} "
            "códigos de bairro duplicados."
        )

    # --------------------------------------------------
    # VALIDAÇÃO FINAL
    # --------------------------------------------------

    print(
        "\nNúmero de bairros encontrados:",
        len(renda_bairros)
    )

    print("\nPrimeiros registros:")

    print(
        renda_bairros.head()
    )

    print("\nValores ausentes:")

    print(
        renda_bairros[
            numeric_columns
        ]
        .isna()
        .sum()
    )

    return renda_bairros

# ==========
# Download da geometria do setor
def load_sector_geometry(
    zip_path: Path,
    municipality_code: str,
    target_crs: str,
    ) -> gpd.GeoDataFrame:
    """
    Carrega a malha de setores censitários do IBGE diretamente
    de um arquivo ZIP, filtra o município desejado e reprojeta
    para o CRS definido no projeto.

    Parameters
    ----------
    zip_path : Path
        Caminho para o arquivo ZIP contendo a malha de setores.

    municipality_code : str
        Código IBGE do município.
        Ex.: "4314902" para Porto Alegre.

    target_crs : str
        CRS de destino.
        Ex.: "EPSG:31982".

    Returns
    -------
    gpd.GeoDataFrame
        GeoDataFrame contendo apenas os setores do município.
    """

    zip_path = Path(zip_path)

    # --------------------------------------------------
    # VALIDAÇÕES INICIAIS
    # --------------------------------------------------

    if not zip_path.exists():
        raise FileNotFoundError(
            f"Arquivo da malha não encontrado: {zip_path}"
        )

    if zip_path.suffix.lower() != ".zip":
        raise ValueError(
            f"O arquivo informado não é um ZIP: {zip_path}"
        )

    # --------------------------------------------------
    # LEITURA DA MALHA
    # --------------------------------------------------

    print(f"\nLendo malha de setores: {zip_path.name}")

    setores = gpd.read_file(
        f"zip://{zip_path}"
    )

    print("Número total de setores:", len(setores))
    print("CRS original:", setores.crs)

    print("\nColunas encontradas:")

    for col in setores.columns:
        print(" -", repr(col))

    # --------------------------------------------------
    # VALIDAÇÃO DA CHAVE
    # --------------------------------------------------

    if "CD_SETOR" not in setores.columns:
        raise KeyError(
            "A coluna 'CD_SETOR' não foi encontrada "
            "na malha de setores."
        )

    # Garante que o código seja tratado como texto
    setores["CD_SETOR"] = (
        setores["CD_SETOR"]
        .astype(str)
        .str.strip()
    )

    # --------------------------------------------------
    # FILTRO DO MUNICÍPIO
    # --------------------------------------------------

    municipality_code = str(municipality_code)

    setores_municipio = setores[
        setores["CD_SETOR"].str.startswith(
            municipality_code,
            na=False
        )
    ].copy()

    if setores_municipio.empty:
        raise ValueError(
            "Nenhum setor encontrado para o município "
            f"de código {municipality_code}."
        )

    print(
        "\nSetores encontrados para o município:",
        len(setores_municipio)
    )

    # --------------------------------------------------
    # VALIDAÇÃO DAS GEOMETRIAS
    # --------------------------------------------------

    if setores_municipio.geometry.isna().any():
        print(
            "Aviso: existem geometrias ausentes "
            "na malha filtrada."
        )

    geometrias_invalidas = (
        ~setores_municipio.geometry.is_valid
    ).sum()

    if geometrias_invalidas > 0:
        print(
            f"Aviso: {geometrias_invalidas} "
            "geometrias inválidas encontradas."
        )

    # --------------------------------------------------
    # REPROJEÇÃO
    # --------------------------------------------------

    if setores_municipio.crs is None:
        raise ValueError(
            "A malha de setores não possui CRS definido."
        )

    setores_municipio = (
        setores_municipio.to_crs(
            target_crs
        )
    )

    print(
        "CRS após reprojeção:",
        setores_municipio.crs
    )

    # --------------------------------------------------
    # VERIFICA DUPLICATAS
    # --------------------------------------------------

    duplicados = (
        setores_municipio["CD_SETOR"]
        .duplicated()
        .sum()
    )

    if duplicados > 0:
        print(
            f"Aviso: {duplicados} códigos de setor "
            "duplicados foram encontrados."
        )

    # --------------------------------------------------
    # RESULTADO
    # --------------------------------------------------

    print("\nPrimeiros setores:")

    print(
        setores_municipio[
            ["CD_SETOR", "geometry"]
        ].head()
    )

    return setores_municipio

# ==========
# Carrega a malha de bairros 
def load_neighborhood_geometry(
    zip_path: Path,
    municipality_code: str,
    target_crs: str,
    ) -> gpd.GeoDataFrame:
    """
    Carrega a malha de bairros do IBGE diretamente de um arquivo ZIP,
    filtra o município desejado e reprojeta para o CRS definido.

    Parameters
    ----------
    zip_path : Path
        Caminho para o ZIP contendo a malha de bairros.

    municipality_code : str
        Código IBGE do município.
        Ex.: "4314902" para Porto Alegre.

    target_crs : str
        CRS de destino.
        Ex.: "EPSG:31982".

    Returns
    -------
    gpd.GeoDataFrame
        GeoDataFrame contendo apenas os bairros do município.
    """

    zip_path = Path(zip_path)

    # --------------------------------------------------
    # VALIDAÇÕES INICIAIS
    # --------------------------------------------------

    if not zip_path.exists():
        raise FileNotFoundError(
            f"Arquivo da malha de bairros não encontrado: {zip_path}"
        )

    if zip_path.suffix.lower() != ".zip":
        raise ValueError(
            f"O arquivo informado não é um ZIP: {zip_path}"
        )

    # --------------------------------------------------
    # LEITURA
    # --------------------------------------------------

    print(f"\nLendo malha de bairros: {zip_path.name}")

    bairros = gpd.read_file(
        f"zip://{zip_path}"
    )

    print("Número total de bairros:", len(bairros))
    print("CRS original:", bairros.crs)

    print("\nColunas encontradas:")

    for col in bairros.columns:
        print(" -", repr(col))

    # --------------------------------------------------
    # IDENTIFICA CHAVE DO BAIRRO
    # --------------------------------------------------

    neighborhood_code_candidates = [
        "CD_BAIRRO",
        "CD_BAIRRO_SUBDISTRITO",
        "COD_BAIRRO",
    ]

    neighborhood_name_candidates = [
        "NM_BAIRRO",
        "NOME_BAIRRO",
        "BAIRRO",
    ]

    neighborhood_code_column = next(
        (
            col
            for col in neighborhood_code_candidates
            if col in bairros.columns
        ),
        None
    )

    neighborhood_name_column = next(
        (
            col
            for col in neighborhood_name_candidates
            if col in bairros.columns
        ),
        None
    )

    if neighborhood_code_column is None:
        raise KeyError(
            "Não foi possível identificar a coluna "
            "de código do bairro."
        )

    # --------------------------------------------------
    # IDENTIFICA COLUNA DO MUNICÍPIO
    # --------------------------------------------------

    municipality_candidates = [
        "CD_MUN",
        "CD_MUNICIPIO",
        "CD_MUNICÍPIO",
        "COD_MUN",
        "COD_MUNICIPIO",
        "COD_MUNICÍPIO",
    ]

    municipality_column = next(
        (
            col
            for col in municipality_candidates
            if col in bairros.columns
        ),
        None
    )

    # --------------------------------------------------
    # GARANTE STRING
    # --------------------------------------------------

    bairros[neighborhood_code_column] = (
        bairros[neighborhood_code_column]
        .astype(str)
        .str.strip()
    )

    municipality_code = str(
        municipality_code
    )

    # --------------------------------------------------
    # FILTRO DO MUNICÍPIO
    # --------------------------------------------------

    if municipality_column is not None:

        bairros[municipality_column] = (
            bairros[municipality_column]
            .astype(str)
            .str.strip()
        )

        bairros_municipio = bairros[
            bairros[municipality_column]
            == municipality_code
        ].copy()

    else:

        # Fallback: usa o prefixo do código do bairro
        bairros_municipio = bairros[
            bairros[
                neighborhood_code_column
            ].str.startswith(
                municipality_code,
                na=False
            )
        ].copy()

    if bairros_municipio.empty:
        raise ValueError(
            "Nenhum bairro encontrado para o município "
            f"de código {municipality_code}."
        )

    print(
        "\nBairros encontrados para o município:",
        len(bairros_municipio)
    )

    # --------------------------------------------------
    # PADRONIZA NOMES DAS COLUNAS
    # --------------------------------------------------

    rename_columns = {
        neighborhood_code_column: "CD_BAIRRO"
    }

    if neighborhood_name_column is not None:
        rename_columns[
            neighborhood_name_column
        ] = "NM_BAIRRO"

    bairros_municipio = (
        bairros_municipio.rename(
            columns=rename_columns
        )
    )

    # --------------------------------------------------
    # VALIDAÇÃO DE GEOMETRIAS
    # --------------------------------------------------

    geometrias_ausentes = (
        bairros_municipio.geometry
        .isna()
        .sum()
    )

    if geometrias_ausentes > 0:
        print(
            f"Aviso: {geometrias_ausentes} "
            "geometrias ausentes."
        )

    geometrias_invalidas = (
        ~bairros_municipio.geometry.is_valid
    ).sum()

    if geometrias_invalidas > 0:
        print(
            f"Aviso: {geometrias_invalidas} "
            "geometrias inválidas encontradas."
        )

    # --------------------------------------------------
    # REPROJEÇÃO
    # --------------------------------------------------

    if bairros_municipio.crs is None:
        raise ValueError(
            "A malha de bairros não possui CRS definido."
        )

    bairros_municipio = (
        bairros_municipio.to_crs(
            target_crs
        )
    )

    print(
        "CRS após reprojeção:",
        bairros_municipio.crs
    )

    # --------------------------------------------------
    # DUPLICATAS
    # --------------------------------------------------

    duplicados = (
        bairros_municipio["CD_BAIRRO"]
        .duplicated()
        .sum()
    )

    if duplicados > 0:
        print(
            f"Aviso: {duplicados} códigos de bairro "
            "duplicados foram encontrados."
        )

    # --------------------------------------------------
    # RESULTADO
    # --------------------------------------------------

    cols_preview = [
        "CD_BAIRRO"
    ]

    if "NM_BAIRRO" in bairros_municipio.columns:
        cols_preview.append(
            "NM_BAIRRO"
        )

    cols_preview.append(
        "geometry"
    )

    print("\nPrimeiros bairros:")

    print(
        bairros_municipio[
            cols_preview
        ].head()
    )

    return bairros_municipio

# ==========
# Constrói o limite municipal a partir da união das geometrias
def build_municipal_boundary(
    gdf: gpd.GeoDataFrame,
    municipality_code: str | None = None,
    municipality_name: str | None = None,
    ) -> gpd.GeoDataFrame:
    """
    Constrói o limite municipal a partir da união das geometrias
    de uma malha já filtrada para um único município.

    Parameters
    ----------
    gdf : gpd.GeoDataFrame
        GeoDataFrame contendo as geometrias do município.
        Ex.: setores censitários de Porto Alegre.

    municipality_code : str, optional
        Código IBGE do município.

    municipality_name : str, optional
        Nome do município.

    Returns
    -------
    gpd.GeoDataFrame
        GeoDataFrame com uma única geometria representando
        o limite municipal.
    """

    # --------------------------------------------------
    # VALIDAÇÕES
    # --------------------------------------------------

    if gdf.empty:
        raise ValueError(
            "O GeoDataFrame está vazio. "
            "Não é possível construir o limite municipal."
        )

    if gdf.crs is None:
        raise ValueError(
            "O GeoDataFrame não possui CRS definido."
        )

    if gdf.geometry.isna().all():
        raise ValueError(
            "Todas as geometrias estão ausentes."
        )

    # --------------------------------------------------
    # REMOVE GEOMETRIAS NULAS
    # --------------------------------------------------

    valid_geometries = gdf.loc[
        gdf.geometry.notna()
    ].copy()

    # --------------------------------------------------
    # CORRIGE GEOMETRIAS INVÁLIDAS, SE NECESSÁRIO
    # --------------------------------------------------

    invalid_count = (
        ~valid_geometries.geometry.is_valid
    ).sum()

    if invalid_count > 0:
        print(
            f"Aviso: {invalid_count} geometrias inválidas "
            "foram encontradas."
        )

        valid_geometries["geometry"] = (
            valid_geometries.geometry.make_valid()
        )

    # --------------------------------------------------
    # UNIÃO DAS GEOMETRIAS
    # --------------------------------------------------

    boundary_geometry = (
        valid_geometries.geometry.union_all()
    )

    # --------------------------------------------------
    # CRIA GEODATAFRAME FINAL
    # --------------------------------------------------

    data = {}

    if municipality_code is not None:
        data["CD_MUN"] = [
            str(municipality_code)
        ]

    if municipality_name is not None:
        data["NM_MUN"] = [
            municipality_name
        ]

    limite = gpd.GeoDataFrame(
        data,
        geometry=[boundary_geometry],
        crs=gdf.crs
    )

    # --------------------------------------------------
    # VALIDAÇÃO FINAL
    # --------------------------------------------------

    if limite.geometry.iloc[0].is_empty:
        raise ValueError(
            "A geometria resultante do limite municipal está vazia."
        )

    print("\nLimite municipal criado com sucesso.")
    print("CRS:", limite.crs)
    print("Número de geometrias:", len(limite))

    return limite

# ==========
# Valida downloads
def validate_downloads(
    setores: gpd.GeoDataFrame,
    bairros: gpd.GeoDataFrame,
    limite: gpd.GeoDataFrame,
    income_variable: str,
    ) -> None:
    """
    Executa validações básicas nas bases processadas.

    Parameters
    ----------
    setores : gpd.GeoDataFrame
        Malha de setores já associada aos dados de renda.

    bairros : gpd.GeoDataFrame
        Malha de bairros do município.

    limite : gpd.GeoDataFrame
        Limite municipal construído a partir da malha.

    income_variable : str
        Nome da variável econômica principal.
        Ex.: "V06004".

    Returns
    -------
    None
        A função imprime um relatório de validação.
    """

    print("\n" + "=" * 70)
    print("VALIDAÇÃO DAS BASES")
    print("=" * 70)

    problemas = 0

    # --------------------------------------------------
    # FUNÇÃO AUXILIAR
    # --------------------------------------------------

    def check(
        description: str,
        condition: bool,
        details: str | None = None,
        ) -> None:

        nonlocal problemas

        if condition:
            print(f"✓ {description}")

        else:
            print(f"⚠ {description}")

            if details:
                print(f"  {details}")

            problemas += 1

        # ==================================================
        # 1. SETORES
        # ==================================================

        print("\n--- SETORES ---")

        check(
            "Base de setores não está vazia",
            not setores.empty,
        )

        check(
            "Setores possuem CRS",
            setores.crs is not None,
        )

        check(
            "Coluna CD_SETOR existe",
            "CD_SETOR" in setores.columns,
        )

        check(
            f"Variável {income_variable} existe",
            income_variable in setores.columns,
        )

        if "CD_SETOR" in setores.columns:

            duplicados = (
                setores["CD_SETOR"]
                .duplicated()
                .sum()
            )

            check(
                "CD_SETOR não possui duplicatas",
                duplicados == 0,
                f"{duplicados} duplicatas encontradas.",
            )

        # --------------------------------------------------
        # GEOMETRIAS DOS SETORES
        # --------------------------------------------------

        geometrias_nulas = (
            setores.geometry
            .isna()
            .sum()
        )

        check(
            "Setores não possuem geometrias nulas",
            geometrias_nulas == 0,
            f"{geometrias_nulas} geometrias nulas.",
        )

        if not setores.empty:

            geometrias_invalidas = (
                ~setores.geometry.is_valid
            ).sum()

            check(
                "Geometrias dos setores são válidas",
                geometrias_invalidas == 0,
                f"{geometrias_invalidas} geometrias inválidas.",
            )

        # --------------------------------------------------
        # RENDA
        # --------------------------------------------------

        if income_variable in setores.columns:

            renda = pd.to_numeric(
                setores[income_variable],
                errors="coerce"
            )

            renda_nula = (
                renda.isna().sum()
            )

            renda_negativa = (
                (renda.dropna() < 0)
                .sum()
            )

            check(
                f"{income_variable} possui dados",
                renda.notna().any(),
            )

            check(
                f"{income_variable} não possui valores negativos",
                renda_negativa == 0,
                f"{renda_negativa} valores negativos.",
            )

            taxa_match = (
                renda.notna().mean()
                * 100
            )

            print(
                f"  Correspondência renda/setores: "
                f"{taxa_match:.2f}%"
            )

            check(
                "Correspondência da renda é maior que 95%",
                taxa_match >= 95,
                (
                    f"Apenas {taxa_match:.2f}% dos setores "
                    "possuem renda."
                ),
            )

        # ==================================================
        # 2. BAIRROS
        # ==================================================

        print("\n--- BAIRROS ---")

        check(
            "Base de bairros não está vazia",
            not bairros.empty,
        )

        check(
            "Bairros possuem CRS",
            bairros.crs is not None,
        )

        check(
            "Coluna CD_BAIRRO existe",
            "CD_BAIRRO" in bairros.columns,
        )

        if "CD_BAIRRO" in bairros.columns:

            bairros_duplicados = (
                bairros["CD_BAIRRO"]
                .duplicated()
                .sum()
            )

            check(
                "CD_BAIRRO não possui duplicatas",
                bairros_duplicados == 0,
                (
                    f"{bairros_duplicados} códigos "
                    "de bairro duplicados."
                ),
            )

        bairros_geom_nulas = (
            bairros.geometry
            .isna()
            .sum()
        )

        check(
            "Bairros não possuem geometrias nulas",
            bairros_geom_nulas == 0,
            (
                f"{bairros_geom_nulas} geometrias "
                "de bairro nulas."
            ),
        )

        if not bairros.empty:

            bairros_invalidos = (
                ~bairros.geometry.is_valid
            ).sum()

            check(
                "Geometrias dos bairros são válidas",
                bairros_invalidos == 0,
                (
                    f"{bairros_invalidos} geometrias "
                    "inválidas."
                ),
            )

        # ==================================================
        # 3. LIMITE MUNICIPAL
        # ==================================================

        print("\n--- LIMITE MUNICIPAL ---")

        check(
            "Limite municipal não está vazio",
            not limite.empty,
        )

        check(
            "Limite possui CRS",
            limite.crs is not None,
        )

        check(
            "Limite possui apenas uma geometria",
            len(limite) == 1,
            (
                f"Foram encontradas {len(limite)} "
                "geometrias."
            ),
        )

        if not limite.empty:

            limite_geom = (
                limite.geometry.iloc[0]
            )

            check(
                "Geometria do limite não está vazia",
                not limite_geom.is_empty,
            )

            check(
                "Geometria do limite é válida",
                limite_geom.is_valid,
            )

        # ==================================================
        # 4. CRS
        # ==================================================

        print("\n--- CONSISTÊNCIA DE CRS ---")

        if (
            setores.crs is not None
            and bairros.crs is not None
        ):

            check(
                "Setores e bairros possuem o mesmo CRS",
                setores.crs == bairros.crs,
                (
                    f"Setores: {setores.crs} | "
                    f"Bairros: {bairros.crs}"
                ),
            )

        if (
            setores.crs is not None
            and limite.crs is not None
        ):

            check(
                "Setores e limite possuem o mesmo CRS",
                setores.crs == limite.crs,
                (
                    f"Setores: {setores.crs} | "
                    f"Limite: {limite.crs}"
                ),
            )

        # ==================================================
        # 5. EXTENSÃO ESPACIAL
        # ==================================================

        print("\n--- EXTENSÃO ESPACIAL ---")

        if (
            not setores.empty
            and not limite.empty
        ):

            setores_union = (
                setores.geometry
                .union_all()
            )

            limite_geom = (
                limite.geometry.iloc[0]
            )

            check(
                "Setores estão contidos no limite municipal",
                setores_union.within(
                    limite_geom.buffer(0.01)
                ),
            )

            # ==================================================
            # RESUMO
            # ==================================================

            print("\n" + "=" * 70)

            if problemas == 0:

                print(
                    "VALIDAÇÃO CONCLUÍDA: "
                    "nenhum problema crítico encontrado."
                )

            else:

                print(
                    "VALIDAÇÃO CONCLUÍDA COM ALERTAS."
                )

                print(
                    f"Total de verificações com problema: "
                    f"{problemas}"
                )

                print("=" * 70)

def load_basic_sector_data(
    source_dir,
    municipality_code,
    population_variable="V0001",
    avg_household_size_variable="V0005",
    households_variable="V0007",
):
    source_dir = Path(source_dir)

    csv_files = list(
        source_dir.rglob("*.csv")
    )

    if not csv_files:
        raise FileNotFoundError(
            f"Nenhum CSV encontrado em {source_dir}"
        )

    basic_files = [
        file
        for file in csv_files
        if "basico" in file.name.lower()
    ]

    if basic_files:
        csv_path = basic_files[0]
    else:
        csv_path = csv_files[0]

    print(
        f"Lendo agregados básicos: {csv_path.name}"
    )

    # --------------------------------------------------
    # LEITURA COM FALLBACK DE ENCODING
    # --------------------------------------------------

    encodings = [
        "utf-8-sig",
        "cp1252",
        "latin-1",
    ]

    df = None
    used_encoding = None

    for encoding in encodings:
        try:
            df = pd.read_csv(
                csv_path,
                sep=";",
                quotechar='"',
                encoding=encoding,
                dtype=str,
                low_memory=False
            )

            used_encoding = encoding
            break

        except UnicodeDecodeError:
            continue

    if df is None:
        raise UnicodeError(
            "Não foi possível ler o arquivo de agregados básicos "
            "usando utf-8-sig, cp1252 ou latin-1."
        )

    print(
        f"Encoding utilizado nos agregados básicos: "
        f"{used_encoding}"
    )

    # limpa nomes de colunas
    df.columns = (
        df.columns
        .str.replace("\ufeff", "", regex=False)
        .str.strip()
    )

    print("\nColunas encontradas nos agregados básicos:")

    for col in df.columns:
        print(" -", repr(col))

    required = [
        "CD_SETOR",
        population_variable,
        avg_household_size_variable,
        households_variable,
    ]

    missing = [
        col
        for col in required
        if col not in df.columns
    ]

    if missing:
        raise KeyError(
            "Colunas ausentes nos agregados básicos: "
            f"{missing}"
        )

    # --------------------------------------------------
    # FILTRA PORTO ALEGRE
    # --------------------------------------------------

    municipality_code = str(
        municipality_code
    )

    df["CD_SETOR"] = (
        df["CD_SETOR"]
        .astype(str)
        .str.strip()
    )

    poa = df.loc[
        df["CD_SETOR"].str.startswith(
            municipality_code,
            na=False
        ),
        required
    ].copy()

    # --------------------------------------------------
    # CONVERSÃO NUMÉRICA
    # --------------------------------------------------

    numeric_columns = [
        population_variable,
        avg_household_size_variable,
        households_variable,
    ]

    for col in numeric_columns:

        poa[col] = (
            poa[col]
            .astype(str)
            .str.replace(",", ".", regex=False)
        )

        poa[col] = pd.to_numeric(
            poa[col],
            errors="coerce"
        )

    # --------------------------------------------------
    # DUPLICIDADES
    # --------------------------------------------------

    duplicated = (
        poa["CD_SETOR"]
        .duplicated()
        .sum()
    )

    if duplicated > 0:
        raise ValueError(
            f"Foram encontrados {duplicated} "
            "CD_SETOR duplicados nos agregados básicos."
        )

    # --------------------------------------------------
    # VALIDAÇÃO
    # --------------------------------------------------

    print(
        f"\nSetores de Porto Alegre encontrados "
        f"nos agregados básicos: {len(poa)}"
    )

    print(
        "\nValores ausentes nos agregados básicos:"
    )

    print(
        poa[
            numeric_columns
        ]
        .isna()
        .sum()
    )

    print(
        "\nPrimeiros registros dos agregados básicos:"
    )

    print(
        poa.head()
    )

    return poa

def read_ibge_city(
    arquivo,
    codigo_municipio,
    coluna_setor="CD_SETOR",
    chunksize=100_000
):

    # Eu armazeno temporariamente os registros
    # encontrados para o município escolhido.

    resultados = []


    # Eu leio o arquivo em blocos porque as bases
    # nacionais do Censo podem ser muito grandes.

    for bloco in pd.read_csv(
        arquivo,
        sep=";",
        encoding="latin1",
        dtype={
            coluna_setor: "string"
        },
        chunksize=chunksize,
        low_memory=False
    ):

        selecionados = bloco[
            bloco[coluna_setor]
            .str.startswith(
                codigo_municipio,
                na=False
            )
        ].copy()


        if not selecionados.empty:

            resultados.append(
                selecionados
            )


    if not resultados:

        raise ValueError(
            f"Nenhum registro encontrado para "
            f"o município {codigo_municipio}."
        )


    return pd.concat(
        resultados,
        ignore_index=True
    )