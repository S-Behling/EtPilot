"""Baixa e salva as redes OSM multimodais de Porto Alegre.

Uso:
    python scripts/prepare_city_networks.py
    python scripts/prepare_city_networks.py --force

Por padrão, redes já existentes não são baixadas novamente.
"""

from __future__ import annotations

import argparse

from _bootstrap import add_project_root_to_path

add_project_root_to_path()

import osmnx as ox

from src.core.config import load_project_config
from src.network.multimodal import (
    SUPPORTED_MODES,
    graph_path_for_mode,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepara as redes OSM multimodais da cidade."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Baixa novamente mesmo quando o GraphML já existe.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_project_config()

    place = config["study_area"]["place"]
    crs = config["study_area"]["crs"]
    network_types = config["study_area"]["network_types"]

    for mode in SUPPORTED_MODES:
        path = graph_path_for_mode(config, mode)

        if path.exists() and not args.force:
            print(f"[skip] {mode}: {path}")
            continue

        network_type = network_types[mode]

        print(
            f"[download] {mode} | network_type={network_type} | {place}"
        )

        graph = ox.graph_from_place(
            place,
            network_type=network_type,
        )
        graph = ox.project_graph(
            graph,
            to_crs=crs,
        )

        path.parent.mkdir(parents=True, exist_ok=True)

        ox.save_graphml(
            graph,
            filepath=path,
        )

        print(
            f"[ok] {mode}: "
            f"{graph.number_of_nodes():,} nós | "
            f"{graph.number_of_edges():,} arestas"
        )


if __name__ == "__main__":
    main()
