"""Funções reutilizáveis de download usadas pelo EtPilot."""

from .downloadDataCNEFE import (
    download_cnefe,
    ler_renda_bairros,
)
from .downloadNetwork import (
    download_neighborhood_network,
    download_network,
)

__all__ = [
    "download_cnefe",
    "ler_renda_bairros",
    "download_network",
    "download_neighborhood_network",
]
