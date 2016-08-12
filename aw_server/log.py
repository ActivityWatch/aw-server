import logging
import appdirs
import os
import datetime

from pythonjsonlogger import jsonlogger


log_file_path = None

def get_log_file_path():
    return log_file_path

def setup_logging(args):
    logger = logging.getLogger()

    # stdout/stderr logger
    logHandler = logging.StreamHandler()
    if args.log_json:
        logHandler.setFormatter(createJsonFormatter())
    logger.addHandler(logHandler)

    # Get and create log path
    user_data_dir = appdirs.user_data_dir("aw-server", "activitywatch")
    log_dir = user_data_dir + ("/testing" if args.testing else "") + "/logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # Set logfile path and name
    global log_file_path
    log_file_path = "{}/{}.log".format(log_dir, str(datetime.datetime.now()))
    
    # File logger 
    fh = logging.FileHandler(log_file_path, mode='w')
    fh.setFormatter(createJsonFormatter())
    logger.addHandler(fh)

    logger.setLevel(logging.DEBUG if args.testing else logging.INFO)


def createJsonFormatter():
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

    return jsonlogger.JsonFormatter(custom_format)
