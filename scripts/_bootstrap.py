"""Inicialização comum para scripts executados diretamente.

Permite executar arquivos da pasta scripts com python scripts/nome.py sem
exigir instalação do projeto como pacote.
"""

from __future__ import annotations

import sys
from pathlib import Path


def add_project_root_to_path() -> Path:
    """Adiciona a raiz do repositório ao sys.path e a retorna."""

    project_root = Path(__file__).resolve().parents[1]
    project_root_text = str(project_root)

    if project_root_text not in sys.path:
        sys.path.insert(0, project_root_text)

    return project_root
