import logging

from werkzeug import serving


class FlaskLogHandler(serving.WSGIRequestHandler):
    def __init__(self, *args):
        self.logger = logging.getLogger("flask")
        super().__init__(*args)

    def log(self, levelname, message, *args):
        msg = args[0]
        code = int(args[1])

        if code in [200, 304]:
            levelname = "debug"
            # type = "debug"

        if levelname == "info":
            levelno = logging.INFO
        elif levelname == "debug":
            levelno = logging.DEBUG
        else:
            raise Exception("Unknown level " + type)
        self.logger.log(levelno, '{} ({}): {}'.format(code, self.address_string(), msg))
