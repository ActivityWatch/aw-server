import logging

from pythonjsonlogger import jsonlogger

from .server import _start
from aw_datastore import Datastore, get_storage_methods, get_storage_method_names



def main():
    """Called from the executable and __main__.py"""

    args, storage_method = parse_args()

    setup_logging(args)

    logger = logging.getLogger("main")
    logger.info("Using storage method: {}".format(args.storage))

    if args.testing:
        logger.info("Will run in testing mode")
        logger.debug("Using args: {}".format(args))

    logger.info("Starting up...")
    _start(port=args.port, testing=args.testing, storage_method=storage_method)


def setup_logging(args):
    logger = logging.getLogger()

    if args.log_json:
        supported_keys = [
            'asctime',
            #'created',
            'filename',
            'funcName',
            'levelname',
            #'levelno',
            'lineno',
            'module',
            #'msecs',
            'message',
            'name',
            'pathname',
            #'process',
            #'processName',
            #'relativeCreated',
            #'thread',
            #'threadName'
        ]

        log_format = lambda x: ['%({0:s})'.format(i) for i in x]
        custom_format = ' '.join(log_format(supported_keys))

        logHandler = logging.StreamHandler()
        formatter = jsonlogger.JsonFormatter(custom_format)
        logHandler.setFormatter(formatter)
        logger.addHandler(logHandler)
    else:
        logging.basicConfig()

    logger.setLevel(logging.DEBUG if args.testing else logging.INFO)


def parse_args():
    import argparse

    storage_methods = get_storage_methods()
    storage_method_names = get_storage_method_names()

    parser = argparse.ArgumentParser(description='Starts an ActivityWatch server')
    parser.add_argument('--testing',
                        action='store_true',
                        help='Run aw-server in testing mode using different ports and database')
    parser.add_argument('--log-json',
                        action='store_true',
                        help='Output the logs in JSON format')
    parser.add_argument('--port',
                        dest='port',
                        type=int,
                        default=None,
                        help='Which port to run the server on')
    parser.add_argument('--storage', dest='storage',
                        choices=storage_method_names,
                        default=storage_method_names[0],
                        help='The method to use for storing data. Some methods (such as MongoDB) require specific Python packages to be available (in the MongoDB case: pymongo)')

    args = parser.parse_args()
    if not args.port:
        args.port = 5600 if not args.testing else 5666
    storage_method = storage_methods[storage_method_names.index(args.storage)]
    return args, storage_method
