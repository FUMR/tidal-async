import base64
import hashlib
import os
import urllib.parse
from typing import Awaitable, Callable, List, Optional

import aiohttp
import aiohttp.typedefs
import music_service_async_interface as generic

from tidal_async import Album, Artist, AudioQuality, Playlist, TidalObject, Track
from tidal_async.exceptions import AuthenticationError, AuthenticationNeeded


class TidalSession(generic.Session):
    _obj = TidalObject
    _quality = AudioQuality

    _redirect_uri = "https://tidal.com/android/login/auth"  # or tidal://login/auth
    _api_base_url = "https://api.tidal.com/"
    _oauth_authorize_url = "https://login.tidal.com/authorize"
    _oauth_token_url = "https://auth.tidal.com/v1/oauth2/token"

    def __init__(self, client_id: str, sess: Optional[aiohttp.ClientSession] = None):
        """
        :param client_id: Tidal client ID to be used with session
        Can be extracted from Android app (.apk file) using `extract_client_id` from `tidal_async.utils`.
        :param sess: optional preconfigured :class:`aiohttp.ClientSession` to be used with this :class:`TidalSession`
        """
        super().__init__(sess)
        self.client_id = client_id

        self._auth_info = None
        self._refresh_token = None

    @property
    def _access_token(self):
        if self._auth_info is None:
            raise AuthenticationNeeded
        return self._auth_info["access_token"]

    @property
    def _token_type(self):
        if self._auth_info is None:
            raise AuthenticationNeeded
        return self._auth_info["token_type"]

    @property
    def country_code(self) -> str:
        """
        Gets Tidal account's country code
        It specifies which region-locked content is available to account.

        :return: Tidal account's country code
        :raises AuthenticationNeeded: when used on unauthorized (not logged in) session
        """
        if self._auth_info is None:
            raise AuthenticationNeeded
        return self._auth_info["user"]["countryCode"]

    async def login(self, interactive_auth_url_getter: Callable[[str], Awaitable[str]], force_relogin=False) -> None:
        """Log the session into Tidal

        :param interactive_auth_url_getter: awaitable callable (eg. async function) for handling interactive auth
        It gets one argument (`authorization_url`) which is URL that needs to be opened by user.
        User needs to authenticate on page and provide resulting URL to the function.
        Function needs to return this URL to complete the authentication.
        Example is `cli_auth_url_getter` from `tidal_api.utils`.
        :param force_relogin: when True forces relogin even if already logged in
        :raises AuthenticationError: when authorization failed
        """
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
                raise AuthenticationError(data["error"], data["error_description"])
            self._auth_info = data
            self._refresh_token = data["refresh_token"]

    async def request(
        self,
        method: str,
        url: aiohttp.typedefs.StrOrURL,
        auth: bool = True,
        headers: Optional[dict] = None,
        autorefresh: bool = True,
        **kwargs,
    ) -> aiohttp.ClientResponse:
        """Asynchroniously sends arbitary request to Tidal's API endpoint

        :param method: HTTP method to use
        eg. GET, POST, HEAD
        :param url: URL to be requested from Tidal server
        It will be joined with API base URL.
        eg. request to `url='topkek'` becomes `'https://api.tidal.com/topkek'`
        :param auth: when True, auth data should be added to the request
        :param headers: dict containing headers to be added to the request
        :param autorefresh: when True and request fails because of expired token, session is refreshed and request retried
        :param kwargs: additional arguments to `aiohttp`
        :raises aiohttp.ClientResponseError: when HTTP error happened
        :return: HTTP response from server
        """

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

    async def get(self, url: aiohttp.typedefs.StrOrURL, **kwargs) -> aiohttp.ClientResponse:
        """Asynchroniously sends arbitary HTTP GET request to Tidal's API endpoint

        :param url: part of URL to be joined with API base URL and requested
        eg. request to `url='topkek'` becomes `'https://api.tidal.com/topkek'`
        :param kwargs: additional arguments to `request` method or `aiohttp`
        :raises aiohttp.ClientResponseError: when HTTP error happened
        :return: HTTP response from server
        """
        return await self.request("GET", url, **kwargs)

    async def post(self, url: aiohttp.typedefs.StrOrURL, **kwargs) -> aiohttp.ClientResponse:
        """Asynchroniously sends arbitary HTTP POST request to Tidal's API endpoint

        :param url: part of URL to be joined with API base URL and requested
        eg. request to `url='topkek'` becomes `'https://api.tidal.com/topkek'`
        :param kwargs: additional arguments to `request` method or `aiohttp`
        :raises aiohttp.ClientResponseError: when HTTP error happened
        :return: HTTP response from server
        """
        return await self.request("POST", url, **kwargs)

    async def logout(self):
        # TODO [#67]: TidalSession.logout
        #   Android app doesn't send any request when clicking "Log out" button
        #   Do we need this?
        raise NotImplementedError

    async def refresh_session(self) -> None:
        """Refreshes tokens stored in :class:`TidalSession` using `refresh_token`

        :raises AuthenticationNeeded: when used on unauthorized (not logged in) session
        :raises AuthenticationError: when authorization failed
        """
        if self._refresh_token is None:
            raise AuthenticationNeeded
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
                raise AuthenticationError(data["error"], data["error_description"])
            self._auth_info = data

    async def close(self):
        """Closes session
        Should be called when session is not gonna be used anymore.
        Does underlying cleanup.
        """
        await self.sess.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def track(self, track_id: int) -> Track:
        """Gets :class:`Track` from Tidal based on ID

        example:
        >>> await sess.track(22563746)
        <tidal_async.api.Track (22563746): Drake - Furthest Thing>

        :param track_id: Tidal ID of :class:`Track`
        :return: :class:`Track` corresponding to Tidal ID
        """
        return await Track.from_id(self, track_id)

    async def album(self, album_id: int) -> Album:
        """Gets :class:`Album` from Tidal based on ID

        example:
        >>> await sess.album(91969976)
        <tidal_async.api.Album (91969976): Do>

        :param album_id: Tidal ID of :class:`Album`
        :return: :class:`Album` corresponding to Tidal ID
        """
        return await Album.from_id(self, album_id)

    async def playlist(self, playlist_uuid: str):
        """Gets :class:`Playlist` from Tidal based on UUID

        example:
        >>> await sess.playlist("dcbab999-7523-4e2f-adf4-57d10fc17516")
        <tidal_async.api.Playlist (dcbab999-7523-4e2f-adf4-57d10fc17516): Soundtracking: Need for Speed>

        :param playlist_uuid: Tidal UUID of :class:`Playlist`
        :return: :class:`Playlist` corresponding to Tidal UUID
        """
        return await Playlist.from_id(self, playlist_uuid)

    async def artist(self, artist_id: int):
        """Gets :class:`Artist` from Tidal based on ID

        example:
        >>> await sess.artist(17752)
        <tidal_async.api.Artist (17752): Psychostick>

        :param artist_id: Tidal ID of :class:`Artist`
        :return: :class:`Artist` corresponding to Tidal ID
        """
        return await Artist.from_id(self, artist_id)

    @staticmethod
    def is_valid_url(url: str) -> bool:
        """Checks if `url` is valid Tidal URL

        :param url: URL to be checked
        :return: `True` if valid Tidal URL, else `False`
        """
        url_ = urllib.parse.urlsplit(url)
        if not url_.scheme:
            # correctly parse urls without scheme
            url_ = urllib.parse.urlsplit("//" + url)

        if url_.netloc == "tidal.com" or url_.netloc.endswith(".tidal.com"):
            return True

        return False


