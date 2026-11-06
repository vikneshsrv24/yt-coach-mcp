"""Typed errors. Messages are written for Claude/the user to read directly."""


class CoachError(Exception):
    """Base class; str(e) is safe to show to the user."""


class ConfigError(CoachError):
    pass


class ChannelNotFound(CoachError):
    pass


class QuotaExceeded(CoachError):
    pass


class ApiError(CoachError):
    pass


class TranscriptUnavailable(CoachError):
    pass
