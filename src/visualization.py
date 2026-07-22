import matplotlib.pyplot as plt

# Plota a rede de ruas com base em um GeoDataFrame de arestas (gdf_edges)
# Figure 'folha'
#    └── Axes 'area de desenho'
#            └── Plot 'desenho'

def plot_network(
    gdf_edges,
    column=None,
    figsize=(12, 12),
    legend=True,
    linewidth=1.5
):

    figure, axes = plt.subplots(figsize=figsize)

    gdf_edges.plot(
        ax=axes,
        column=column,
        legend=legend,
        linewidth=linewidth
    )

    axes.set_axis_off()

    return figure, axes