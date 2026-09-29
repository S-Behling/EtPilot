def download_network(crs, city, network_type="drive"):
    """Baixa e reprojeta a rede viária da cidade."""
    import osmnx as ox

    place = city
    print(f"Baixando a rede de ruas de {place}...")

    graph = ox.graph_from_place(
        place,
        network_type=network_type,
    )

    graph = ox.project_graph(
        graph,
        to_crs=crs,
    )

    print(graph.graph["crs"])
    return graph


def download_neighborhood_network(
    neighborhood,
    crs,
    city,
    network_type="drive",
):
    """Baixa e reprojeta a rede viária de um bairro."""
    import osmnx as ox

    place = f"{neighborhood}, {city}"
    print(f"Baixando a rede de ruas de {place}...")

    graph = ox.graph_from_place(
        place,
        network_type=network_type,
    )

    graph = ox.project_graph(
        graph,
        to_crs=crs,
    )

    print(graph.graph["crs"])
    return graph
