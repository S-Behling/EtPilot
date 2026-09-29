
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


# Exportacao de dados para GeoPackage
# Especifico para exportar bairros, setores e renda em um único arquivo GeoPackage
def export_gpkg(dir, 
    bairros: gpd.GeoDataFrame,
    setores: gpd.GeoDataFrame,
    inter: gpd.GeoDataFrame,
) -> None:

    DIR_SAIDA = dir / "censo_2022" / "bairros_setores_renda.gpkg"
    
    DIR_SAIDA.mkdir(parents=True, exist_ok=True)

    if DIR_SAIDA.exists():
        DIR_SAIDA.unlink()

    print("[EXPORT] Escrevendo GeoPackage...")

    bairros.to_file(
        DIR_SAIDA,
        layer="bairros_renda",
        driver="GPKG",
    )

    setores.to_file(
        DIR_SAIDA,
        layer="setores_poa",
        driver="GPKG",
    )

    inter.to_file(
        DIR_SAIDA,
        layer="setores_bairro_renda",
        driver="GPKG",
    )

    print("\n" + "=" * 60)
    print("CONCLUÍDO")
    print("=" * 60)
    print(f"Arquivo: {DIR_SAIDA}")
    print(f"Bairros: {len(bairros)}")
    print(f"Setores: {len(setores)}")
    print(f"Fragmentos setor-bairro: {len(inter)}")
    print("\nCamadas:")
    print("  - bairros_renda")
    print("  - setores_poa")
    print("  - setores_bairro_renda")