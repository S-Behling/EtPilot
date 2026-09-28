import unittest

import numpy as np

from src.domain.agent import Agent
from src.domain.enums import IncomeGroup, TravelMode
from src.simulation.mode_choice import (
    calculate_mode_probabilities,
    choose_mode,
)


class ModeChoiceTests(unittest.TestCase):
    def _agent(self, distance_m):
        # Cria um agente com distância OD disponível antes do roteamento
        agent = Agent(
            agent_id=1,
            income_group=IncomeGroup.LOW,
        )
        agent.od_distance_m = distance_m
        return agent

    def _base_config(self):
        return {
            "low": {
                "walk": 0.25,
                "bike": 0.10,
                "transit": 0.55,
                "car": 0.10,
            }
        }

    def _distance_config(self):
        return {
            "enabled": True,
            "decay_per_km": {
                "walk": 0.55,
                "bike": 0.12,
                "transit": 0.03,
                "car": 0.0,
            },
            "max_distance_km": {
                "walk": 6.0,
                "bike": 20.0,
                "transit": None,
                "car": None,
            },
        }

    def _probability_map(self, distance_m):
        agent = self._agent(
            distance_m
        )

        modes, probabilities = (
            calculate_mode_probabilities(
                agent=agent,
                config=self._base_config(),
                available_modes={
                    TravelMode.WALK,
                    TravelMode.BIKE,
                    TravelMode.CAR,
                },
                distance_config=self._distance_config(),
            )
        )

        return {
            mode.value: probability
            for mode, probability
            in zip(
                modes,
                probabilities,
                strict=True,
            )
        }

    def test_distance_reduces_walk_probability(self):
        # Compara a mesma regra modal em uma viagem curta e outra longa
        short = self._probability_map(
            1000.0
        )
        long = self._probability_map(
            5000.0
        )

        self.assertGreater(
            short["walk"],
            long["walk"],
        )

    def test_walk_becomes_unavailable_above_maximum(self):
        # Zera o peso de caminhada acima do limite provisório do piloto
        probabilities = self._probability_map(
            7000.0
        )

        self.assertEqual(
            probabilities["walk"],
            0.0,
        )

    def test_car_gains_relative_share_with_distance(self):
        # Mantém o carro sem penalização e aumenta sua participação relativa
        short = self._probability_map(
            1000.0
        )
        long = self._probability_map(
            5000.0
        )

        self.assertGreater(
            long["car"],
            short["car"],
        )

    def test_disabled_adjustment_preserves_filtered_base_probabilities(self):
        # Reproduz a normalização original quando o ajuste está desativado
        agent = self._agent(
            5000.0
        )

        modes, probabilities = (
            calculate_mode_probabilities(
                agent=agent,
                config=self._base_config(),
                available_modes={
                    TravelMode.WALK,
                    TravelMode.BIKE,
                    TravelMode.CAR,
                },
                distance_config={
                    "enabled": False,
                },
            )
        )

        result = {
            mode.value: probability
            for mode, probability
            in zip(
                modes,
                probabilities,
                strict=True,
            )
        }

        expected_total = (
            0.25
            + 0.10
            + 0.10
        )

        self.assertAlmostEqual(
            result["walk"],
            0.25 / expected_total,
        )
        self.assertAlmostEqual(
            result["bike"],
            0.10 / expected_total,
        )
        self.assertAlmostEqual(
            result["car"],
            0.10 / expected_total,
        )

    def test_choose_mode_uses_adjusted_probabilities(self):
        # Sorteia somente modos que permanecem disponíveis após o ajuste
        agent = self._agent(
            7000.0
        )
        rng = np.random.default_rng(
            42
        )

        selections = {
            choose_mode(
                agent=agent,
                config=self._base_config(),
                rng=rng,
                available_modes={
                    TravelMode.WALK,
                    TravelMode.BIKE,
                    TravelMode.CAR,
                },
                distance_config=self._distance_config(),
            )
            for _ in range(
                100
            )
        }

        self.assertNotIn(
            TravelMode.WALK,
            selections,
        )

    def test_transit_probability_is_preserved_when_transit_is_available(self):
        # Mantém transit no conjunto de escolha em vez de redistribuir sua massa aos modos OSM
        agent = self._agent(
            5000.0
        )

        modes, probabilities = (
            calculate_mode_probabilities(
                agent=agent,
                config=self._base_config(),
                available_modes={
                    TravelMode.WALK,
                    TravelMode.BIKE,
                    TravelMode.CAR,
                    TravelMode.TRANSIT,
                },
                distance_config={
                    "enabled": False,
                },
            )
        )

        result = {
            mode.value: probability
            for mode, probability
            in zip(
                modes,
                probabilities,
                strict=True,
            )
        }

        self.assertAlmostEqual(
            result[
                "transit"
            ],
            0.55,
        )
        self.assertAlmostEqual(
            sum(
                result.values()
            ),
            1.0,
        )


if __name__ == "__main__":
    unittest.main()
