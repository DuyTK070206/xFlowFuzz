"""Compatibility package exposing the project modules under ``xFlowFuzz``.

The repository keeps source folders at the project root for backward
compatibility (``runner``, ``graph``...). Extending ``__path__`` lets both
``from runner ...`` and ``from xFlowFuzz.runner ...`` resolve to the same code.
"""
from pathlib import Path

__path__.append(str(Path(__file__).resolve().parents[1]))
__version__ = "0.2.0"
