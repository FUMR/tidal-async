import asyncio
import contextlib
from urllib.parse import urlparse

from music_service_async_interface import InvalidURL


def snake_to_camel(attr: str) -> str:
    """
    :param attr: snake case string
    :return: camel case string
    """
    return "".join(c if i == 0 else c.capitalize() for i, c in enumerate(attr.split("_")))


def id_from_url(url, urlname):
    parsed_url = urlparse(url)
    name, domain = parsed_url.hostname.rsplit(".", 2)[-2:]
    path = parsed_url.path

    if name != "tidal" or domain != "com":
        raise InvalidURL

    id_prefix = f"/{urlname}/"

    if id_prefix not in path:
        raise InvalidURL

    return path.split(id_prefix, 1)[1].split("/", 1)[0]


async def cli_auth_url_getter(authorization_url: str) -> str:
    # Test (bad) implementation, it's blocking and should be overwritten in code using this API
    print("Authorization prompt URL:", authorization_url)
    print(
        "Paste this URL to your browser, login to Tidal when asked,\n"
        "copy URL from your browser after successful authentication (it will show Not found error)\n"
        "Paste it in prompt below"
    )

    return input("Enter auth_url: ")


@contextlib.contextmanager
def lock_context_manager(lock):
    yield lock.acquire().__await__()
    lock.release()


class AsyncCacheable:
    # NOTE: Used snippet from https://stackoverflow.com/a/46723144
    def __init__(self, co):
        self.co = co
        self.done = False
        self.result = None
        self.lock = asyncio.Lock()

    def __await__(self):
        with lock_context_manager(self.lock) as t:
            yield from t

            if self.done:
                return self.result
            self.result = yield from self.co.__await__()
            self.done = True

        return self.result


def cacheable(f):
    # NOTE: Used snippet from https://stackoverflow.com/a/46723144
    def wrapped(*args, **kwargs):
        r = f(*args, **kwargs)
        return AsyncCacheable(r)

    return wrapped


def gen_title(obj) -> str:
    """Generates full title from track/album version

    :param obj: object with `version` and `title` attributes
    :return: title including version
    eg. Some track (REMIX)
    """
    title = obj.title.strip()
    version = obj.version.strip() if "version" in obj and obj.version else ""

    return f"{title} ({version})" if version and version not in title else title


async def gen_artist(obj) -> str:
    """Generates artist string from track/album

    :param obj: object with `artists` function being Async Generator of `(`:class:`Artist``, `:class:`ArtistType``)`
    eg. Track or Album
    :return: string of artists with their roles
    eg.
    `Main, Artists`
    `Main, Artists feat. With, Featuring`
    """
    artists = [a async for a in obj.artists()]
    main = ", ".join(a[0].name for a in artists if a[1].value == "MAIN")
    feat = ", ".join(a[0].name for a in artists if a[1].value == "FEATURED")
    return main if not feat else f"{main} feat. {feat}"


async def artists_names(obj):
    return [a[0].name async for a in obj.artists()]


try:
    from zipfile import ZipFile

    from androguard.core.bytecodes.axml import ARSCParser

except ImportError:

    def extract_client_id(apk_file):
        raise NotImplementedError


else:

    def extract_client_id(apk_file):
        with ZipFile(apk_file) as apk:
            with apk.open("resources.arsc") as res:
                return ARSCParser(res.read()).get_string("com.aspiro.tidal", "default_client_id")[1]
