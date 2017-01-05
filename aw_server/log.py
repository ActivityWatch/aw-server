import logging

from werkzeug import serving
from werkzeug._internal import _log


def config_flask_logging():
    # Fix this
    # app.logger.setFormatter(logging.Formatter("%(message)s"))
    pass


class FlaskLogHandler(serving.WSGIRequestHandler):
    def __init__(self, *args):
        self.logger = logging.getLogger("flask")
        self.logger.setLevel(logging.INFO)
        super().__init__(*args)

    def log(self, levelname, message, *args):
        msg = args[0]
        code = args[1]

        if code in [200, 304]:
            levelname = "debug"
            # type = "debug"

        if levelname == "info":
            levelno = logging.INFO
        elif levelname == "debug":
            levelno = logging.DEBUG
        else:
            raise Exception("Unknown level " + type)
        self.logger.log(levelno, '{} - {} - {}\n'.format(code, self.address_string(), msg))
