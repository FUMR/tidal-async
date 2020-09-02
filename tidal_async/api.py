import base64
import enum
import json
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, AsyncGenerator, List

import music_service_async_interface as generic

from tidal_async.utils import id_from_url, parse_title, snake_to_camel

if TYPE_CHECKING:
    from tidal_async import TidalSession


# TODO [#1]: Artist object
#   needs https://github.com/FUMR/music-service-async-interface/issues/5 to be resolved first


class AudioQuality(enum.Enum):
    Normal = "LOW"
    High = "HIGH"
    HiFi = "LOSSLESS"
    Master = "HI_RES"


class AudioMode(enum.Enum):
    # TODO [#2]: Find more audio modes
    Stereo = "STEREO"


class Cover(generic.Cover):
    def __init__(self, sess: "TidalSession", id_):
        self.sess = sess
        self.id = id_

    def get_url(self, size=(640, 640)):
        # Valid resolutions: 80x80, 160x160, 320x320, 640x640, 1280x1280
        return f"https://resources.tidal.com/images/{self.id.replace('-', '/')}/{size[0]}x{size[1]}.jpg"


class TidalObject(generic.Object, ABC):
    def __init__(self, sess: "TidalSession", dict_):
        self.sess: "TidalSession" = sess
        self.dict = dict_

    @abstractmethod
    async def reload_info(self):
        ...

    @classmethod
    async def from_id(cls, sess: "TidalSession", id_):
        # TODO [#20]: Make sure from_id cannot be called on TidalObject
        #   Same goes for from_url
        #   I was pretty sure I can just mark it @abstractmethod and don't override it, but it looks like I was wrong
        obj = cls(sess, {"id": id_})
        await obj.reload_info()
        return obj

    @classmethod
    async def from_url(cls, sess: "TidalSession", url):
        if hasattr(cls, "urlname"):
            return await cls.from_id(sess, id_from_url(url, cls.urlname))

        # Called class has no field urlname so from_url is not implemented
        raise NotImplementedError

    async def get_url(self) -> str:
        return self.url

    def __getitem__(self, item):
        return self.dict[snake_to_camel(item)]

    def __contains__(self, item):
        return snake_to_camel(item) in self.dict

    def __getattr__(self, attr):
        return self[attr]


# TODO [#3]: Downloading lyrics
class Track(TidalObject, generic.Track):
    urlname = "track"

    def __repr__(self):
        cls = self.__class__
        return f"<{cls.__module__}.{cls.__qualname__} ({self.id}): {self.artist_name} - {self.title}>"

    async def reload_info(self):
        resp = await self.sess.get(
            f"/v1/tracks/{self.id}",
            params={
                "countryCode": self.sess.country_code,
            },
        )
        self.dict = await resp.json()

    @property
    def title(self) -> str:
        return self["title"]

    @property
    def artist_name(self) -> str:
        return self.artist["name"]

    @property
    def album(self):
        return Album(self.sess, self["album"])

    @property
    def cover(self):
        return self.album.cover

    # TODO [#21]: Track.artist
    #   Needs #1 to be resolved

    @property
    def audio_quality(self):
        return AudioQuality(self["audioQuality"])

    async def _playbackinfopostpaywall(self, audio_quality=AudioQuality.Master):
        resp = await self.sess.get(
            f"/v1/tracks/{self.id}/playbackinfopostpaywall",
            params={
                "playbackmode": "STREAM",
                "assetpresentation": "FULL",
                "audioquality": audio_quality.value,
            },
        )

        return await resp.json()

    async def _stream_manifest(self, audio_quality=AudioQuality.Master):
        data = await self._playbackinfopostpaywall(audio_quality)
        return json.loads(base64.b64decode(data["manifest"]))

    async def get_file_url(self, audio_quality=AudioQuality.Master) -> str:
        # TODO [#16]: [Track.get_stream_url] Raise exception when audio quality is worse than min_audio_quality
        #   eg. InsufficientAudioQuality
        # TODO [#17]: [Track.get_stream_url] Allow to specify min_audio_quality in per-session basics
        return (await self._stream_manifest(audio_quality))["urls"][0]

    async def get_metadata(self):
        # TODO [#22]: fix Track.get_metadata
        #   and add lyrics if possible
        album = self.album
        await album.reload_info()

        tags = {
            # general metatags
            "artist": self.artist_name,
            "title": parse_title(self, self.artists),
            # album related metatags
            "albumartist": album.artist["name"],
            "album": parse_title(album),
            "date": str(album.year),
            # track/disc position metatags
            "discnumber": str(self.volumeNumber),
            "disctotal": str(album.numberOfVolumes),
            "tracknumber": str(self.trackNumber),
            "tracktotal": str(album.numberOfTracks),
        }

        # Tidal sometimes returns null for track copyright
        if "copyright" in self and self.copyright:
            tags["copyright"] = self.copyright
        elif "copyright" in album and album.copyright:
            tags["copyright"] = album.copyright

        # identifiers for later use in own music libraries
        if "isrc" in self and self.isrc:
            tags["isrc"] = self.isrc
        if "upc" in album and album.upc:
            tags["upc"] = album.upc

        return tags


