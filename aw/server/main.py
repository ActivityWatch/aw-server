import logging
import sys

from . import start


def main():
    """Called from __main__.py"""
    logger = logging.getLogger("main")

    testing = "--testing" in sys.argv

    if testing:
        logger.info("Starting up in testing mode")
        debug = True
        port = 5666
    else:
        debug = False
        port = 5600

    start(debug=debug, port=port, testing=testing)

