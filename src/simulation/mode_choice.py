import numpy as np

from src.domain.enums import TravelMode


def choose_mode(agent, config, rng, available_modes):
    probabilities = config[agent.income_group.value]

    modes = []
    weights = []

    for mode_name, p in probabilities.items():
        mode = TravelMode(mode_name)

        if mode in available_modes:
            modes.append(mode)
            weights.append(p)

    weights = np.asarray(weights, dtype=float)
    weights /= weights.sum()

    return rng.choice(modes, p=weights)