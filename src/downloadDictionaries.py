from pathlib import Path
import requests


# ============================================================
# CAMINHOS DO PROJETO
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = PROJECT_ROOT / "data"
DICTIONARY_DIR = DATA_DIR / "dicionarios"

DICTIONARY_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# URLS OFICIAIS DO IBGE
# ============================================================

URL_DICIONARIO_RENDA = (
    "https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/"
    "Agregados_por_Setores_Censitarios_Rendimento_do_Responsavel/"
    "dicionario_de_dados_renda_responsavel_20260508.xlsx"
)

URL_DICIONARIO_AGREGADOS = (
    "https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/"
    "Agregados_por_Setores_Censitarios/"
    "dicionario_de_dados_agregados_por_setores_censitarios_20260520.xlsx"
)


# ============================================================
# FUNÇÃO DE DOWNLOAD
# ============================================================

def download_file(
    url: str,
    destination: Path,
) -> Path:

    destination = Path(destination)

    if destination.exists():

        print(
            f"Arquivo já existe: "
            f"{destination.name}"
        )

        return destination

    print(
        f"Baixando: {destination.name}"
    )

    response = requests.get(
        url,
        stream=True,
        timeout=120
    )

    response.raise_for_status()

    with open(destination, "wb") as f:

        for chunk in response.iter_content(
            chunk_size=1024 * 1024
        ):

            if chunk:
                f.write(chunk)

    print(
        f"Download concluído: "
        f"{destination}"
    )

    return destination


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("DOWNLOAD DOS DICIONÁRIOS — CENSO 2022")
    print("=" * 70)

    # --------------------------------------------------------
    # DICIONÁRIO DE RENDA
    # --------------------------------------------------------

    renda_path = (
        DICTIONARY_DIR
        / "dicionario_renda_responsavel.xlsx"
    )

    download_file(
        url=URL_DICIONARIO_RENDA,
        destination=renda_path
    )

    # --------------------------------------------------------
    # DICIONÁRIO DOS AGREGADOS
    # --------------------------------------------------------

    agregados_path = (
        DICTIONARY_DIR
        / "dicionario_agregados_setores.xlsx"
    )

    download_file(
        url=URL_DICIONARIO_AGREGADOS,
        destination=agregados_path
    )

    # --------------------------------------------------------
    # RESULTADO
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("DICIONÁRIOS DISPONÍVEIS")
    print("=" * 70)

    print(
        "Rendimento:",
        renda_path
    )

    print(
        "Agregados:",
        agregados_path
    )

    print("=" * 70)


# ============================================================
# EXECUÇÃO
# ============================================================

if __name__ == "__main__":
    main()