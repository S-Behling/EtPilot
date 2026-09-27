import sys
from pathlib import Path
import requests
import zipfile

#sys.path.append(str(Path.cwd().parent))

# Importa metodos
import data_utils as dwl

# ============================================================
# 1. DIRETÓRIOS DO PROJETO
# ============================================================

# Identifica a raiz do projeto

CURRENT_DIR = Path.cwd()

if CURRENT_DIR.name == "notebooks":
    PROJECT_ROOT = CURRENT_DIR.parent
else:
    PROJECT_ROOT = CURRENT_DIR


# Cria uma pasta específica para os dados do Censo 2022

CENSO_DIR = (
    PROJECT_ROOT
    / "data"
    / "censo_2022"
)


MICRODADOS_DIR = (
    CENSO_DIR
    / "microdados_publicos"
)


APOND_DIR = (
    CENSO_DIR
    / "areas_ponderacao"
)


DOCUMENTACAO_DIR = (
    CENSO_DIR
    / "dicionarios"
)


# Cria as pastas caso ainda não existam

for pasta in [
    CENSO_DIR,
    MICRODADOS_DIR,
    APOND_DIR,
    DOCUMENTACAO_DIR
]:
    pasta.mkdir(
        parents=True,
        exist_ok=True
    )


print(CENSO_DIR)

# ============================================================
# 2. MICRODADOS PÚBLICOS - RIO GRANDE DO SUL
# ============================================================

# Somente os dados do Censo 2022

URL_MICRODADOS_RS = (
    "https://ftp.ibge.gov.br/"
    "Censos/Censo_Demografico_2022/"
    "Microdados_e_Areas_de_Ponderacao/"
    "Microdados_de_acesso_Publico/"
    "csv/"
    "43_RS.zip"
)


MICRODADOS_ZIP = (
    MICRODADOS_DIR
    / "43_RS.zip"
)


dwl.baixar_arquivo(URL_MICRODADOS_RS, MICRODADOS_ZIP)

# ============================================================
# 3. EXTRAÇÃO DOS MICRODADOS
# ============================================================

MICRODADOS_EXTRAIDOS = (
    MICRODADOS_DIR
    / "43_RS"
)


MICRODADOS_EXTRAIDOS.mkdir(
    parents=True,
    exist_ok=True
)


with zipfile.ZipFile(
    MICRODADOS_ZIP,
    "r"
) as zip_ref:

    zip_ref.extractall(
        MICRODADOS_EXTRAIDOS
    )


print("Microdados extraídos em:")

print(MICRODADOS_EXTRAIDOS)

for arquivo in MICRODADOS_EXTRAIDOS.rglob("*"):

    if arquivo.is_file():

        print(arquivo.name)


# ============================================================
# 4. TABELAS DAS ÁREAS DE PONDERAÇÃO
# ============================================================

URL_APOND_TABELAS = (
    "https://ftp.ibge.gov.br/"
    "Censos/Censo_Demografico_2022/"
    "Microdados_e_Areas_de_Ponderacao/"
    "Areas_de_Ponderacao/"
    "tabelas_xlsx.zip"
)


APOND_ZIP = (
    APOND_DIR
    / "tabelas_xlsx.zip"
)


dwl.baixar_arquivo(
    URL_APOND_TABELAS,
    APOND_ZIP
)

APOND_EXTRAIDAS = (
    APOND_DIR
    / "tabelas_xlsx"
)


APOND_EXTRAIDAS.mkdir(
    parents=True,
    exist_ok=True
)


with zipfile.ZipFile(APOND_ZIP,"r") as zip_ref:
    zip_ref.extractall(APOND_EXTRAIDAS)


print("Tabelas das APONDs extraídas em:")
print(APOND_EXTRAIDAS)

for arquivo in APOND_EXTRAIDAS.rglob("*"):
    if arquivo.is_file():
        print(arquivo.name)

# D0090 → Área de Ponderação
# D0110 → peso amostral do acesso público
# D0111 → peso amostral do acesso controlado

# ============================================================
# 5. VALIDAÇÃO DOS DOWNLOADS
# ============================================================

arquivos = {
    "Microdados RS": MICRODADOS_ZIP,
    "Tabelas APOND": APOND_ZIP
}


for nome, caminho in arquivos.items():

    print(
        f"{nome}:",
        "OK"
        if caminho.exists()
        else "ERRO"
    )

for arquivo in MICRODADOS_EXTRAIDOS.rglob("*"):
    if arquivo.is_file():
        print(arquivo.name)

for arquivo in APOND_EXTRAIDAS.rglob("*"):
    if arquivo.is_file():
        print(arquivo.name)