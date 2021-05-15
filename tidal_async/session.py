import base64
import hashlib
import os
import urllib.parse
from typing import Optional

import aiohttp
import music_service_async_interface as generic

from tidal_async import Album, Artist, AudioQuality, Playlist, TidalObject, Track
from tidal_async.exceptions import AuthorizationError, AuthorizationNeeded


class TidalSession(generic.Session):
    _obj = TidalObject
    _quality = AudioQuality

    _redirect_uri = "https://tidal.com/android/login/auth"  # or tidal://login/auth
    _api_base_url = "https://api.tidal.com/"
    _oauth_authorize_url = "https://login.tidal.com/authorize"
    _oauth_token_url = "https://auth.tidal.com/v1/oauth2/token"

    def __init__(self, client_id, sess: Optional[aiohttp.ClientSession] = None):
        super().__init__(sess)
        self.client_id = client_id

        self._auth_info = None
        self._refresh_token = None

    @property
    def _access_token(self):
        if self._auth_info is None:
            raise AuthorizationNeeded
        return self._auth_info["access_token"]

    @property
    def _token_type(self):
        if self._auth_info is None:
            raise AuthorizationNeeded
        return self._auth_info["token_type"]

    @property
    def country_code(self):
        if self._auth_info is None:
            raise AuthorizationNeeded
        return self._auth_info["user"]["countryCode"]

    async def login(self, interactive_auth_url_getter, force_relogin=False):
        if self._auth_info is not None and not force_relogin:
            return

        # https://tools.ietf.org/html/rfc7636#appendix-B
        code_verifier = base64.urlsafe_b64encode(os.urandom(32))[:-1]
        code_challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier).digest())[:-1]

        qs = urllib.parse.urlencode(
            {
                "response_type": "code",
                "redirect_uri": self._redirect_uri,
                "client_id": self.client_id,
                "appMode": "android",
                "code_challenge": code_challenge.decode("ascii"),
                "code_challenge_method": "S256",
                "restrict_signup": "true",
            }
        )

        authorization_url = urllib.parse.urljoin(self._oauth_authorize_url, "?" + qs)

        auth_url = await interactive_auth_url_getter(authorization_url)

        code = urllib.parse.parse_qs(urllib.parse.urlsplit(auth_url).query)["code"][0]

        async with self.sess.post(
            self._oauth_token_url,
            data={
                "code": code,
                "client_id": self.client_id,
                "grant_type": "authorization_code",
                "redirect_uri": self._redirect_uri,
                "scope": "r_usr w_usr w_sub",
                "code_verifier": code_verifier.decode("ascii"),
            },
        ) as resp:
            data = await resp.json()
            if resp.status != 200:
                raise AuthorizationError(data["error"], data["error_description"])
            self._auth_info = data
            self._refresh_token = data["refresh_token"]

    async def request(self, method, url, auth=True, headers=None, autorefresh=True, **kwargs):
        url = urllib.parse.urljoin(self._api_base_url, url)
        headers_ = {} if headers is None else headers
        if auth:
            headers_.update(
                {
                    "X-Tidal-Token": self.client_id,
                    "Authorization": f"{self._token_type} {self._access_token}",
                }
            )

        resp = await self.sess.request(method, url, headers=headers_, **kwargs)
        if autorefresh and resp.status == 401 and (await resp.json())["subStatus"] == 11003:
            await self.refresh_session()
            return await self.request(method, url, auth, headers, False, **kwargs)
        else:
            resp.raise_for_status()

        return resp

    async def get(self, url, **kwargs):
        return await self.request("GET", url, **kwargs)

    async def post(self, url, **kwargs):
        return await self.request("POST", url, **kwargs)

    async def logout(self):
        # TODO [#14]: TidalSession.logout
        # WTF, android app doesn't send any request when clicking "Log out" button
        raise NotImplementedError

    async def refresh_session(self):
        if self._refresh_token is None:
            raise AuthorizationNeeded
        async with self.sess.post(
            self._oauth_token_url,
            data={
                "client_id": self.client_id,
                "grant_type": "refresh_token",
                "scope": "r_usr w_usr w_sub",
                "refresh_token": self._refresh_token,
            },
        ) as resp:
            data = await resp.json()
            if resp.status != 200:
                raise AuthorizationError(data["error"], data["error_description"])
            self._auth_info = data

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

    async def playlist(self, playlist_uuid):
        return await Playlist.from_id(self, playlist_uuid)

    async def artist(self, artist_id):
        return await Artist.from_id(self, artist_id)

    @staticmethod
    def is_valid_url(url: str) -> bool:
        url_ = urllib.parse.urlsplit(url)
        if not url_.scheme:
            # correctly parse urls without scheme
            url_ = urllib.parse.urlsplit("//" + url)

        if url_.netloc == "tidal.com" or url_.netloc.endswith(".tidal.com"):
            return True

        return False


class TidalMultiSession(TidalSession):
    # It helps with downloading multiple tracks simultaneously and overriding region lock
    # TODO [#8]: [TidalMultiSession] Run request on random session
    # TODO [#9]: [TidalMultiSession] Retry failed (404) requests (regionlock) on next session
    # TODO [$609fd0c46e4622062cd686b3]: [TidalMultiSession] Merge search results from all sessions
    # TODO [#10]: [TidalMultiSession] Try file download request on all sessions in queue fullness order
    #   Someone told me that Tidal blocks downloading of files simultaneously, but I didn't really noticed that
    def __init__(self, client_id):
        self.sessions = []
        self.client_id = client_id

    async def add_session(self, sess: Optional[TidalSession] = None, interactive_auth_url_getter=None):
        if sess is None:
            if interactive_auth_url_getter is None:
                raise AuthorizationError("missing auth handler")
            sess = TidalSession(self.client_id)
            await sess.login(interactive_auth_url_getter)

        if self._auth_info is None:
            raise AuthorizationNeeded("tried to add unauthenticated Tidal session to multi-session object")

        self.sessions.append(sess)

    async def login(self, *args, **kwargs):
        raise NotImplementedError

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
