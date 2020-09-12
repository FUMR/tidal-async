import base64
import enum
import json
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import TYPE_CHECKING, AsyncGenerator, Optional, Tuple

import music_service_async_interface as generic

from tidal_async.exceptions import InsufficientAudioQuality
from tidal_async.utils import cacheable, gen_artist, gen_title, id_from_url, snake_to_camel

if TYPE_CHECKING:
    from tidal_async import TidalSession


# TODO [$5f5d45327772070dc3721d3c]: Fix caching of Objects when created with __init__

# TODO [$5f5d45327772070dc3721d3d]: Generic iterator
#   Now we have very similar code in Album.tracks, Playlist.tracks and Artist.albums


class AudioQuality(generic.AudioQuality):
    Normal = "LOW"
    High = "HIGH"
    HiFi = "LOSSLESS"
    Master = "HI_RES"


class AudioMode(enum.Enum):
    # TODO [#2]: Find more audio modes
    #   atm it will still be a string
    Stereo = "STEREO"


class Cover(generic.Cover):
    def __init__(self, sess: "TidalSession", id_):
        self.sess = sess
        self.id = id_

    def get_url(self, size=(640, 640)):
        # Valid resolutions: 80x80, 160x160, 320x320, 640x640, 1280x1280
        return f"https://resources.tidal.com/images/{self.id.replace('-', '/')}/{size[0]}x{size[1]}.jpg"


