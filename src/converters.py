from pathlib import Path

import geopandas as gpd


def shapefile_to_gpkg(
    input_path: str,
    output_path: str,
    layer: str,
):
    """Converte um Shapefile para GeoPackage."""
    gdf = gpd.read_file(input_path)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    gdf.to_file(
        output_path,
        layer=layer,
        driver="GPKG",
    )

    print(f"Conversão concluída: {output_path}")


def export_gpkg(
    output_file: str | Path,
    bairros: gpd.GeoDataFrame,
    setores: gpd.GeoDataFrame,
    inter: gpd.GeoDataFrame,
) -> Path:
    """
    Exporta bairros, setores e a interseção setor-bairro
    para um único GeoPackage.
    """
    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    if output_file.exists():
        output_file.unlink()

    print("[EXPORT] Escrevendo GeoPackage...")

    bairros.to_file(
        output_file,
        layer="bairros_renda",
        driver="GPKG",
    )

    setores.to_file(
        output_file,
        layer="setores_poa",
        driver="GPKG",
    )

    inter.to_file(
        output_file,
        layer="setores_bairro_renda",
        driver="GPKG",
    )

    print("\n" + "=" * 60)
    print("CONCLUÍDO")
    print("=" * 60)
    print(f"Arquivo: {output_file}")
    print(f"Bairros: {len(bairros)}")
    print(f"Setores: {len(setores)}")
    print(f"Fragmentos setor-bairro: {len(inter)}")
    print("\nCamadas:")
    print("  - bairros_renda")
    print("  - setores_poa")
    print("  - setores_bairro_renda")

    return output_file
