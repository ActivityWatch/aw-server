import os
import sys
import logging
from datetime import datetime

import appdirs
from pythonjsonlogger import jsonlogger

from werkzeug import serving
from werkzeug._internal import _log


log_file_path = None


def get_log_file_path():
    return log_file_path


def setup_logging(args):
    conf_flask_logging()

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if args.testing else logging.INFO)

    root_logger.addHandler(create_stderr_handler(args))
    root_logger.addHandler(create_file_handler(args))


def conf_flask_logging():
    # Fix this
    # app.logger.setFormatter(logging.Formatter("%(message)s"))
    pass


def create_stderr_handler(args):
    stderr_handler = logging.StreamHandler(stream=sys.stderr)

    if args.log_json:
        stderr_handler.setFormatter(create_json_formatter())
    else:
        stderr_handler.setFormatter(create_human_formatter())

    return stderr_handler


def create_file_handler(args):
    # Get and create log path
    user_data_dir = appdirs.user_data_dir("aw-server", "activitywatch")
    log_dir = os.path.join(user_data_dir, "testing" if args.testing else "", "logs")
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # Set logfile path and name
    global log_file_path
    log_file_path = os.path.join(log_dir, str(datetime.now().isoformat()) + ".log")

    # File logger
    fh = logging.FileHandler(log_file_path, mode='w')
    fh.setFormatter(create_json_formatter())

    return fh


def create_human_formatter():
    return logging.Formatter('%(asctime)-15s [%(levelname)-5s]: %(message)s (%(filename)s:%(lineno)s)')


def create_json_formatter():
    supported_keys = [
        'asctime',
        # 'created',
        'filename',
        'funcName',
        'levelname',
        # 'levelno',
        'lineno',
        'module',
        # 'msecs',
        'message',
        'name',
        'pathname',
        # 'process',
        # 'processName',
        # 'relativeCreated',
        # 'thread',
        # 'threadName'
    ]

    def log_format(x):
        """Used to give JsonFormatter proper parameter format"""
        return ['%({0:s})'.format(i) for i in x]

    custom_format = ' '.join(log_format(supported_keys))

    return jsonlogger.JsonFormatter(custom_format)

class FlaskLogHandler(serving.WSGIRequestHandler):
    def __init__(self, *args):
        self.logger = logging.getLogger("flask")
        super().__init__(*args)

    def log(self, type, message, *args):
        msg = args[0]
        code = args[1]
        if code in [200, 304]:
            type = "debug"
        _log(type, '{} - {} - {}\n'.format(code, self.address_string(), msg))