class TidalObject(generic.Object, ABC):
    def __init__(self, sess: "TidalSession", dict_, id_field_name="id"):
        self.sess: "TidalSession" = sess
        self.dict = dict_
        self._id_field_name = id_field_name

    def __repr__(self):
        cls = self.__class__
        return f"<{cls.__module__}.{cls.__qualname__} ({self.get_id()})>"

    @abstractmethod
    async def reload_info(self):
        ...

    @classmethod
    @lru_cache
    @cacheable
    async def from_id(cls, sess: "TidalSession", id_, id_field_name="id") -> "TidalObject":
        if cls is TidalObject:
            # method should be used on child classes
            raise NotImplementedError

        obj = cls(sess, {id_field_name: id_}, id_field_name)
        await obj.reload_info()
        return obj

    @classmethod
    async def from_url(cls, sess: "TidalSession", url) -> "TidalObject":
        if cls is TidalObject:
            # method should be used on child classes
            raise NotImplementedError

        if hasattr(cls, "urlname"):
            return await cls.from_id(sess, id_from_url(url, cls.urlname))

        # Called class has no field urlname so from_url is not implemented
        raise NotImplementedError

    async def get_url(self) -> str:
        return self.url

    def get_id(self):
        return self[self._id_field_name]

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
        return f"<{cls.__module__}.{cls.__qualname__} ({self.get_id()}): {self.artist_name} - {self.title}>"

    async def reload_info(self):
        resp = await self.sess.get(
            f"/v1/tracks/{self.get_id()}",
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
        return self.artist.name

    @property
    def album(self):
        return Album(self.sess, self["album"])

    @property
    def cover(self):
        return self.album.cover

    @property
    def artist(self):
        return Artist(self.sess, self["artist"])

    async def artists(self) -> AsyncGenerator[Tuple["Artist", str], None]:
        # TODO [$5f5d45327772070dc3721d3e]: Artist types enum
        for artist in self["artists"]:
            yield await Artist.from_id(self.sess, artist["id"]), artist["type"]

    @property
    def audio_quality(self):
        return AudioQuality(self["audioQuality"])

    async def _playbackinfopostpaywall(self, preferred_audio_quality):
        resp = await self.sess.get(
            f"/v1/tracks/{self.get_id()}/playbackinfopostpaywall",
            params={
                "playbackmode": "STREAM",
                "assetpresentation": "FULL",
                "audioquality": preferred_audio_quality.value,
            },
        )

        return await resp.json()

    async def _stream_manifest(self, preferred_audio_quality):
        data = await self._playbackinfopostpaywall(preferred_audio_quality)
        return json.loads(base64.b64decode(data["manifest"])), data

    async def get_file_url(
        self,
        required_quality: Optional[AudioQuality] = None,
        preferred_quality: Optional[AudioQuality] = None,
        **kwargs,
    ) -> str:
        if preferred_quality is None:
            preferred_quality = self.sess.preferred_audio_quality
        if required_quality is None:
            required_quality = self.sess.required_audio_quality

        manifest, playback_info = await self._stream_manifest(preferred_quality)
        quality = AudioQuality(playback_info["audioQuality"])

        if quality < required_quality:
            raise InsufficientAudioQuality(f"Got {quality} for {self}, required audio quality is {required_quality}")

        return manifest["urls"][0]

    async def get_metadata(self):
        # TODO [#22]: Rewrite Track.get_metadata
        #   - [ ] lyrics
        #   - [x] rewrite title parsing
        #   - [x] replayGain
        #   - [ ] multiple artists
        album = self.album
        await album.reload_info()

        tags = {
            # general metatags
            "artist": await gen_artist(self),
            "title": await gen_title(self),
            # album related metatags
            "albumartist": await gen_artist(album),
            "album": await gen_title(album),
            "date": album.release_date,
            # track/disc position metatags
            "discnumber": self.volume_number,
            "disctotal": album.number_of_volumes,
            "tracknumber": self.track_number,
            "tracktotal": album.number_of_tracks,
            "replaygain_track_gain": self.replay_gain,
            "replaygain_track_peak": self.peak,
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


class Playlist(TidalObject, generic.ObjectCollection[Track]):
    urlname = "playlist"

    def __repr__(self):
        cls = self.__class__
        return f"<{cls.__module__}.{cls.__qualname__} ({self.get_id()}): {self.title}>"

    async def reload_info(self):
        resp = await self.sess.get(
            f"/v1/playlists/{self.get_id()}",
            params={
                "countryCode": self.sess.country_code,
            },
        )

        self.dict = await resp.json()

    @classmethod
    async def from_id(cls, sess: "TidalSession", id_: str, id_field_name="uuid") -> "Playlist":
        playlist = await super().from_id(sess, id_, id_field_name)
        assert isinstance(playlist, cls)
        return playlist

    @property
    def cover(self):
        # NOTE: It may be also self['squareImage'], needs testing
        return Cover(self.sess, self["image"])

    async def tracks(self, per_request_limit=50) -> AsyncGenerator[Track, None]:
        offset = 0
        total_items = 1

        while offset < total_items:
            resp = await self.sess.get(
                f"/v1/playlists/{self.get_id()}/tracks",
                params={
                    "countryCode": self.sess.country_code,
                    "offset": offset,
                    "limit": per_request_limit,
                },
            )
            data = await resp.json()

            total_items = data["totalNumberOfItems"]
            offset = data["offset"] + data["limit"]

            for track in data["items"]:
                # python doesn't support `yield from` in async functions.. why?
                yield Track(self.sess, track)


class Album(TidalObject, generic.ObjectCollection[Track]):
    urlname = "album"

    @property
    def artist(self):
        return Artist(self.sess, self["artist"])

    def __repr__(self):
        cls = self.__class__
        return f"<{cls.__module__}.{cls.__qualname__} ({self.get_id()}): {self.title}>"

    async def reload_info(self):
        resp = await self.sess.get(
            f"/v1/albums/{self.get_id()}",
            params={
                "countryCode": self.sess.country_code,
            },
        )

        self.dict = await resp.json()

    @property
    def cover(self):
        return Cover(self.sess, self["cover"])

    async def artists(self) -> AsyncGenerator[Tuple["Artist", str], None]:
        # TODO [$5f5d45327772070dc3721d3f]: Artist types enum
        for artist in self["artists"]:
            yield await Artist.from_id(self.sess, artist["id"]), artist["type"]

    async def tracks(self, per_request_limit=50) -> AsyncGenerator[Track, None]:
        offset = 0
        total_items = 1

        while offset < total_items:
            resp = await self.sess.get(
                f"/v1/albums/{self.get_id()}/tracks",
                params={
                    "countryCode": self.sess.country_code,
                    "offset": offset,
                    "limit": per_request_limit,
                },
            )
            data = await resp.json()

            total_items = data["totalNumberOfItems"]
            offset = data["offset"] + data["limit"]

            for track in data["items"]:
                # python doesn't support `yield from` in async functions.. why?
                yield Track(self.sess, track)


class Artist(TidalObject, generic.ObjectCollection[Album]):
    urlname = "artist"

    def __repr__(self):
        cls = self.__class__
        return f"<{cls.__module__}.{cls.__qualname__} ({self.get_id()}): {self.name}>"

    async def reload_info(self):
        resp = await self.sess.get(
            f"/v1/artists/{self.get_id()}",
            params={
                "countryCode": self.sess.country_code,
            },
        )

        self.dict = await resp.json()

    @property
    def picture(self):
        return Cover(self.sess, self["picture"])

    async def albums(self, per_request_limit=10) -> AsyncGenerator[Album, None]:
        offset = 0
        total_items = 1

        while offset < total_items:
            resp = await self.sess.get(
                f"/v1/artists/{self.get_id()}/albums",
                params={
                    "countryCode": self.sess.country_code,
                    "offset": offset,
                    "limit": per_request_limit,
                },
            )
            data = await resp.json()

            total_items = data["totalNumberOfItems"]
            offset = data["offset"] + data["limit"]

            for album in data["items"]:
                # python doesn't support `yield from` in async functions.. why?
                yield Album(self.sess, album)
