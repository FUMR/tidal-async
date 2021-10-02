import asyncio
import base64
import enum
import json
from abc import ABC
from functools import lru_cache
from typing import TYPE_CHECKING, AsyncGenerator, List, Optional, Tuple, Type

import music_service_async_interface as generic
from aiohttp import ClientResponseError

from tidal_async.exceptions import InsufficientAudioQuality
from tidal_async.utils import cacheable, gen_artist, gen_title, id_from_url, snake_to_camel

if TYPE_CHECKING:
    from tidal_async import TidalSession


# TODO [#47]: Fix caching of Objects when created with __init__


class AudioQuality(generic.AudioQuality):
    Normal = "LOW"
    High = "HIGH"
    HiFi = "LOSSLESS"
    Master = "HI_RES"


class AudioMode(enum.Enum):
    # TODO [#66]: Find more audio modes
    #   Until we can fill whole `Enum` it will still be used as a string.
    Stereo = "STEREO"


class Cover(generic.Cover):
    def __init__(self, sess: "TidalSession", id_):
        self.sess = sess
        self.id = id_

    def get_url(self, size=(640, 640)) -> str:
        """Gets :class:`Cover` image URL

        :param size: image resolution tuple: `(640, 640)` means the image will be 640x640
        known valid tuples are: `(80, 80)`, `(160, 160)`, `(320, 320)`, `(640, 640)`, `(1280, 1280)`
        :return: URL to :class:`Cover` image
        """
        return f"https://resources.tidal.com/images/{self.id.replace('-', '/')}/{size[0]}x{size[1]}.jpg"


