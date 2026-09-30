"""Prepara os dados espaciais de uma região para o piloto.

Fluxo:
1. carrega a área regional;
2. carrega redes modais urbanas;
3. filtra origens e destinos;
4. recorta as redes;
5. faz snapping modal após o recorte;
6. filtra GTFS/ônibus para a mesma área;
7. salva cache regional e plots de diagnóstico.

Uso:
    python scripts/prepare_region.py --region city
    python scripts/prepare_region.py --region south
"""

from __future__ import annotations

import argparse

from _bootstrap import add_project_root_to_path

add_project_root_to_path()

import geopandas as gpd
import osmnx as ox

from src.core.config import (
    load_project_config,
    load_regions_config,
    project_path,
)
from src.network.multimodal import (
    assign_modal_nodes,
    load_mode_graphs,
)
from src.plot import (
    plot_modal_snapping,
    plot_regional_data,
    plot_transit_state,
    save_plot,
)
from src.spatial.regional_data import prepare_regional_data
from src.spatial.regions import build_study_area
from src.spatial.transit_filter import filter_transit_to_study_area
from src.transit.data import load_transit_data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepara recorte regional multimodal do EtPilot."
    )
    parser.add_argument(
        "--region",
        default=None,
        help="city, center, north, south ou east.",
    )
    return parser.parse_args()


def prepare_region(region_name: str | None = None) -> None:
    config = load_project_config()
    regions_config = load_regions_config(config)

    region_name = (
        region_name
        or config["study_area"]["default_region"]
    )

    neighborhoods_path = project_path(
        config["paths"]["neighborhoods"]
    )
    origins_path = project_path(
        config["paths"]["origins_income"]
    )
    destinations_path = project_path(
        config["paths"]["destinations"]
    )

    neighborhoods = gpd.read_file(
        neighborhoods_path,
        engine="pyogrio",
    )

    municipality_boundary = neighborhoods[
        ["geometry"]
    ].copy()

    study_area = build_study_area(
        region_name=region_name,
        regions_config=regions_config,
        municipality_boundary=municipality_boundary,
        neighborhoods=neighborhoods,
    )

    print(f"[area] {study_area.label}")

    graphs = load_mode_graphs(config)

    origins = gpd.read_file(
        origins_path,
        engine="pyogrio",
    )
    destinations = gpd.read_file(
        destinations_path,
        layer="destinations",
        engine="pyogrio",
    )

    regional = prepare_regional_data(
        study_area=study_area,
        origins=origins,
        destinations=destinations,
        graphs=graphs,
        network_buffer_m=float(
            config["routing"]["regional_network_buffer_m"]
        ),
    )

    regional_origins = assign_modal_nodes(
        regional.origins,
        regional.graphs,
    )
    regional_destinations = assign_modal_nodes(
        regional.destinations,
        regional.graphs,
    )

    transit = load_transit_data(config)
    regional_transit = filter_transit_to_study_area(
        transit,
        study_area,
        buffer_m=float(
            config["routing"]["regional_network_buffer_m"]
        ),
    )

    cache_dir = (
        project_path(config["paths"]["regional_cache"])
        / region_name
    )
    plots_dir = (
        project_path(config["paths"]["outputs"])
        / "diagnostics"
        / region_name
    )

    cache_dir.mkdir(
        parents=True,
        exist_ok=True,
    )
    plots_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    regional_origins.to_file(
        cache_dir / "origins.gpkg",
        driver="GPKG",
        engine="pyogrio",
    )
    regional_destinations.to_file(
        cache_dir / "destinations.gpkg",
        driver="GPKG",
        engine="pyogrio",
    )

    for mode, graph in regional.graphs.items():
        ox.save_graphml(
            graph,
            filepath=cache_dir / f"graph_{mode}.graphml",
        )

    regional_transit.stops.to_file(
        cache_dir / "transit_stops.gpkg",
        driver="GPKG",
        engine="pyogrio",
    )
    regional_transit.physical_edges.to_file(
        cache_dir / "transit_physical_edges.gpkg",
        driver="GPKG",
        engine="pyogrio",
    )
    regional_transit.connectors.to_parquet(
        cache_dir / "transit_connectors.parquet",
        index=False,
    )
    regional_transit.connections.to_parquet(
        cache_dir / "transit_connections.parquet",
        index=False,
    )
    regional_transit.connection_to_physical_edge.to_parquet(
        cache_dir / "transit_connection_to_physical_edge.parquet",
        index=False,
    )
    regional_transit.service_dates.to_parquet(
        cache_dir / "transit_service_dates.parquet",
        index=False,
    )

    regional_with_nodes = regional.__class__(
        study_area=regional.study_area,
        origins=regional_origins,
        destinations=regional_destinations,
        graphs=regional.graphs,
    )

    fig, _ = plot_regional_data(regional_with_nodes)
    save_plot(
        fig,
        plots_dir / "01_regional_data.png",
    )

    fig, _ = plot_modal_snapping(
        study_area=study_area,
        points=regional_origins,
        graphs=regional.graphs,
        sample_size=100,
        title=f"Snapping modal das origens — {study_area.label}",
    )
    save_plot(
        fig,
        plots_dir / "02_origin_snapping.png",
    )

    fig, _ = plot_transit_state(
        study_area=study_area,
        transit=regional_transit,
    )
    save_plot(
        fig,
        plots_dir / "03_transit.png",
    )

    print(
        "[ok] região preparada | "
        f"origens={len(regional_origins):,} | "
        f"destinos={len(regional_destinations):,} | "
        f"paradas={len(regional_transit.stops):,} | "
        f"conexões={len(regional_transit.connections):,}"
    )
    print(f"[cache] {cache_dir}")
    print(f"[plots] {plots_dir}")


def main() -> None:
    args = parse_args()
    prepare_region(
        region_name=args.region,
    )


if __name__ == "__main__":
    main()
