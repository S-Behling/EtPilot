import json
from pathlib import Path

import osmnx as ox
import geopandas as gpd
import pandas as pd
import numpy as np

from pyproj import CRS

# SUBCATEGORIAS FUNCIONAIS

# Preserva a classificação mais específica disponível no OpenStreetMap para cada destino.

def obter_subcategoria(row):

    # Para compras, eu priorizo a classificação shop.
    if row["category"] == "shopping":

        if pd.notna(row.get("shop")):
            return row["shop"]

        return row.get("amenity")


    # Para educação e saúde, a classificação principal
    # é obtida através de amenity.
    if row["category"] in {
        "education",
        "health"
    }:

        return row.get("amenity")


    # Para lazer, eu priorizo leisure e utilizo amenity
    # quando leisure não estiver disponível.
    if row["category"] == "leisure":

        if pd.notna(row.get("leisure")):
            return row["leisure"]

        return row.get("amenity")


    return None


