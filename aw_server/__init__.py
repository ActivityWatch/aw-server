import logging as _logging

logger = _logging.getLogger(__name__)

from . import __about__
from .__about__ import __version__

from .server import create_app

from . import api
from . import rest

from .main import main
