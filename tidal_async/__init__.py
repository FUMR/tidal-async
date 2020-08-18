__version__ = '0.1.0'

from .api import AudioMode, AudioQuality, Cover, Track, Album
from .session import TidalMultiSession, TidalSession


async def cli_auth_url_getter(authorization_url):
    # raise NotImplemented
    # Test (bad) implementation, it's blocking and should be overwritten in code using this API
    print("Authorization prompt URL:", authorization_url)
    print("Paste this URL to your browser, login to Tidal when asked,\n"
          "copy URL from your browser after successful authentication (it will show Not found error)\n"
          "Paste it in prompt below")

    return input("Enter auth_url: ")


__all__ = ['AudioMode', 'AudioQuality', 'Cover', 'Track', 'Album', 'TidalSession', 'TidalMultiSession', 'cli_auth_url_getter']

try:
    from androguard.core.bytecodes.axml import ARSCParser

    from zipfile import ZipFile

    def extract_client_id(apk_file):
        with ZipFile(apk_file) as apk:
            with apk.open("resources.arsc") as res:
                return ARSCParser(res.read()).get_string("com.aspiro.tidal", "default_client_id")[1]

    __all__.append('extract_client_id')

except ImportError:
    pass
