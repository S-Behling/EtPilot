import numpy as np

# Peso das trajetorias
def destination_weights(
    distances,
    attractiveness,
    beta
):
    distances = np.asarray(distances)
    attractiveness = np.asarray(attractiveness)

    weights = attractiveness * np.exp(-beta * distances)

    if weights.sum() == 0:
        return np.ones(len(weights)) / len(weights)

    return weights / weights.sum()