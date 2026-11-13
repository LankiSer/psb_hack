"""Запуск сабмита прямо из клонированного репозитория."""
import runpy
import sys
from pathlib import Path

if __name__ == "__main__":
    backend = Path(__file__).resolve().parent / "backend"
    sys.path.insert(0, str(backend))
    runpy.run_path(str(backend / "solution.py"), run_name="__main__")
