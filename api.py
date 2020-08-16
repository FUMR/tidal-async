import base64
import enum
import hashlib
import json
import os
import urllib.parse
from zipfile import ZipFile

import aiohttp
from androguard.core.bytecodes.axml import ARSCParser


# TODO: playlists
# TODO: artists


class AlreadyLoggedIn(Exception):
    pass


class AuthorizationNeeded(Exception):
    pass


class AuthorizationError(Exception):
    pass


def extract_client_id(apk_file):
    with ZipFile(apk_file) as apk:
        with apk.open("resources.arsc") as res:
            return ARSCParser(res.read()).get_string("com.aspiro.tidal", "default_client_id")[1]


class AudioQuality(enum.Enum):
    Normal = "LOW"
    High = "HIGH"
    HiFi = "LOSSLESS"
    Master = "HI_RES"


class AudioMode(enum.Enum):
    # TODO: find more modes
    Stereo = "STEREO"


class Cover(object):
    def __init__(self, id_):
        self.id = id_

    @property
    def url(self, size=(320, 320)):
        # Valid resolutions: 80x80, 160x160, 320x320, 640x640, 1280x1280
        return f"https://resources.tidal.com/images/{self.id.replace('-', '/')}/{size[0]}x{size[1]}.jpg"


class TidalObject(object):
    def __init__(self, tidal_session, dict_):
        self.session = tidal_session
        self.dict = dict_

    async def reload_info(self):
        raise NotImplemented

    @classmethod
    async def from_id(cls, tidal_session, id_: int):
        obj = cls(tidal_session, {'id': id_})
        await obj.reload_info()
        return obj

    @property
    def id(self):
        return self.dict['id']

    def __getattr__(self, attr):
        # snake_case to camelCase for making access moar pythonic
        return self.dict.get("".join([c if i == 0 else c.capitalize() for i, c in enumerate(attr.split('_'))]))


class Album(TidalObject):
    async def reload_info(self):
        resp = await self.session.get(f"/v1/albums/{self.id}/tracks", params={
            "countryCode": self.session.country_code
        })
        resp.raise_for_status()
        self.dict = await resp.json()

    @classmethod
    async def from_url(cls, tidal_session, url):
        # TODO
        raise NotImplemented

    @property
    def cover(self):
        return Cover(self.dict['cover'])

    async def tracks(self):
        if 'items' not in self.dict:
            await self.reload_info()
        return [Track(self.session, track) for track in self.dict['items']]


class Track(TidalObject):
    async def reload_info(self):
        resp = await self.session.get(f"/v1/tracks/{self.id}", params={
            "countryCode": self.session.country_code
        })
        resp.raise_for_status()
        self.dict = await resp.json()

    @classmethod
    async def from_url(cls, tidal_session, url):
        # TODO
        raise NotImplemented

    @property
    def album(self):
        return Album(self.session, self.dict['album'])

    @property
    def cover(self):
        return self.album.cover

    @property
    def audio_quality(self):
        return AudioQuality(self.dict['audioQuality'])

    async def _playbackinfopostpaywall(self, audio_quality=AudioQuality.Master):
        # TODO: audioMode
        resp = await self.session.get(f"/v1/tracks/{self.id}/playbackinfopostpaywall", params={
            "playbackmode": "STREAM", "assetpresentation": "FULL",
            "audioquality": audio_quality.value
        })
        resp.raise_for_status()

        return await resp.json()

    async def _stream_manifest(self, audio_quality=AudioQuality.Master):
        data = await self._playbackinfopostpaywall(audio_quality)
        return json.loads(base64.b64decode(data['manifest']))
    
    async def stream_url(self, audio_quality=AudioQuality.Master):
        return (await self._stream_manifest(audio_quality))['urls'][0]

    # TODO: filelike


async def cli_auth_url_getter(authorization_url):
    # raise NotImplemented
    # Test (bad) implementation, it's blocking and should be overwritten in code using this API
    print("Authorization prompt URL:", authorization_url)
    print("Paste this URL to your browser, login to Tidal when asked,\n"
          "copy URL from your browser after successful authentication (it will show Not found error)\n"
          "Paste it in prompt below")

    return input("Enter auth_url: ")