class Playlist(TidalObject, generic.TrackCollection):
    # TODO [#23]: Reimplement Playlist.from_id and Playlist.__init__
    #   Playlist field for `id` is named `uuid`, not `id` as in other objects
    #   Should also fix @wvffle 's workaround with self.dict.update
    urlname = "playlist"

    def __repr__(self):
        cls = self.__class__
        return f"<{cls.__module__}.{cls.__qualname__} ({self.id}): {self.title}>"

    async def reload_info(self):
        resp = await self.sess.get(
            f"/v1/playlists/{self.id}",
            params={
                "countryCode": self.sess.country_code,
            },
        )

        # NOTE: I'm updating self.dict and not reassigning it as the return from the api does not contain the `id` key
        self.dict.update(await resp.json())

    @property
    def cover(self):
        # NOTE: It may be also self['squareImage'], needs testing
        return Cover(self.sess, self["image"])

    async def tracks(self, per_request_limit=50) -> AsyncGenerator[Track, None]:
        offset = 0
        total_items = 1

        while offset < total_items:
            resp = await self.sess.get(f"/v1/playlists/{self.id}/tracks", params={
                "countryCode": self.sess.country_code,
                "offset": offset,
                "limit": per_request_limit,
            })
            data = await resp.json()

            total_items = data['totalNumberOfItems']
            offset = data['offset'] + data['limit']

            for track in data['items']:
                # python doesn't support `yield from` in async functions.. why?
                yield Track(self.sess, track)


class Album(TidalObject, generic.TrackCollection):
    urlname = "album"

    # TODO [#24]: Album.artist
    #   Needs #1 to be resolved

    def __repr__(self):
        cls = self.__class__
        return f"<{cls.__module__}.{cls.__qualname__} ({self.id}): {self.artist['name']} - {self.title}>"

    async def reload_info(self):
        resp = await self.sess.get(
            f"/v1/albums/{self.id}",
            params={
                "countryCode": self.sess.country_code,
            },
        )

        self.dict = await resp.json()

    @property
    def cover(self):
        return Cover(self.sess, self["cover"])

    async def tracks(self, per_request_limit=50) -> AsyncGenerator[Track, None]:
        offset = 0
        total_items = 1

        while offset < total_items:
            resp = await self.sess.get(f"/v1/albums/{self.id}/tracks", params={
                "countryCode": self.sess.country_code,
                "offset": offset,
                "limit": per_request_limit,
            })
            data = await resp.json()

            total_items = data['totalNumberOfItems']
            offset = data['offset'] + data['limit']

            for track in data['items']:
                # python doesn't support `yield from` in async functions.. why?
                yield Track(self.sess, track)