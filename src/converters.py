
import geopandas as gpd


def shapefile_to_gpkg(
    input_path: str,
    output_path: str,
    layer: str
):
    """
    Converte um arquivo Shapefile para GeoPackage.

    Parameters
    ----------
    input_path : str
        Caminho do arquivo .shp.
    output_path : str
        Caminho do arquivo .gpkg que será criado.
    layer : str
        Nome da camada dentro do GeoPackage.
    """

    gdf = gpd.read_file(input_path)

    gdf.to_file(
        output_path,
        layer=layer,
        driver="GPKG"
    )

    print(f"Conversão concluída: {output_path}")