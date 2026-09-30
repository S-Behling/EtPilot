"""Remove todos os arquivos gerados dentro de outputs/.

Uso:
    python scripts/clear_outputs.py

A estrutura de pastas é preservada; somente arquivos e links simbólicos são
removidos.
"""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUTS_DIR = PROJECT_ROOT / "outputs"


def clear_output_files(output_dir: Path = OUTPUTS_DIR) -> int:
    """Remove recursivamente todos os arquivos de output_dir."""

    output_dir = output_dir.resolve()
    project_root = PROJECT_ROOT.resolve()

    if project_root not in output_dir.parents:
        raise ValueError(
            "Por segurança, o diretório de saída deve estar dentro do projeto."
        )

    if not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)
        return 0

    removed = 0

    for path in output_dir.rglob("*"):
        if path.is_file() or path.is_symlink():
            path.unlink()
            removed += 1

    return removed


def main() -> None:
    removed = clear_output_files()
    print(
        f"Limpeza concluída: {removed} arquivo(s) removido(s) de "
        f"{OUTPUTS_DIR}."
    )


if __name__ == "__main__":
    main()
