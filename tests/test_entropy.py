import math
import unittest

from src.analysis.entropy import normalized_shannon_entropy


class EntropyTests(unittest.TestCase):
    def test_single_group_returns_zero(self):
        # Verifica composição totalmente concentrada em um grupo
        result = normalized_shannon_entropy(
            [10, 0, 0],
            n_categories=3,
        )

        self.assertAlmostEqual(
            result,
            0.0,
        )

    def test_equal_three_groups_returns_one(self):
        # Verifica diversidade máxima entre três grupos
        result = normalized_shannon_entropy(
            [10, 10, 10],
            n_categories=3,
        )

        self.assertAlmostEqual(
            result,
            1.0,
        )

    def test_two_equal_groups_use_three_group_maximum(self):
        # Normaliza pelo universo de três grupos, mesmo com um grupo ausente
        result = normalized_shannon_entropy(
            [5, 5, 0],
            n_categories=3,
        )

        expected = (
            math.log(2)
            / math.log(3)
        )

        self.assertAlmostEqual(
            result,
            expected,
        )

    def test_zero_total_returns_nan(self):
        # Diferencia ausência de observação de concentração social
        result = normalized_shannon_entropy(
            [0, 0, 0],
            n_categories=3,
        )

        self.assertTrue(
            math.isnan(
                result
            )
        )


if __name__ == "__main__":
    unittest.main()
