# METODOS 

def classify_road_type(edge):

    highway = edge["highway"]

    if highway == "busway":
        return "Bus Corridor"

    elif highway == "primary":
        return "Arterial Road"

    elif highway == "secondary":
        return "Collector Road"

    elif highway == "secondary_link":
        return "Collector Link"

    elif highway == "tertiary":
        return "Local Collector"

    elif highway == "residential":
        return "Residential Street"

    return "Other"

def classify_road_type_pt(edge):

    highway = edge["highway"]

    if highway == "busway":
        return "Corredor de onibus"

    elif highway == "primary":
        return "Via Arterial"

    elif highway == "secondary":
        return "Via Coletora"

    elif highway == "secondary_link":
        return "Link Coletor"

    elif highway == "tertiary":
        return "Via Coletora Local"

    elif highway == "residential":
        return "Rua Residencial"

    return "Outro"


def classify_road_type2(edge):

    highway = edge.get("highway")

    if isinstance(highway, list):
        highway = highway[0]

    mapping = {
        "busway": "Bus Corridor",
        "motorway": "Motorway",
        "trunk": "Trunk Road",
        "primary": "Arterial Road",
        "secondary": "Collector Road",
        "secondary_link": "Collector Link",
        "tertiary": "Local Collector",
        "residential": "Residential Street"
    }

    return mapping.get(highway, "Other")


def classify_network(gdf_edges):

    gdf_edges = gdf_edges.copy()

    gdf_edges["road_type"] = gdf_edges.apply(
        classify_road_type_pt,
        axis=1
    )

    return gdf_edges

def classify_modal(edge):

    highway = edge["highway"]

    if highway == "busway":
        return "bus"

    elif highway in [
        "primary",
        "secondary",
        "tertiary",
        "residential"
    ]:
        return "car"

    elif highway == "cycleway":
        return "bike"

    elif highway == "footway":
        return "pedestrian"

    return "other"