class TidalObject(generic.Object, ABC):
    _id_field_name = "id"

    def __init__(
        self,
        sess: "TidalSession",
        dict_,
    ):
        self.sess: "TidalSession" = sess
        self.dict = dict_

    def __repr__(self):
        cls = self.__class__
        return f"<{cls.__module__}.{cls.__qualname__} ({self.get_id()})>"

    async def _iter_coll(self, coll_name, obj_type: Type["TidalObject"], per_request_limit):
        offset = 0
        total_items = 1

        while offset < total_items:
            resp = await self.sess.get(
                f"/v1/{self.apiname}/{self.get_id()}/{coll_name}",
                params={
                    "countryCode": self.sess.country_code,
                    "offset": offset,
                    "limit": per_request_limit,
                },
            )
            data = await resp.json()

            total_items = data["totalNumberOfItems"]
            offset = data["offset"] + data["limit"]

            for item in data["items"]:
                # python doesn't support `yield from` in async functions.. why?
                yield obj_type(self.sess, item)

    async def reload_info(self) -> None:
        """Reloads object's information from Tidal server"""
        resp = await self.sess.get(
            f"/v1/{self.apiname}/{self.get_id()}",
            params={
                "countryCode": self.sess.country_code,
            },
        )
        self.dict = await resp.json()

    @classmethod
    @lru_cache()
    @cacheable
    async def from_id(cls, sess: "TidalSession", id_) -> "TidalObject":
        """Fetches object from Tidal based on ID

        example:
        >>> await Track.from_id(sess, 22563746)
        <tidal_async.api.Track (22563746): Drake - Furthest Thing>
        >>> await Playlist.from_id(sess, "dcbab999-7523-4e2f-adf4-57d10fc17516")
        <tidal_async.api.Playlist (dcbab999-7523-4e2f-adf4-57d10fc17516): Soundtracking: Need for Speed>
        >>> await Album.from_id(sess, 91969976)
        <tidal_async.api.Album (91969976): Do>
        >>> await Artist.from_id(sess, 17752)
        <tidal_async.api.Artist (17752): Psychostick>

        TIP: :class:`TidalSession`'s function can be used instead!
        >>> await sess.track(22563746)
        <tidal_async.api.Track (22563746): Drake - Furthest Thing>
        >>> await sess.playlist("dcbab999-7523-4e2f-adf4-57d10fc17516")
        <tidal_async.api.Playlist (dcbab999-7523-4e2f-adf4-57d10fc17516): Soundtracking: Need for Speed>
        >>> await sess.album(91969976)
        <tidal_async.api.Album (91969976): Do>
        >>> await sess.artist(17752)
        <tidal_async.api.Artist (17752): Psychostick>

        :param sess: :class:`TidalSession` instance to use when loading data from Tidal
        :param id_: Tidal ID of object
        :raises NotImplementedError: when particular object can't be fetched by ID
        :return: corresponding object, e.g. :class:`Track` or :class:`Playlist`
        """
        if cls is TidalObject:
            # method should be used on child classes
            raise NotImplementedError

        obj = cls(sess, {cls._id_field_name: id_})
        await obj.reload_info()
        return obj

    @classmethod
    async def from_url(cls, sess: "TidalSession", url: str) -> "TidalObject":
        """Fetches object from Tidal based on URL

        example:
        >>> await Track.from_url(sess, 'https://www.tidal.com/track/22563746')
        <tidal_async.api.Track (22563746): Drake - Furthest Thing>
        >>> await Playlist.from_url(sess, 'https://www.tidal.com/playlist/dcbab999-7523-4e2f-adf4-57d10fc17516')
        <tidal_async.api.Playlist (dcbab999-7523-4e2f-adf4-57d10fc17516): Soundtracking: Need for Speed>
        >>> await Album.from_url(sess, 'https://www.tidal.com/album/91969976')
        <tidal_async.api.Album (91969976): Do>
        >>> await Artist.from_url(sess, 'https://www.tidal.com/artist/17752')
        <tidal_async.api.Artist (17752): Psychostick>

        TIP: :class:`TidalSession`'s functions can be used instead, those will autodetect object type!
        >>> await sess.object_from_url('https://www.tidal.com/artist/17752')
        <tidal_async.api.Artist (17752): Psychostick>
        >>> [o async for o in sess.parse_urls('''parsing https://www.tidal.com/artist/17752 topkek
        ... https://www.tidal.com/album/91969976 urls''')]
        [<tidal_async.api.Artist (17752): Psychostick>, <tidal_async.api.Album (91969976): Do>]

        :param sess: :class:`TidalSession` instance to use when loading data from Tidal
        :param url: Tidal URL to corresponding object
        :raises NotImplementedError: when particular object type can't be fetched by URL
        :raises InvalidURL: when URL is being unparsable by this :class:`TidalObject`
        :return: corresponding object, e.g. :class:`Track` or :class:`Playlist`
        """
        if cls is TidalObject:
            # method should be used on child classes
            raise NotImplementedError

        if hasattr(cls, "urlname"):
            return await cls.from_id(sess, id_from_url(url, cls.urlname))

        # Called class has no field urlname so from_url is not implemented
        raise NotImplementedError

    async def get_url(self) -> str:
        """Gets object's URL

        :return: URL to object
        """
        return self.url

    def get_id(self):
        """Gets object's Tidal ID

        :return: Tidal ID of object
        """
        return self[self._id_field_name]

    def __getitem__(self, item):
        return self.dict[snake_to_camel(item)]

    def __contains__(self, item):
        return snake_to_camel(item) in self.dict

    def __getattr__(self, attr):
        return self[attr]


class ArtistType(enum.Enum):
    main = "MAIN"
    featured = "FEATURED"
    contributor = "CONTRIBUTOR"
    artist = "ARTIST"


