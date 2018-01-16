import werkzeug.exceptions


class BadRequest(werkzeug.exceptions.BadRequest):
    def __init__(self, type: str, message: str) -> None:
        super().__init__(message)
        self.type = type

class NotFound(werkzeug.exceptions.NotFound):
    def __init__(self, type: str, message: str) -> None:
        super().__init__(message)
        self.type = type

class Unauthorized(werkzeug.exceptions.Unauthorized):
    def __init__(self, type: str, message: str) -> None:
        super().__init__(message)
        self.type = type
