import werkzeug.exceptions


class BadRequest(werkzeug.exceptions.BadRequest):
    def __init__(self, type: str, message: str) -> None:
        super().__init__(message)
        self.type = type
