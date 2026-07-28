# METODOS 
def classify_road_type(edge, mapping):
    highway = edge.get("highway")

    if isinstance(highway, list):
        highway = highway[0]

    return mapping.get(highway, "Other")


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

def classify_network(gdf_edges, mapping):

    gdf_edges["road_type"] = gdf_edges.apply(
        lambda edge: classify_road_type(edge, mapping),
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