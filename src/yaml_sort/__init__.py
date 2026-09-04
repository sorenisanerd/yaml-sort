"""yaml-sort — deterministic YAML key ordering.

Public API: :func:`yaml_sort.core.sort_text`.
"""

from .core import parse_document, sort_text

__all__ = ["parse_document", "sort_text"]
__version__ = "0.2.0"
