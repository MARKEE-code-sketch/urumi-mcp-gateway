class PlatformError(Exception):
    def __init__(self, status, code, message, principal=None):
        super().__init__(code)
        self.status, self.code, self.message = status, code, message
        self.principal = principal


def invalid():
    return PlatformError(422, "INVALID_INPUT", "The supplied input is invalid.")


def unavailable():
    return PlatformError(503, "DEPENDENCY_UNAVAILABLE", "A required dependency is unavailable.")


def conflict():
    return PlatformError(409, "CONFLICT", "The operation conflicts with current state.")


def missing():
    return PlatformError(404, "NOT_FOUND", "The resource was not found.")
