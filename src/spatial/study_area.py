"""Modelo de domínio para o recorte espacial de uma execução."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shapely.geometry.base import BaseGeometry


@dataclass(frozen=True, slots=True)
class StudyArea:
    """Área espacial efetivamente utilizada em uma execução do EtPilot."""

    name: str
    label: str
    geometry: BaseGeometry
    crs: Any
    source_neighborhoods: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("StudyArea.name não pode ser vazio.")

        if self.geometry is None or self.geometry.is_empty:
            raise ValueError("StudyArea.geometry não pode ser vazia.")

        if self.crs is None:
            raise ValueError("StudyArea.crs precisa estar definido.")
