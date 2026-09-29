#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import sys
import io
import re
import shutil
import urllib.request
import zipfile
import json
from pathlib import Path
import osmnx as ox
import src

import src
import geopandas as gpd
import pandas as pd
from src.downloads.downloadDataCNEFE import (
    download,
    download_cnefe,
    ler_renda_bairros,
    preparar_bairros,
    preparar_setores,
    sobrepor_setores_bairros
)

from src import converters

# ============================================================
# CONFIGURAÇÕES
# ============================================================

# Carrega o arquivo de json de configuração
#   open -> inputs: arquivo, modo de abertura, codificação
with open("../config/config.json", "r", encoding="utf-8") as config_file:
    config = json.load(config_file)

# Configurações
study_area = config["study_area"]
crs = study_area["crs"]

city = study_area["place"]
cod_city = study_area["cod_municipio"]
network_type = study_area["network_type"]

# Escolha do bairro (primeiro da lista), se quiser
neighborhood = study_area["districts"][0]

# ============================================================
# URLS
# ============================================================

URL_BAIRROS = (
    "https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/"
    "Agregados_por_Setores_Censitarios/malha_com_atributos/"
    "bairros/gpkg/UF/RS/RS_bairros_CD2022.gpkg"
)

URL_SETORES = (
    "https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/"
    "Agregados_por_Setores_Censitarios/malha_com_atributos/"
    "setores/gpkg/UF/RS/RS_setores_CD2022.gpkg"
)

URL_RENDA_BAIRROS = (
    "https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/"
    "Agregados_por_Setores_Censitarios_Rendimento_do_Responsavel/"
    "Agregados_por_bairros_renda_responsavel_BR_20260508_csv.zip"
)

IBGE_CNEFE_BASE_URL = (
    "https://ftp.ibge.gov.br/"
    "Cadastro_Nacional_de_Enderecos_para_Fins_Estatisticos/"
    "Censo_Demografico_2022/"
    "Arquivos_CNEFE/CSV/Municipio"
)

CSV_RENDA_NO_ZIP = "Agregados_por_bairros_renda_responsavel_BR.csv"

# ============================================================
# DIRETORIOS DE SAÍDA
# ============================================================
BASE_DIR = Path(__file__).resolve().parent
DIR_DADOS = BASE_DIR / "data"
DIR_CENSO = BASE_DIR / "data" /"censo_2022"
print(DIR_CENSO)
ARQ_BAIRROS = "bairros_poa.gpkg"
ARQ_SETORES = "setores_poa.gpkg"    
ARQ_RENDA_BAIRROS = "renda_bairros_poa.gpkg"


# ============================================================
# DOWNLOADS
# ============================================================

# Rede
network_graph = src.downloadNetwork.download_network(study_area, crs, city)
# Rede bairro
neighborhood_network_graph = src.download_neighborhood_network(neighborhood, crs, city)
# Bairro
neighborhood = src.downloadDataCNEFE.download(URL_BAIRROS, DIR_CENSO / ARQ_BAIRROS)
# Setores
setores = src.downloadDataCNEFE.download(URL_SETORES, DIR_CENSO / ARQ_SETORES)
# Renda por bairro
#neighborhood_income = src.downloadDataCNEFE.download(URL_RENDA_BAIRROS, DIR_CENSO / ARQ_RENDA_BAIRROS)
neighborhood_income = gpd.read_file("../data/censo_2022/renda_bairros.gpkg")
print("[LEITURA] Renda oficial por bairro...")

income = ler_renda_bairros(neighborhood_income, CSV_RENDA_NO_ZIP, cod_city)
print(f"[OK] Registros de renda de Porto Alegre: {len(income)}")
bairros = preparar_bairros(income, crs, ARQ_BAIRROS)
setores = preparar_setores(crs, ARQ_SETORES)
inter = sobrepor_setores_bairros(setores, bairros)

converters.export_gpkg(bairros, setores, inter)
# ============================================================
# INFORMACOES
# ============================================================

# Informacoes da rede/grafo
print(network_graph)
print(f"Nós: {len(network_graph.nodes)}")
print(f"Arestas: {len(network_graph.edges)}")

print(neighborhood_network_graph)
print(f"Nós: {len(neighborhood_network_graph.nodes)}")
print(f"Arestas: {len(neighborhood_network_graph.edges)}")



# ============================================================
# SAVES
# ============================================================

DIR_DADOS.mkdir(parents=True, exist_ok=True)

ox.save_graphml(network_graph, "../data/graph/rede-poa.graphml")
ox.save_graphml(neighborhood_network_graph, "../data/graph/rede-bomFim.graphml")