import logging

from .server import _start
from .log import setup_logging
from aw_datastore import Datastore, get_storage_methods, get_storage_method_names



def main():
    """Called from the executable and __main__.py"""

    args, storage_method = parse_args()

    setup_logging(args)

    logger = logging.getLogger("main")
    logger.info("Using storage method: {}".format(args.storage))

    if args.testing:
        # TODO: Set logging level for root logger properly
        logger.info("Will run in testing mode")
        logger.debug("Using args: {}".format(args))
        testing = True
        port = 5666
    else:
        testing = False
        port = 5600

    logger.info("Starting up...")
    _start(port=port, testing=testing, storage_method=storage_method)


def parse_args():
    import argparse

    storage_methods = get_storage_methods()
    storage_method_names = get_storage_method_names()

    parser = argparse.ArgumentParser(description='Starts an ActivityWatch server')
    parser.add_argument('--testing', action='store_true',
                        help='Run aw-server in testing mode using different ports and database')
    parser.add_argument('--log-json', action='store_true',
                        help='Output the logs in JSON format')
    # TODO: Implement datastore.FILES storage method and use it so that there is a storage method
    #       with persistence that does not have any dependencies on external software (such as MongoDB)
    parser.add_argument('--storage', dest='storage',
                        choices=storage_method_names,
                        default=storage_method_names[0],
                        help='The method to use for storing data. Some methods (such as MongoDB) require specific Python packages to be available (in the MongoDB case: pymongo)')


    args = parser.parse_args()
    storage_method = storage_methods[storage_method_names.index(args.storage)]
    return args, storage_method
