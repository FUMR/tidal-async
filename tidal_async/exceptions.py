
class AlreadyLoggedIn(Exception):
    pass


class AuthorizationNeeded(Exception):
    pass


class AuthorizationError(Exception):
    pass


class UnknownSession(Exception):
    pass
