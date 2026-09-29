"""Funções de download usadas pelo EtPilot."""

from .downloadNetwork import (
    download_network,
    download_neighborhood_network,
)

__all__ = [
    "download_network",
    "download_neighborhood_network",
]
