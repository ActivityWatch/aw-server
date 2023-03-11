import logging as _logging

logger = _logging.getLogger(__name__)

from .__about__ import __version__
from .main import main

__all__ = [
    "__version__",
    "main",
]
