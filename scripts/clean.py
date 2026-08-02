"""Remove project-generated development artifacts without touching source files."""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIRECTORIES = (
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "build",
    "dist",
    "htmlcov",
)
FILES = (".coverage", "coverage.xml", "demo.jsonl", "report.html")


def main() -> None:
    for name in DIRECTORIES:
        path = ROOT / name
        if path.is_dir():
            shutil.rmtree(path)
    for name in FILES:
        path = ROOT / name
        if path.is_file():
            path.unlink()
    for cache in ROOT.rglob("__pycache__"):
        if ".venv" not in cache.parts and cache.is_dir():
            shutil.rmtree(cache)


if __name__ == "__main__":
    main()
