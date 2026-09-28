"""Prepara as bases espaciais para o roteamento multimodal do piloto.

Uso
---
Depois de baixar as três redes em `01_download_network.ipynb`:

    python -m src.network.prepare_multimodal_data

O comando:
1. adiciona node_car, node_walk e node_bike às origens socioeconômicas;
2. reconstrói os destinos CNEFE com nós específicos por modo.
"""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd

from src.destinationsCNEFE import build_destinations_cnefe
from src.network.multimodal import (
    assign_modal_nodes,
    load_mode_graphs,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config" / "config.json"


def load_config() -> dict:
    with CONFIG_PATH.open(
        "r",
        encoding="utf-8",
    ) as f:
        return json.load(f)


def _replace_gpkg(
    gdf: gpd.GeoDataFrame,
    path: Path,
) -> None:
    """Substitui um GeoPackage de forma explícita."""

    temporary = path.with_name(
        f"{path.stem}.tmp{path.suffix}"
    )

    if temporary.exists():
        temporary.unlink()

    gdf.to_file(
        temporary,
        driver="GPKG",
        engine="pyogrio",
    )

    if path.exists():
        path.unlink()

    temporary.replace(path)


def prepare_origins(
    config: dict,
    graphs: dict[str, object],
) -> gpd.GeoDataFrame:
    origins_path = (
        PROJECT_ROOT
        / config["paths"]["origins_income"]
    )

    if not origins_path.exists():
        raise FileNotFoundError(
            "Base de origens socioeconômicas não encontrada: "
            f"{origins_path}"
        )

    origins = gpd.read_file(
        origins_path,
        engine="pyogrio",
    )

    prefix = config["routing"].get(
        "node_column_prefix",
        "node_",
    )

    origins = assign_modal_nodes(
        origins,
        graphs,
        prefix=prefix,
    )

    _replace_gpkg(
        origins,
        origins_path,
    )

    print(
        "Origens atualizadas:",
        origins_path,
    )

    print(
        origins[
            [
                "origin_id",
                f"{prefix}car",
                f"{prefix}walk",
                f"{prefix}bike",
            ]
        ]
        .head()
        .to_string(index=False)
    )

    return origins


def main() -> None:
    config = load_config()

    print("1/3 — Carregando redes modais...")
    graphs = load_mode_graphs(
        config=config,
        project_root=PROJECT_ROOT,
    )

    print("2/3 — Atualizando origens...")
    prepare_origins(
        config=config,
        graphs=graphs,
    )

    print("3/3 — Reconstruindo destinos CNEFE...")
    build_destinations_cnefe()

    print(
        "\nOK: origens e destinos possuem nós "
        "específicos para car, walk e bike."
    )


if __name__ == "__main__":
    main()
