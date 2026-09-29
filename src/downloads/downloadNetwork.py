

def download_network(crs, city):
    import osmnx as ox
    
    # Monta a string
    place = city

    # Selecao da regiao de interesse
    #place = "Porto Alegre, Rio Grande do Sul, Brazil"
    print(f"Baixando a rede de ruas de {place}...")

    graph = ox.graph_from_place(
        place,
        network_type="drive"
    )

    # Converte o grafo para o sistema de coordenadas desejado (definido no arquivo config.json)
    graph = ox.project_graph(graph, to_crs=crs)

    print(graph.graph["crs"])

    return graph

def download_neighborhood_network(neighborhood, crs, city):
    import osmnx as ox
    
    # Monta a string
    place = f"{neighborhood}, {city}"

    # Selecao da regiao de interesse
    #place = "Bom Fim, Porto Alegre, Rio Grande do Sul, Brazil"
    print(f"Baixando a rede de ruas de {place}...")

    graph = ox.graph_from_place(
        place,
        network_type="drive"
    )

    # Converte o grafo para o sistema de coordenadas desejado (definido no arquivo config.json)
    graph = ox.project_graph(graph, to_crs=crs)
    print(graph.graph["crs"])

    return graph

    
    