class DaikinError(Exception):
    """Base integration error."""


class ConfigurationError(DaikinError):
    pass


class AuthenticationError(DaikinError):
    pass


class ApiError(DaikinError):
    pass


class RateLimitError(ApiError):
    pass


class UnsupportedOperation(DaikinError):
    pass
