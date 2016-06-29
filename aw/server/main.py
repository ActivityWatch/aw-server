import logging

from .server import _start
from aw.datastore import Datastore, get_storage_methods, get_storage_method_names


def main():
    """Called from the executable and __main__.py"""
    import argparse

    storage_methods = get_storage_methods()
    storage_method_names = get_storage_method_names()

    parser = argparse.ArgumentParser(description='Starts an ActivityWatch server')
    parser.add_argument('--testing', action='store_true',
                        help='Run aw-server in testing mode using different ports and database')
    # TODO: Implement datastore.FILES storage method and use it so that there is a storage method
    #       with persistence that does not have any dependencies on external software (such as MongoDB)
    parser.add_argument('--storage', dest='storage',
                        choices=storage_method_names,
                        default=storage_method_names[0],
                        help='The method to use for storing data. Some methods (such as MongoDB) require specific Python packages to be available (in the MongoDB case: pymongo)')
    args = parser.parse_args()

    logger = logging.getLogger("main")
    logging.basicConfig(level=logging.DEBUG if args.testing else logging.INFO)

    logging.info("Using storage method: {}".format(args.storage))
    storage_method = storage_methods[storage_method_names.index(args.storage)]

    if args.testing:
        # TODO: Set logging level for root logger properly
        logger.info("Will run in testing mode")
        logger.debug("Using args: {}".format(args))
        testing = True
        port = 5666
    else:
        testing = False
        port = 5600

    logger.info("Staring up...")
    _start(port=port, testing=testing, storage_method=storage_method)