class TidalMultiSession(TidalSession):
    """Class providing unified :class:`TidalSession` based interface consisting of multiple sessions
    It helps with overcoming region lock and rate limits using multiple Tidal accounts and possibly separate proxies.
    """

    # TODO [#68]: Run request on random session in TidalMultiSession
    # TODO [#69]: Retry failed (404) requests (regionlock) on next session in TidalMultiSession
    # TODO [#61]: Merge search results from all sessions in TidalMultiSession
    def __init__(self, client_id: str):
        """
        :param client_id: Tidal client ID to be used with session
        Can be extracted from Android app (.apk file) using `extract_client_id` from `tidal_async.utils`.
        """
        self.sessions: List[TidalSession] = []
        self.client_id: str = client_id

    async def add_session(self, sess: TidalSession) -> None:
        """Add existing :class:`TidalSession` to list of sessions

        :param sess: authorized :class:`TidalSession`
        :raises AuthenticationNeeded: if supplied session is not authenticated
        """
        assert isinstance(sess, TidalSession)

        if sess._auth_info is None:
            raise AuthenticationNeeded("tried to add unauthenticated Tidal session to multi-session object")

        self.sessions.append(sess)

    async def login(
        self,
        interactive_auth_url_getter: Callable[[str], Awaitable[str]],
        force_relogin=False,
        client_id: Optional[str] = None,
        sess: Optional[aiohttp.ClientSession] = None,
    ) -> None:
        """Log the session into Tidal and add it to sessions list

        :param interactive_auth_url_getter: awaitable callable (eg. async function) for handling interactive auth
        It get's one argument (`authorization_url`) which is URL that needs to be opened by user.
        User needs to authenticate on page and provide resulting URL to the function.
        Function needs to return this URL to complete the authorization.
        Example is `cli_auth_url_getter` from `tidal_api.utils`.
        :param force_relogin: when True forces relogin even if already logged in
        :param client_id: Tidal client ID to be used with session
        Can be extracted from Android app (.apk file) using `extract_client_id` from `tidal_async.utils`.
        When not provided, client_id from :class:`TidalMultiSession` will be used.
        :param sess: optional preconfigured :class:`aiohttp.ClientSession` to be used with this :class:`TidalSession`
        :raises AuthenticationError: when authentication failed
        """
        if not client_id:
            client_id = self.client_id

        tsess = TidalSession(client_id, sess)
        await tsess.login(interactive_auth_url_getter, force_relogin)

        self.sessions.append(tsess)

    async def logout(self, sess: Optional[TidalSession] = None) -> None:
        """Logs out and removes `sess` from sessions list session
        When no `sess` specified all sessions are logged out and removed.

        :param sess: :class:`TidalSession` to logout and remove
        """
        if sess is None:
            for s in self.sessions[:]:
                s.logout()
                s.close()
                self.sessions.remove(s)
        else:
            if sess in self.sessions:
                sess.logout()
                sess.close()
                self.sessions.remove(sess)

    async def close(self):
        """Closes all sessions
        Should be called when session is not gonna be used anymore.
        Does underlying cleanup.
        """
        for s in self.sessions:
            await s.close()
