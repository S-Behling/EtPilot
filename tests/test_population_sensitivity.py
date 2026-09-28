import unittest

import pandas as pd

from src.analysis.population_sensitivity import (
    _selection_table,
    _stability_table,
    _validate_sizes,
)


class PopulationSensitivityTests(unittest.TestCase):
    def test_normalizes_population_sizes(self):
        # Remove duplicatas e mantém os tamanhos em ordem crescente
        self.assertEqual(
            _validate_sizes(
                [
                    500,
                    100,
                    250,
                    500,
                ]
            ),
            [
                100,
                250,
                500,
            ],
        )

    def test_stability_requires_ge10_support(self):
        # Evita selecionar um N sem suporte pareado no limiar de dez agentes
        summary = pd.DataFrame(
            {
                "n_agents_requested": [
                    100,
                    250,
                ],
                "H_soc_mean_supported_baseline": [
                    0.70,
                    0.71,
                ],
                "H_soc_mean_supported_differentiated": [
                    0.66,
                    0.67,
                ],
                "sufficient_delta_H_soc_mean": [
                    -0.12,
                    -0.11,
                ],
                "paired_delta_H_soc_mean": [
                    -0.03,
                    -0.02,
                ],
                "flow_ge_10_both": [
                    0,
                    20,
                ],
            }
        )

        stability = _stability_table(
            summary,
            tolerance=0.05,
            min_paired_ge10=1,
        )

        self.assertFalse(
            stability.iloc[
                0
            ][
                "stable_vs_next"
            ]
        )

    def test_selects_smallest_stable_population(self):
        # Seleciona o menor N cuja mudança para o próximo tamanho fica dentro da tolerância
        summary = pd.DataFrame(
            {
                "n_agents_requested": [
                    100,
                    250,
                    500,
                ],
                "seed": [
                    42,
                    42,
                    42,
                ],
                "H_soc_mean_supported_baseline": [
                    0.70,
                    0.72,
                    0.73,
                ],
                "H_soc_mean_supported_differentiated": [
                    0.60,
                    0.62,
                    0.63,
                ],
                "sufficient_delta_H_soc_mean": [
                    -0.10,
                    -0.10,
                    -0.09,
                ],
                "paired_delta_H_soc_mean": [
                    -0.04,
                    -0.03,
                    -0.03,
                ],
                "flow_ge_5_both": [
                    40,
                    120,
                    300,
                ],
                "flow_ge_10_both": [
                    0,
                    15,
                    80,
                ],
            }
        )

        stability = _stability_table(
            summary,
            tolerance=0.05,
            min_paired_ge10=1,
        )
        selection = _selection_table(
            summary,
            stability,
        )

        self.assertEqual(
            selection.iloc[
                0
            ][
                "candidate_operational_n"
            ],
            250,
        )
        self.assertEqual(
            selection.iloc[
                0
            ][
                "selection_status"
            ],
            "smallest_n_stable_vs_next",
        )

    def test_uses_largest_population_when_no_plateau_exists(self):
        # Mantém o maior N como referência quando a faixa testada não estabiliza
        summary = pd.DataFrame(
            {
                "n_agents_requested": [
                    100,
                    250,
                ],
                "seed": [
                    42,
                    42,
                ],
                "H_soc_mean_supported_baseline": [
                    0.40,
                    0.80,
                ],
                "H_soc_mean_supported_differentiated": [
                    0.30,
                    0.70,
                ],
                "sufficient_delta_H_soc_mean": [
                    -0.10,
                    -0.40,
                ],
                "paired_delta_H_soc_mean": [
                    -0.02,
                    -0.20,
                ],
                "flow_ge_5_both": [
                    20,
                    100,
                ],
                "flow_ge_10_both": [
                    5,
                    30,
                ],
            }
        )

        stability = _stability_table(
            summary,
            tolerance=0.05,
            min_paired_ge10=1,
        )
        selection = _selection_table(
            summary,
            stability,
        )

        self.assertEqual(
            selection.iloc[
                0
            ][
                "candidate_operational_n"
            ],
            250,
        )
        self.assertEqual(
            selection.iloc[
                0
            ][
                "selection_status"
            ],
            "no_plateau_within_tested_range",
        )


if __name__ == "__main__":
    unittest.main()