class Track(TidalObject, generic.Searchable, generic.Track):
    urlname = "track"
    apiname = "tracks"

    def __init__(self, sess: "TidalSession", dict_):
        super().__init__(sess, dict_)
        self._lyrics_dict = None

    def __repr__(self):
        cls = self.__class__
        return f"<{cls.__module__}.{cls.__qualname__} ({self.get_id()}): {self.artist_name} - {self.title}>"

    async def reload_info(self) -> None:
        """Reloads :class:`Track`'s information from Tidal server"""
        await super().reload_info()
        self._lyrics_dict = None

    @property
    def title(self) -> str:
        """
        :return: :class:`Track`'s title
        """
        return self["title"]

    @property
    def artist_name(self) -> str:
        """
        :return: :class:`Track`'s :class:`Artist` name
        """
        return gen_artist(self)

    @property
    def album(self) -> "Album":
        """
        :return: :class:`Album` containing :class:`Track`
        """
        return Album(self.sess, self["album"])

    @property
    def cover(self) -> Optional[Cover]:
        """
        :return: :class:`Cover` image or `None` if :class:`Track` has no cover
        """
        return self.album.cover

    @property
    def artists(self) -> List[Tuple["Artist", ArtistType]]:
        """Generates :class:`list` of :class:`Artist`s of the :class:`Track` with their corresponding role

        example:
        >>> track = await sess.track(182424124)
        >>> track.artists
        [(<tidal_async.api.Artist (3639903): Oki>, <ArtistType.main: 'MAIN'>),
         (<tidal_async.api.Artist (9191980): Young Igi>, <ArtistType.main: 'MAIN'>),
         (<tidal_async.api.Artist (6803759): Otsochodzi>, <ArtistType.main: 'MAIN'>),
         (<tidal_async.api.Artist (9729783): OIO>, <ArtistType.featured: 'FEATURED'>),
         (<tidal_async.api.Artist (10518755): @Atutowy>, <ArtistType.featured: 'FEATURED'>)]

        :return: :class:`list` of `(`:class:`Artist``, `:class:`ArtistType``)`
        """
        return [(Artist(self.sess, a), ArtistType(a["type"])) for a in self["artists"]]

    @property
    def audio_quality(self) -> AudioQuality:
        """
        :return: maximum available :class:`AudioQuality` of :class:`Track`
        """
        return AudioQuality(self["audioQuality"])

    async def _playbackinfopostpaywall(self, preferred_audio_quality) -> dict:
        resp = await self.sess.get(
            f"/v1/tracks/{self.get_id()}/playbackinfopostpaywall",
            params={
                "playbackmode": "STREAM",
                "assetpresentation": "FULL",
                "audioquality": preferred_audio_quality.value,
            },
        )

        return await resp.json()

    async def get_file_url(
        self,
        required_quality: Optional[AudioQuality] = None,
        preferred_quality: Optional[AudioQuality] = None,
        **kwargs,
    ) -> str:
        """Fetches direct URL to music file

        :param required_quality: required (lower limit) :class:`AudioQuality` for track
        if ommited value from session is used
        :param preferred_quality: preferred (upper limit) :class:`AudioQuality` you want to get
        if ommited value from session is used
        :param kwargs: not used
        :raises InsufficientAudioQuality: when available :class:`AudioQuality` is lower than `required_quality`
        :return: direct URL of music file
        """
        if preferred_quality is None:
            preferred_quality = self.sess.preferred_audio_quality
        if required_quality is None:
            required_quality = self.sess.required_audio_quality

        playback_info = await self._playbackinfopostpaywall(preferred_quality)
        quality = AudioQuality(playback_info["audioQuality"])

        if quality < required_quality:
            raise InsufficientAudioQuality(f"Got {quality} for {self}, required audio quality is {required_quality}")

        try:
            manifest = json.loads(base64.b64decode(playback_info["manifest"]))
        except json.decoder.JSONDecodeError:
            return f'data:application/dash+xml;base64,{playback_info["manifest"]}'
        return manifest["urls"][0]

    async def _lyrics(self) -> Optional[dict]:
        if self._lyrics_dict is not None:
            return self._lyrics_dict

        try:
            resp = await self.sess.get(
                f"/v1/tracks/{self.get_id()}/lyrics", params={"countryCode": self.sess.country_code}
            )
        except ClientResponseError as e:
            if e.status == 404:
                return None
            else:
                raise

        self._lyrics_dict = await resp.json()
        return self._lyrics_dict

    async def lyrics(self) -> Optional[str]:
        """Fetches lyrics for :class:`Track`

        :return: Lyrics string when available, `None` when not
        """
        lyrics_dict = await self._lyrics()
        if lyrics_dict is None or "lyrics" not in lyrics_dict:
            return None

        return lyrics_dict["lyrics"]

    async def subtitles(self) -> Optional[str]:
        """Fetches subtitles (time-synchronized lyrics) for :class:`Track`

        :return: Subtitles string in LRC format when available, `None` when not
        """
        lyrics_dict = await self._lyrics()
        if lyrics_dict is None or "subtitles" not in lyrics_dict:
            return None

        return lyrics_dict["subtitles"]

    async def get_metadata(self) -> dict:
        """Generates metadata for music file to be tagged with

        :return: dict containing tags compatbile with `mediafile` library
        """
        album = self.album

        [url, lyrics, _] = await asyncio.gather(self.get_url(), self.lyrics(), album.reload_info())

        tags = {
            # general metatags
            "artist": self.artist_name,
            "artists": [a[0].name for a in self.artists],
            "title": gen_title(self),
            # album related metatags
            "albumartist": album.artist_name,
            "albumartists": [a[0].name for a in album.artists],
            "album": gen_title(album),
            "date": album.release_date,
            # track/disc position metatags
            "disc": self.volume_number,
            "disctotal": album.number_of_volumes,
            "track": self.track_number,
            "tracktotal": album.number_of_tracks,
            # replaygain
            "rg_track_gain": self.replay_gain,
            "rg_track_peak": self.peak,
            # track url
            "url": url,
        }

        # Tidal sometimes returns null for track copyright
        if "copyright" in self and self.copyright:
            tags["copyright"] = self.copyright
        elif "copyright" in album and album.copyright:
            tags["copyright"] = album.copyright

        # identifiers for later use in music libraries
        if "isrc" in self and self.isrc:
            tags["isrc"] = self.isrc
        if "upc" in album and album.upc:
            tags["barcode"] = album.upc

        if lyrics:
            tags["lyrics"] = lyrics

        # uses cached lyrics data
        subtitles = await self.subtitles()
        if subtitles:
            # TODO [#60]: Support for subtitles tag
            #   Preliminary (invalid) support for subtitles tag.
            #   Subtitles are not supported in `mediafile` at the moment.
            #   depends on solving the beetbox/mediafile#48
            tags["subtitles"] = subtitles

        return tags