class TidalSession(object):
    _redirect_uri = "https://tidal.com/android/login/auth"  # or tidal://login/auth
    _api_base_url = "https://api.tidal.com/"
    _oauth_authorize_url = "https://login.tidal.com/authorize"
    _oauth_token_url = "https://auth.tidal.com/v1/oauth2/token"

    def __init__(self, client_id, interactive_auth_url_getter):
        self.client_id = client_id
        self.sess = aiohttp.ClientSession()
        self._interactive_auth_getter = interactive_auth_url_getter

        self._auth_info = None

    @property
    def _access_token(self):
        if self._auth_info is None:
            raise AuthorizationNeeded
        return self._auth_info['access_token']

    @property
    def _refresh_token(self):
        if self._auth_info is None:
            raise AuthorizationNeeded
        return self._auth_info['refresh_token']

    @property
    def _token_type(self):
        if self._auth_info is None:
            raise AuthorizationNeeded
        return self._auth_info['token_type']

    @property
    def country_code(self):
        if self._auth_info is None:
            raise AuthorizationNeeded
        return self._auth_info['user']['countryCode']

    async def login(self):
        if self._auth_info is not None:
            # TODO: refresh session
            raise AlreadyLoggedIn

        # https://tools.ietf.org/html/rfc7636#appendix-B
        code_verifier = base64.urlsafe_b64encode(os.urandom(32))[:-1]
        code_challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier).digest())[:-1]

        qs = urllib.parse.urlencode({
            "response_type": "code",
            "redirect_uri": self._redirect_uri,
            "client_id": self.client_id,
            "appMode": "android",
            "code_challenge": code_challenge.decode('ascii'),
            "code_challenge_method": "S256",
            "restrict_signup": "true"
        })

        authorization_url = urllib.parse.urljoin(self._oauth_authorize_url, "?" + qs)

        auth_url = await self._interactive_auth_getter(authorization_url)

        code = urllib.parse.parse_qs(urllib.parse.urlsplit(auth_url).query)['code'][0]

        async with self.sess.post(self._oauth_token_url, data={
            "code": code,
            "client_id": self.client_id,
            "grant_type": "authorization_code",
            "redirect_uri": self._redirect_uri,
            "scope": "r_usr w_usr w_sub",
            "code_verifier": code_verifier.decode('ascii'),
        }) as resp:
            data = await resp.json()
            if resp.status != 200:
                raise AuthorizationError(data['error'], data['error_description'])
            self._auth_info = data

    async def request(self, method, url, auth=True, headers=None, **kwargs):
        url = urllib.parse.urljoin(self._api_base_url, url)
        if auth:
            if headers is None:
                headers = {}
            headers.update({
                "X-Tidal-Token": self.client_id,
                "Authorization": f"{self._token_type} {self._access_token}"
            })

        return await self.sess.request(method, url, headers=headers, **kwargs)

    async def get(self, url, **kwargs):
        return await self.request("GET", url, **kwargs)

    async def post(self, url, **kwargs):
        return await self.request("POST", url, **kwargs)

    async def logout(self):
        # TODO
        raise NotImplemented

    async def refresh_session(self):
        # TODO
        raise NotImplemented

    async def close(self):
        await self.sess.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def track(self, track_id):
        return await Track.from_id(self, track_id)

    async def album(self, album_id):
        return await Album.from_id(self, album_id)


class UnknownSession(Exception):
    pass


class TidalMultiSession(TidalSession):
    # It helps with downloading multiple tracks simultaneously and overriding region lock
    # TODO: run request on random session
    # TODO: retry failed (404) requests (regionlock) on next session
    # TODO: try file download request on all sessions in queue fullness order
    #  (tidal blocks downloading of files simultaneously)
    def __init__(self, client_id, interactive_auth_url_getter):
        self.sessions = []
        self.client_id = client_id
        self._interactive_auth_getter = interactive_auth_url_getter

    async def add_session(self):
        sess = TidalSession(self.client_id, self._interactive_auth_getter)
        await sess.login()
        self.sessions.append(sess)

    async def login(self):
        raise NotImplemented

    async def logout(self, sess_num=None):
        if sess_num is None:
            for s in self.sessions:
                s.logout()
        else:
            if sess_num < len(self.sessions):
                self.sessions[sess_num].logout()
                del self.sessions[sess_num]

    async def close(self):
        for s in self.sessions:
            await s.close()
