import asyncio
from urllib.parse import urlparse

from music_service_async_interface import InvalidURL


def snake_to_camel(attr):
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


async def cli_auth_url_getter(authorization_url):
    # raise NotImplemented
    # Test (bad) implementation, it's blocking and should be overwritten in code using this API
    print("Authorization prompt URL:", authorization_url)
    print(
        "Paste this URL to your browser, login to Tidal when asked,\n"
        "copy URL from your browser after successful authentication (it will show Not found error)\n"
        "Paste it in prompt below"
    )

    return input("Enter auth_url: ")


class Cacheable:
    # NOTE: Used snipped from https://stackoverflow.com/a/46723144
    def __init__(self, co):
        self.co = co
        self.done = False
        self.result = None
        self.lock = asyncio.Lock()

    def __await__(self):
        with (yield from self.lock):
            if self.done:
                return self.result
            self.result = yield from self.co.__await__()
            self.done = True
            return self.result


def cacheable(f):
    # NOTE: Used snipped from https://stackoverflow.com/a/46723144
    def wrapped(*args, **kwargs):
        r = f(*args, **kwargs)
        return Cacheable(r)

    return wrapped


def gen_title(track, artists=()):
    """Generates full title from track/album version and artist list"""
    if len(artists) > 1:
        title = track.title.strip()  # just in case

        # add featuring artists if not already
        if "(feat." not in title:
            title += f' (feat. {", ".join([a[0].name for a in artists if a[1] != "MAIN"])})'

        return f'{title}{f" [{track.version}]" if track.version and track.version not in track.title else ""}'
    else:
        return f'{track.title}{f" ({track.version})" if track.version and track.version not in track.title else ""}'


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