class Playlist(TidalObject, generic.Searchable, generic.ObjectCollection[Track]):
    urlname = "playlist"
    apiname = "playlists"
    _id_field_name = "uuid"

    def __repr__(self):
        cls = self.__class__
        return f"<{cls.__module__}.{cls.__qualname__} ({self.get_id()}): {self.title}>"

    @classmethod
    @lru_cache()
    @cacheable
    async def from_id(cls, sess: "TidalSession", id_: str) -> "Playlist":
        """Fetches :class:`Playlist` from Tidal based on ID

        example:
        >>> await Playlist.from_id(sess, "dcbab999-7523-4e2f-adf4-57d10fc17516")
        <tidal_async.api.Playlist (dcbab999-7523-4e2f-adf4-57d10fc17516): Soundtracking: Need for Speed>

        TIP: :class:`TidalSession`'s function can be used instead!
        >>> await sess.playlist("dcbab999-7523-4e2f-adf4-57d10fc17516")
        <tidal_async.api.Playlist (dcbab999-7523-4e2f-adf4-57d10fc17516): Soundtracking: Need for Speed>

        :param sess: :class:`TidalSession` instance to use when loading data from Tidal
        :param id_: Tidal ID of :class:`Playlist`
        :return: :class:`Playlist` corresponding to Tidal ID
        """
        playlist = await super().from_id(sess, id_)
        assert isinstance(playlist, cls)
        return playlist

    @property
    def cover(self) -> Optional[Cover]:
        """
        :return: :class:`Cover` image or `None` if :class:`Playlist` has no cover
        """
        # NOTE: It may be also self['squareImage'], needs testing
        return Cover(self.sess, self["image"]) if self["image"] is not None else None

    async def tracks(self, per_request_limit: int = 50) -> AsyncGenerator[Track, None]:
        """Generates async interable of :class:`Track`s in the :class:`Playlist`

        example:
        >>> playlist = await sess.playlist("dcbab999-7523-4e2f-adf4-57d10fc17516")
        >>> [t async for t in playlist.tracks()]
        [<tidal_async.api.Track (479662): Wolfmother - Joker And The Thief>,
         <tidal_async.api.Track (68508927): My Chemical Romance - Thank You for the Venom>,
         <tidal_async.api.Track (17461909): Lower Than Atlantis - Love Someone Else>,
         <tidal_async.api.Track (58070669): EA Games Soundtrack - Wingman>,
         ...]

        :param per_request_limit: max amount of :class:`Track`s to load in one request
        :yield: :class:`Track`s in the :class:`Playlist`
        """
        async for track in self._iter_coll("tracks", Track, per_request_limit):
            yield track


