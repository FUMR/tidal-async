from music_service_async_interface import InsufficientAudioQuality


class AuthorizationNeeded(Exception):
    pass


class AuthorizationError(Exception):
    pass


class UnknownSession(Exception):
    pass
