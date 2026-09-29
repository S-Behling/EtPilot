from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import osmnx as ox


def _prepare_output_path(output_path: str | Path) -> Path:
    """Cria o diretório de saída e retorna o caminho normalizado."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return output_path


def _finish_map(
    figure,
    axes,
    output_path: str | Path,
    title: str,
    dpi: int = 300,
) -> Path:
    """Aplica acabamento comum, salva e fecha a figura."""
    output_path = _prepare_output_path(output_path)

    axes.set_title(title, fontsize=14, pad=12)
    axes.set_axis_off()
    axes.set_aspect("equal")

    figure.tight_layout()
    figure.savefig(
        output_path,
        dpi=dpi,
        bbox_inches="tight",
    )
    plt.close(figure)

    print(f"[MAPA] Salvo em: {output_path}")
    return output_path


# ============================================================
# FUNÇÃO LEGADA
# ============================================================

def plot_network(
    gdf_edges,
    column=None,
    figsize=(12, 12),
    legend=True,
    linewidth=1.5,
):
    """
    Plota uma rede a partir de um GeoDataFrame de arestas.

    Mantida por compatibilidade com notebooks existentes.
    """
    figure, axes = plt.subplots(figsize=figsize)

    gdf_edges.plot(
        ax=axes,
        column=column,
        legend=legend,
        linewidth=linewidth,
    )

    axes.set_axis_off()

    return figure, axes


# ============================================================
# MAPA 1 — RENDA
# ============================================================

def plot_income_map(
    regions: gpd.GeoDataFrame,
    value_column: str,
    output_path: str | Path,
    title: str = "Renda média por bairro",
    cmap: str = "YlOrRd",
    boundary: gpd.GeoDataFrame | None = None,
    dpi: int = 300,
) -> Path:
    """
    Gera mapa coroplético contínuo com gradiente de renda.

    Parameters
    ----------
    regions
        Regiões a serem coloridas. No piloto, bairros de Porto Alegre.
    value_column
        Coluna numérica usada no gradiente.
    output_path
        Caminho do PNG de saída.
    title
        Título do mapa.
    cmap
        Paleta contínua do Matplotlib.
    boundary
        Limite municipal opcional.
    dpi
        Resolução da imagem.
    """
    if value_column not in regions.columns:
        raise KeyError(
            f"A coluna '{value_column}' não existe no GeoDataFrame. "
            f"Colunas disponíveis: {list(regions.columns)}"
        )

    gdf = regions.copy()
    gdf[value_column] = gdf[value_column].astype("float64")

    figure, axes = plt.subplots(figsize=(12, 12))

    gdf.plot(
        ax=axes,
        column=value_column,
        cmap=cmap,
        legend=True,
        linewidth=0.35,
        edgecolor="white",
        missing_kwds={
            "color": "lightgray",
            "edgecolor": "white",
            "label": "Sem dado",
        },
        legend_kwds={
            "label": "Renda média do responsável pelo domicílio (R$)",
            "shrink": 0.72,
        },
    )

    if boundary is not None and not boundary.empty:
        boundary.boundary.plot(
            ax=axes,
            linewidth=1.0,
            color="black",
        )

    return _finish_map(
        figure=figure,
        axes=axes,
        output_path=output_path,
        title=title,
        dpi=dpi,
    )


# ============================================================
# MAPA 2 — REDES
# ============================================================

def plot_networks_map(
    city_graph,
    output_path: str | Path,
    neighborhood_graph=None,
    boundary: gpd.GeoDataFrame | None = None,
    title: str = "Redes viárias do piloto",
    dpi: int = 300,
) -> Path:
    """
    Gera mapa da rede municipal e, quando fornecida, destaca a rede
    do bairro-piloto.

    O grafo municipal é desenhado como contexto e a rede do bairro
    recebe maior espessura para evidenciar o recorte piloto.
    """
    _, city_edges = ox.graph_to_gdfs(city_graph)

    figure, axes = plt.subplots(figsize=(12, 12))

    if boundary is not None and not boundary.empty:
        boundary.plot(
            ax=axes,
            facecolor="white",
            edgecolor="black",
            linewidth=0.8,
        )

    city_edges.plot(
        ax=axes,
        linewidth=0.35,
        color="0.55",
        label="Rede municipal",
    )

    if neighborhood_graph is not None:
        _, neighborhood_edges = ox.graph_to_gdfs(
            neighborhood_graph
        )

        neighborhood_edges.plot(
            ax=axes,
            linewidth=1.0,
            color="black",
            label="Rede do bairro-piloto",
        )

        axes.legend(
            loc="lower left",
            frameon=True,
        )

    return _finish_map(
        figure=figure,
        axes=axes,
        output_path=output_path,
        title=title,
        dpi=dpi,
    )


# ============================================================
# MAPA 3 — BAIRROS E SETORES
# ============================================================

def plot_neighborhoods_sectors_map(
    neighborhoods: gpd.GeoDataFrame,
    sectors: gpd.GeoDataFrame,
    output_path: str | Path,
    title: str = "Bairros e setores censitários",
    dpi: int = 300,
) -> Path:
    """
    Gera mapa comparando os limites administrativos dos bairros
    com a malha fina dos setores censitários.
    """
    bairros = neighborhoods.copy()
    setores = sectors.copy()

    if bairros.crs != setores.crs:
        setores = setores.to_crs(bairros.crs)

    figure, axes = plt.subplots(figsize=(12, 12))

    setores.boundary.plot(
        ax=axes,
        linewidth=0.25,
        color="0.70",
        label="Setores censitários",
    )

    bairros.boundary.plot(
        ax=axes,
        linewidth=1.1,
        color="black",
        label="Bairros",
    )

    axes.legend(
        loc="lower left",
        frameon=True,
    )

    return _finish_map(
        figure=figure,
        axes=axes,
        output_path=output_path,
        title=title,
        dpi=dpi,
    )


# ============================================================
# ORQUESTRADOR
# ============================================================

def generate_pilot_maps(
    income_regions: gpd.GeoDataFrame,
    neighborhoods: gpd.GeoDataFrame,
    sectors: gpd.GeoDataFrame,
    city_graph,
    output_dir: str | Path,
    income_column: str = "RENDA_MED_BAIRRO",
    neighborhood_graph=None,
    boundary: gpd.GeoDataFrame | None = None,
) -> dict[str, Path]:
    """
    Gera os três mapas finais de diagnóstico do piloto.

    Returns
    -------
    dict[str, Path]
        Caminhos das imagens geradas.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    income_map = plot_income_map(
        regions=income_regions,
        value_column=income_column,
        output_path=output_dir / "mapa_renda_gradiente.png",
        title="Distribuição da renda média por bairro",
        boundary=boundary,
    )

    network_map = plot_networks_map(
        city_graph=city_graph,
        neighborhood_graph=neighborhood_graph,
        boundary=boundary,
        output_path=output_dir / "mapa_redes.png",
        title="Rede viária de Porto Alegre e recorte piloto",
    )

    neighborhoods_sectors_map = plot_neighborhoods_sectors_map(
        neighborhoods=neighborhoods,
        sectors=sectors,
        output_path=output_dir / "mapa_bairros_setores.png",
        title="Bairros e setores censitários de Porto Alegre",
    )

    return {
        "income_map": income_map,
        "network_map": network_map,
        "neighborhoods_sectors_map": neighborhoods_sectors_map,
    }