class Album(TidalObject, generic.Searchable, generic.ObjectCollection[Track]):
    urlname = "album"
    apiname = "albums"

    def __repr__(self):
        cls = self.__class__
        return f"<{cls.__module__}.{cls.__qualname__} ({self.get_id()}): {self.title}>"

    @property
    def artist_name(self) -> str:
        """
        :return: :class:`Album`'s :class:`Artist` name
        """
        return gen_artist(self)

    @property
    def cover(self) -> Optional[Cover]:
        """
        :return: :class:`Cover` image or `None` if :class:`Album` has no cover
        """
        return Cover(self.sess, self["cover"]) if self["cover"] is not None else None

    @property
    def artists(self) -> List[Tuple["Artist", ArtistType]]:
        """Generates :class:`list` of :class:`Artist`s of the :class:`Album` with their corresponding role

        example:
        >>> album = await sess.album(180429444)
        >>> album.artists
        [(<tidal_async.api.Artist (4609597): donGURALesko>, <ArtistType.main: 'MAIN'>),
         (<tidal_async.api.Artist (3974059): The Returners>, <ArtistType.main: 'MAIN'>)]

        :return: :class:`list` of `(`:class:`Artist``, `:class:`ArtistType``)`
        """

        return [(Artist(self.sess, a), ArtistType(a["type"])) for a in self["artists"]]

    async def tracks(self, per_request_limit: int = 50) -> AsyncGenerator[Track, None]:
        """Generates async interable of :class:`Tracks`s in the :class:`Album`

        example:
        >>> album = await sess.album(180429444)
        >>> [t async for t in album.tracks()]
        [<tidal_async.api.Track (180429445): donGURALesko - Bangladesz>]

        :param per_request_limit: max amount of :class:`Track`s to load in one request
        :yield: :class:`Track`s from :class:`Album`
        """
        async for track in self._iter_coll("tracks", Track, per_request_limit):
            yield track


class Artist(TidalObject, generic.Searchable, generic.ObjectCollection[Album]):
    urlname = "artist"
    apiname = "artists"

    def __repr__(self):
        cls = self.__class__
        return f"<{cls.__module__}.{cls.__qualname__} ({self.get_id()}): {self.name}>"

    @property
    def cover(self) -> Optional[Cover]:
        """
        :return: :class:`Cover` image or `None` if :class:`Artist` has no picture
        """
        return Cover(self.sess, self["picture"]) if self["picture"] is not None else None

    async def albums(self, per_request_limit: int = 10) -> AsyncGenerator[Album, None]:
        """Generates async interable of :class:`Album`s created by the :class:`Artist`

        example:
        >>> artist = await sess.artist(4609597)
        >>> [a async for a in artist.albums()]
        [<tidal_async.api.Album (165409155): Vrony & Pro-Tony>,
         <tidal_async.api.Album (139368091): DZIADZIOR>,
         <tidal_async.api.Album (110742859): Inwazja porywaczy ciał>,
         <tidal_async.api.Album (110742784): Manewry Mixtape>,
         <tidal_async.api.Album (106710978): Miłość, szmaragd i krokodyl>,
         <tidal_async.api.Album (170226527): Latające Ryby>,
         <tidal_async.api.Album (170232018): Dom Otwartych Drzwi>,
         <tidal_async.api.Album (170231954): Drewnianej Małpy Rock>,
         <tidal_async.api.Album (170232038): Magnum Ignotum>,
         <tidal_async.api.Album (170231927): Projekt: Jeden z życia moment>,
         <tidal_async.api.Album (170231872): Opowieści z betonowego lasu>,
         <tidal_async.api.Album (170231895): Zaklinacz Deszczu>,
         <tidal_async.api.Album (170231451): Totem Leśnych Ludzi>,
         <tidal_async.api.Album (170231995): EL POLAKO>]

        :param per_request_limit: max amount of :class:`Album`s to load in one request
        :yield: :class:`Album`s created by the :class:`Artist`
        """
        async for album in self._iter_coll("albums", Album, per_request_limit):
            yield album
