"""Filtragem regional dos produtos de transporte coletivo."""

from __future__ import annotations

from dataclasses import dataclass

import geopandas as gpd
import pandas as pd

from src.spatial.study_area import StudyArea
from src.transit.data import TransitData


@dataclass(frozen=True, slots=True)
class RegionalTransitData:
    """Dados GTFS consistentes com a área regional selecionada."""

    stops: gpd.GeoDataFrame
    connectors: pd.DataFrame
    connections: pd.DataFrame
    physical_edges: gpd.GeoDataFrame
    connection_to_physical_edge: pd.DataFrame
    service_dates: pd.DataFrame


def filter_transit_to_study_area(
    transit: TransitData,
    study_area: StudyArea,
    *,
    buffer_m: float = 0.0,
) -> RegionalTransitData:
    """Recorta paradas, arestas físicas e conexões para a área de estudo."""

    if buffer_m < 0:
        raise ValueError("buffer_m não pode ser negativo.")

    stops = _to_study_crs(transit.stops, study_area)
    physical_edges = _to_study_crs(
        transit.physical_edges,
        study_area,
    )

    geometry = (
        study_area.geometry.buffer(buffer_m)
        if buffer_m > 0
        else study_area.geometry
    )

    regional_stops = stops.loc[
        stops.geometry.map(geometry.covers)
    ].copy()

    regional_physical_edges = physical_edges.loc[
        physical_edges.geometry.intersects(geometry)
    ].copy()

    stop_ids = set(
        regional_stops["stop_id"].astype(str)
    )
    physical_ids = set(
        regional_physical_edges[
            "transit_physical_edge_id"
        ].astype(str)
    )

    mapping = transit.connection_to_physical_edge.copy()
    mapping["connection_id"] = mapping["connection_id"].astype(str)
    mapping["transit_physical_edge_id"] = (
        mapping["transit_physical_edge_id"].astype(str)
    )

    regional_mapping = mapping.loc[
        mapping["transit_physical_edge_id"].isin(physical_ids)
    ].copy()

    connection_ids = set(
        regional_mapping["connection_id"].astype(str)
    )

    connections = transit.connections.copy()
    connections["connection_id"] = (
        connections["connection_id"].astype(str)
    )
    connections["from_stop_id"] = (
        connections["from_stop_id"].astype(str)
    )
    connections["to_stop_id"] = (
        connections["to_stop_id"].astype(str)
    )

    regional_connections = connections.loc[
        connections["connection_id"].isin(connection_ids)
        & connections["from_stop_id"].isin(stop_ids)
        & connections["to_stop_id"].isin(stop_ids)
    ].copy()

    valid_connection_ids = set(
        regional_connections["connection_id"].astype(str)
    )

    regional_mapping = regional_mapping.loc[
        regional_mapping["connection_id"].isin(valid_connection_ids)
    ].copy()

    connectors = transit.connectors.copy()
    connectors["stop_id"] = connectors["stop_id"].astype(str)
    regional_connectors = connectors.loc[
        connectors["stop_id"].isin(stop_ids)
    ].copy()

    active_service_ids = set(
        regional_connections["service_id"].astype(str)
    )

    service_dates = transit.service_dates.copy()
    service_dates["service_id"] = (
        service_dates["service_id"].astype(str)
    )
    regional_service_dates = service_dates.loc[
        service_dates["service_id"].isin(active_service_ids)
    ].copy()

    return RegionalTransitData(
        stops=regional_stops,
        connectors=regional_connectors,
        connections=regional_connections,
        physical_edges=regional_physical_edges,
        connection_to_physical_edge=regional_mapping,
        service_dates=regional_service_dates,
    )


def _to_study_crs(
    data: gpd.GeoDataFrame,
    study_area: StudyArea,
) -> gpd.GeoDataFrame:
    if data.crs is None:
        raise ValueError("GeoDataFrame de transporte sem CRS.")

    if str(data.crs) == str(study_area.crs):
        return data.copy()

    return data.to_crs(study_area.crs)
