from music_service_async_interface import InsufficientAudioQuality


class AuthenticationNeeded(Exception):
    pass


class AuthenticationError(Exception):
    pass


class UnknownSession(Exception):
    pass
