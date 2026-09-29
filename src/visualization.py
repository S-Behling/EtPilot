from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patheffects as path_effects
import numpy as np
import osmnx as ox
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.lines import Line2D


def _soft_colormap(
    cmap_name: str,
    start: float = 0.08,
    end: float = 0.78,
    white_mix: float = 0.38,
) -> LinearSegmentedColormap:
    """
    Retorna uma versão suave/pastel de um colormap contínuo.

    Além de evitar os extremos mais saturados da paleta, mistura as cores
    com branco. O resultado preserva as diferenças relativas de renda,
    mas reduz bastante o peso visual do gradiente.
    """
    base = plt.get_cmap(cmap_name)

    colors = base(
        np.linspace(
            start,
            end,
            256,
        )
    )

    colors[:, :3] = (
        colors[:, :3] * (1.0 - white_mix)
        + white_mix
    )

    return LinearSegmentedColormap.from_list(
        f"{cmap_name}_soft",
        colors,
    )


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
    title: str = "Renda média por setor censitário",
    cmap: str = "YlOrRd",
    boundary: gpd.GeoDataFrame | None = None,
    dpi: int = 300,
) -> Path:
    """
    Gera mapa coroplético contínuo com gradiente de renda.

    Parameters
    ----------
    regions
        Regiões a serem coloridas. No piloto, setores censitários.
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
    plot_cmap = _soft_colormap(cmap)

    gdf.plot(
        ax=axes,
        column=value_column,
        cmap=plot_cmap,
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
    title: str = "Rede viária",
    dpi: int = 300,
) -> Path:
    """
    Gera um mapa uniforme da rede viária municipal.

    O parâmetro neighborhood_graph é mantido apenas por compatibilidade
    com chamadas antigas, mas não é desenhado. Assim nenhum bairro ou
    conjunto de ruas recebe destaque no mapa final.
    """
    _, city_edges = ox.graph_to_gdfs(city_graph)

    figure, axes = plt.subplots(figsize=(12, 12))

    if boundary is not None and not boundary.empty:
        boundary.plot(
            ax=axes,
            facecolor="white",
            edgecolor="0.15",
            linewidth=0.8,
        )

    city_edges.plot(
        ax=axes,
        linewidth=0.35,
        color="0.35",
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
    Gera mapa em que cada bairro recebe uma cor e os setores
    censitários aparecem com contorno mais espesso.

    As geometrias são dissolvidas por código antes da plotagem para
    evitar sobreposição visual de registros duplicados.
    """
    bairros = neighborhoods.copy()
    setores = sectors.copy()

    if bairros.crs != setores.crs:
        setores = setores.to_crs(bairros.crs)

    if "CD_BAIRRO" in bairros.columns:
        bairros = bairros.dissolve(
            by="CD_BAIRRO",
            as_index=False,
        )

    if "CD_SETOR" in setores.columns:
        setores = setores.dissolve(
            by="CD_SETOR",
            as_index=False,
        )

    bairros = bairros.reset_index(drop=True)
    bairros["_BAIRRO_PLOT_ID"] = range(len(bairros))

    # Colormap categórico com uma posição para cada bairro.
    cmap_bairros = plt.get_cmap(
        "turbo",
        max(len(bairros), 2),
    )

    figure, axes = plt.subplots(figsize=(12, 12))

    bairros.plot(
        ax=axes,
        column="_BAIRRO_PLOT_ID",
        cmap=cmap_bairros,
        legend=False,
        edgecolor="white",
        linewidth=0.7,
    )

    # Setores desenhados por cima para permanecerem legíveis sobre
    # qualquer cor de bairro.
    setores.boundary.plot(
        ax=axes,
        linewidth=0.65,
        color="0.15",
    )

    legend_handles = [
        Line2D(
            [0],
            [0],
            linewidth=6,
            color="0.55",
            label="Bairros (cores distintas)",
        ),
        Line2D(
            [0],
            [0],
            linewidth=0.65,
            color="0.15",
            label="Setores censitários",
        ),
    ]

    axes.legend(
        handles=legend_handles,
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
# PRÉ-VISUALIZAÇÃO — RENDA + NOMES DOS BAIRROS
# ============================================================

def preview_income_map_with_labels(
    neighborhoods: gpd.GeoDataFrame,
    value_column: str = "RENDA_MED_BAIRRO",
    name_column: str = "NM_BAIRRO",
    title: str = "Renda média por bairro",
    cmap: str = "YlOrRd",
    boundary: gpd.GeoDataFrame | None = None,
    figsize: tuple[int, int] = (16, 16),
    label_fontsize: float = 5.5,
):
    """
    Monta um mapa exploratório de renda com o nome de todos os bairros.

    Esta função NÃO salva arquivo e NÃO fecha a figura. Ela foi pensada
    para uso em notebook, permitindo visualizar o resultado antes de
    decidir o estilo final dos mapas exportados.

    Returns
    -------
    tuple
        (figure, axes)
    """
    required = [value_column, name_column, "geometry"]
    missing = [
        column
        for column in required
        if column not in neighborhoods.columns
    ]

    if missing:
        raise KeyError(
            f"Colunas ausentes para a pré-visualização: {missing}. "
            f"Disponíveis: {list(neighborhoods.columns)}"
        )

    bairros = neighborhoods.copy()

    if "CD_BAIRRO" in bairros.columns:
        # Evita rótulos e bordas duplicados.
        aggregation = {
            value_column: "first",
            name_column: "first",
        }
        bairros = bairros.dissolve(
            by="CD_BAIRRO",
            aggfunc=aggregation,
            as_index=False,
        )

    bairros[value_column] = bairros[value_column].astype("float64")

    figure, axes = plt.subplots(figsize=figsize)

    bairros.plot(
        ax=axes,
        column=value_column,
        cmap=cmap,
        legend=True,
        linewidth=0.45,
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
            linewidth=0.9,
            color="0.15",
        )

    # representative_point() mantém o rótulo dentro do polígono,
    # inclusive para bairros com geometrias côncavas.
    pontos_rotulo = bairros.geometry.representative_point()

    for (_, row), point in zip(
        bairros.iterrows(),
        pontos_rotulo,
    ):
        nome = str(row[name_column]).strip()

        texto = axes.annotate(
            nome,
            xy=(point.x, point.y),
            ha="center",
            va="center",
            fontsize=label_fontsize,
            color="black",
        )

        # Halo branco melhora a leitura sem criar caixas sobre o mapa.
        texto.set_path_effects([
            path_effects.Stroke(
                linewidth=1.5,
                foreground="white",
            ),
            path_effects.Normal(),
        ])

    axes.set_title(
        title,
        fontsize=15,
        pad=12,
    )
    axes.set_axis_off()
    axes.set_aspect("equal")
    figure.tight_layout()

    return figure, axes


# ============================================================
# PRÉ-VISUALIZAÇÃO — RENDA SETORIAL + NOMES DOS BAIRROS
# ============================================================

def preview_sector_income_with_neighborhood_labels(
    sectors: gpd.GeoDataFrame,
    neighborhoods: gpd.GeoDataFrame,
    value_column: str = "RENDA_MED_SETOR",
    name_column: str = "NM_BAIRRO",
    title: str = "Renda média por setor censitário",
    cmap: str = "YlOrRd",
    boundary: gpd.GeoDataFrame | None = None,
    figsize: tuple[int, int] = (16, 16),
    label_fontsize: float = 5.5,
):
    """
    Pré-visualiza a renda por setor censitário e escreve os nomes dos
    bairros por cima.

    A função não salva arquivo nem fecha a figura. Foi criada para uso
    exploratório em notebook.
    """
    if value_column not in sectors.columns:
        raise KeyError(
            f"A coluna '{value_column}' não existe nos setores. "
            f"Colunas disponíveis: {list(sectors.columns)}"
        )

    if name_column not in neighborhoods.columns:
        raise KeyError(
            f"A coluna '{name_column}' não existe nos bairros. "
            f"Colunas disponíveis: {list(neighborhoods.columns)}"
        )

    setores = sectors.copy()
    bairros = neighborhoods.copy()

    if bairros.crs != setores.crs:
        bairros = bairros.to_crs(setores.crs)

    setores[value_column] = setores[value_column].astype("float64")

    if "CD_BAIRRO" in bairros.columns:
        bairros = bairros.dissolve(
            by="CD_BAIRRO",
            aggfunc={name_column: "first"},
            as_index=False,
        )

    figure, axes = plt.subplots(figsize=figsize)
    plot_cmap = _soft_colormap(cmap)

    setores.plot(
        ax=axes,
        column=value_column,
        cmap=plot_cmap,
        legend=True,
        linewidth=0.20,
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

    bairros.boundary.plot(
        ax=axes,
        linewidth=0.75,
        color="0.15",
    )

    if boundary is not None and not boundary.empty:
        limite = boundary

        if limite.crs != setores.crs:
            limite = limite.to_crs(setores.crs)

        limite.boundary.plot(
            ax=axes,
            linewidth=1.1,
            color="black",
        )

    pontos_rotulo = bairros.geometry.representative_point()

    for (_, row), point in zip(
        bairros.iterrows(),
        pontos_rotulo,
    ):
        nome = str(row[name_column]).strip()

        texto = axes.annotate(
            nome,
            xy=(point.x, point.y),
            ha="center",
            va="center",
            fontsize=label_fontsize,
            color="black",
        )

        texto.set_path_effects([
            path_effects.Stroke(
                linewidth=1.5,
                foreground="white",
            ),
            path_effects.Normal(),
        ])

    axes.set_title(
        title,
        fontsize=15,
        pad=12,
    )
    axes.set_axis_off()
    axes.set_aspect("equal")
    figure.tight_layout()

    return figure, axes


# ============================================================
# ORQUESTRADOR
# ============================================================

def generate_pilot_maps(
    income_regions: gpd.GeoDataFrame,
    neighborhoods: gpd.GeoDataFrame,
    sectors: gpd.GeoDataFrame,
    city_graph,
    output_dir: str | Path,
    income_column: str = "RENDA_MED_SETOR",
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
        title="Distribuição da renda média por setor censitário",
        boundary=boundary,
    )

    network_map = plot_networks_map(
        city_graph=city_graph,
        boundary=boundary,
        output_path=output_dir / "mapa_redes.png",
        title="Rede viária de Porto Alegre",
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
