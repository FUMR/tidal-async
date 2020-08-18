import base64
import enum
import json
from typing import Callable, Optional, Union

try:
    from httpseekablefile import AsyncSeekableHTTPFile
except ImportError:
    pass


# TODO: playlists
# TODO: artists


class AudioQuality(enum.Enum):
    Normal = "LOW"
    High = "HIGH"
    HiFi = "LOSSLESS"
    Master = "HI_RES"


class AudioMode(enum.Enum):
    # TODO: find more modes
    Stereo = "STEREO"


class Cover(object):
    def __init__(self, tidal_session, id_):
        self.sess = tidal_session
        self.id = id_

    @property
    def url(self, size=(320, 320)):
        # Valid resolutions: 80x80, 160x160, 320x320, 640x640, 1280x1280
        return f"https://resources.tidal.com/images/{self.id.replace('-', '/')}/{size[0]}x{size[1]}.jpg"

    if 'AsyncSeekableHTTPFile' in globals():
        async def get_async_file(self, filename: Optional[str] = None):
            return await AsyncSeekableHTTPFile.create(self.url, filename, self.sess.sess)


class TidalObject(object):
    def __init__(self, tidal_session, dict_):
        self.sess = tidal_session
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
        resp = await self.sess.get(f"/v1/albums/{self.id}", params={
            "countryCode": self.sess.country_code
        })
        self.dict = await resp.json()

        # TODO: move to .tracks()
        resp = await self.sess.get(f"/v1/albums/{self.id}/tracks", params={
            "countryCode": self.sess.country_code
        })
        self.dict.update(await resp.json())

    @classmethod
    async def from_url(cls, tidal_session, url):
        # TODO
        raise NotImplemented

    @property
    def cover(self):
        return Cover(self.sess, self.dict['cover'])

    async def tracks(self):
        if 'items' not in self.dict:
            await self.reload_info()
        return [Track(self.sess, track) for track in self.dict['items']]


class Track(TidalObject):
    # TODO: lyrics
    async def reload_info(self):
        resp = await self.sess.get(f"/v1/tracks/{self.id}", params={
            "countryCode": self.sess.country_code
        })
        self.dict = await resp.json()

    @classmethod
    async def from_url(cls, tidal_session, url):
        # TODO
        raise NotImplemented

    @property
    def album(self):
        return Album(self.sess, self.dict['album'])

    @property
    def cover(self):
        return self.album.cover

    @property
    def audio_quality(self):
        return AudioQuality(self.dict['audioQuality'])

    async def _playbackinfopostpaywall(self, audio_quality=AudioQuality.Master):
        # TODO: audioMode
        resp = await self.sess.get(f"/v1/tracks/{self.id}/playbackinfopostpaywall", params={
            "playbackmode": "STREAM", "assetpresentation": "FULL",
            "audioquality": audio_quality.value
        })

        return await resp.json()

    async def _stream_manifest(self, audio_quality=AudioQuality.Master):
        data = await self._playbackinfopostpaywall(audio_quality)
        return json.loads(base64.b64decode(data['manifest']))
    
    async def stream_url(self, audio_quality=AudioQuality.Master):
        return (await self._stream_manifest(audio_quality))['urls'][0]

    if 'AsyncSeekableHTTPFile' in globals():
        async def get_async_file(self, audio_quality=AudioQuality.Master, filename: Optional[Union[Callable[['Track'], str], str]] = None):
            if callable(filename):
                filename = filename(self)
            elif filename is None:
                filename = self.title
            return await AsyncSeekableHTTPFile.create(await self.stream_url(audio_quality), filename, self.sess.sess)
