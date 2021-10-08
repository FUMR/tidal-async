import hashlib
import os
from typing import Optional, Sized

import mpegdash
import pytest

from tidal_async import (
    Album,
    Artist,
    AudioQuality,
    Playlist,
    TidalSession,
    Track,
    dash_mpd_from_data_url,
    extract_client_id,
)

# TODO [#63]: Unit tests!
#   - [ ] login process (not sure how to do this - it's interactive oauth2)
#   - [x] session refreshing
#   - [ ] Track
#       - [x] loading track info
#       - [x] downloading tracks
#       - [x] track lyrics
#       - [ ] track metadata generation
#   - [x] loading album info
#       - [x] listing tracks from albums
#   - [x] loading playlist info
#       - [x] listing tracks from playlists
#   - [x] loading artists
#       - [x] listing albums from artists
#   - [x] loading cover arts
#   - [x] parsing URLs
#   - [x] searching
#   - [x] extracting client_id from Tidal Android `.apk`
#   - [ ] TidalMultiSession tests (what kind of?)
#   - [x] caching TidalObject creation
#       - [x] caching of tracks
#       - [x] caching of albums
#       - [x] caching of playlists
#       - [x] caching of artists


@pytest.mark.asyncio
async def test_refresh_session():
    client_id = os.getenv("TIDAL_CLIENT_ID")
    async with TidalSession(client_id) as sess:
        sess._refresh_token = os.getenv("TIDAL_REFRESH_TOKEN")
        await sess.refresh_session()


@pytest.mark.asyncio
@pytest.fixture()
async def sess():
    client_id = os.getenv("TIDAL_CLIENT_ID")
    async with TidalSession(client_id) as sess:
        sess._refresh_token = os.getenv("TIDAL_REFRESH_TOKEN")
        await sess.refresh_session()
        yield sess


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "id_, artist, title",
    (
        (79580198, "Psychostick", "Dogs Like Socks"),
        (22563749, "Drake", "Own It"),
    ),
)
async def test_track_title(sess: TidalSession, id_, artist, title):
    track = await sess.track(id_)
    assert track.title == title and track.artist_name == artist


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "id_, lyrics_len",
    (
        (6758222, None),
        (22563746, 3079),
    ),
)
async def test_track_lyrics(sess: TidalSession, id_, lyrics_len):
    track = await sess.track(id_)
    lyrics = await track.lyrics()
    if lyrics is None:
        assert lyrics_len == lyrics
    else:
        assert len(lyrics) == lyrics_len


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "id_, subtitles_len",
    (
        (6758222, None),
        (22563746, 4181),
    ),
)
async def test_track_subtitles(sess: TidalSession, id_, subtitles_len):
    track = await sess.track(id_)
    subtitles = await track.subtitles()
    if subtitles is None:
        assert subtitles_len == subtitles
    else:
        assert len(subtitles) == subtitles_len


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "id_, artist, title",
    (
        (91969976, "Psychostick", "Do"),
        (22563744, "Drake", "Nothing Was The Same"),
    ),
)
async def test_album_title(sess: TidalSession, id_, artist, title):
    album = await sess.album(id_)
    assert album.title == title and album.artist_name == artist


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "id_, limit, first_title, last_title",
    (
        (91969976, 10, "We Are a Band", "Flop"),
        (22563744, 5, "Tuscan Leather", "Pound Cake / Paris Morton Music 2"),
    ),
)
async def test_album_tracks(sess: TidalSession, id_, limit, first_title, last_title):
    album = await sess.album(id_)
    tracks = [track async for track in album.tracks(per_request_limit=limit)]
    assert tracks[0].title == first_title
    assert tracks[-1].title == last_title


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "id_, title",
    (("dcbab999-7523-4e2f-adf4-57d10fc17516", "Soundtracking: Need for Speed"),),
)
async def test_playlist_title(sess: TidalSession, id_, title):
    playlist = await sess.playlist(id_)
    assert playlist.title == title


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "id_, limit, first_title, last_title",
    (("dcbab999-7523-4e2f-adf4-57d10fc17516", 50, "Joker And The Thief", "Watch My Feet"),),
)
async def test_playlist_tracks(sess: TidalSession, id_, limit, first_title, last_title):
    playlist = await sess.playlist(id_)
    tracks = [track async for track in playlist.tracks(per_request_limit=limit)]
    assert tracks[0].title == first_title
    assert tracks[-1].title == last_title


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "id_, name",
    (("12832", "Scorpions"),),
)
async def test_artist_name(sess: TidalSession, id_, name):
    artist = await sess.artist(id_)
    assert artist.name == name


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "id_, limit, first_title, last_title",
    (("12832", 10, "Born To Touch Your Feelings - Best of Rock Ballads", "Fly To The Rainbow"),),
)
async def test_artist_albums(sess: TidalSession, id_, limit, first_title, last_title):
    artist = await sess.artist(id_)
    albums = [album async for album in artist.albums(per_request_limit=limit)]
    assert albums[0].title == first_title
    assert albums[-1].title == last_title


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url_string, out_types, out_ids",
    (
        # just empty string
        ("", (), ()),
        # tidal url not pointing to any object
        ("https://offer.tidal.com/campaigns/5ced61f174bf330018621c43/products", (), ()),
        # just one url and nothing else
        ("http://www.tidal.com/track/50096997", (Track,), (50096997,)),
        ("http://www.tidal.com/album/139475048", (Album,), (139475048,)),
        ("https://listen.tidal.com/album/152676381", (Album,), (152676381,)),
        ("https://tidal.com/album/139475048", (Album,), (139475048,)),
        (
            "http://www.tidal.com/playlist/dcbab999-7523-4e2f-adf4-57d10fc17516",
            (Playlist,),
            ("dcbab999-7523-4e2f-adf4-57d10fc17516",),
        ),
        ("https://listen.tidal.com/album/110359322/track/110359323", (Track,), (110359323,)),
        ("https://listen.tidal.com/artist/12832", (Artist,), (12832,)),
        # text sent by Android app when sharing track
        (
            "Check out this track on TIDAL"
            ': "PATOINTELIGENCJA (REMIX ZAJEBI$TY)" by WIXAPOL, '
            "Mata https://tidal.com/track/150525636",
            (Track,),
            (150525636,),
        ),
        # multiple links with whitespaces between them
        (
            "http://www.tidal.com/track/50096997"
            " http://www.tidal.com/album/139475048\n"
            "http://www.tidal.com/track/50096997",
            (Track, Album, Track),
            (50096997, 139475048, 50096997),
        ),
        # Someone has other ideas?
    ),
)
async def test_url_parsing(sess: TidalSession, url_string, out_types, out_ids):
    assert [(obj.__class__, obj.get_id()) async for obj in sess.parse_urls(url_string)] == list(zip(out_types, out_ids))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    (
        "http://www.tidal.com/track/50096997",
        "http://www.tidal.com/album/139475048",
        "http://www.tidal.com/playlist/dcbab999-7523-4e2f-adf4-57d10fc17516",
        "https://listen.tidal.com/artist/12832",
    ),
)
async def test_object_cache(sess: TidalSession, url):
    obj1 = await sess.object_from_url(url)
    obj2 = await sess.object_from_url(url)
    assert obj1 is obj2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query, type, result_repr",
    (
        (
            "kek",
            Track,
            "<tidal_async.api.Track (118769589): Pezet, Paluch, KęKę, Sokół, Ten Typ Mes - Gorzka woda (prod. Auer) (Remix)>",
        ),
        ("dongural", Artist, "<tidal_async.api.Artist (4609597): donGURALesko>"),
        (
            "need for speed",
            Playlist,
            "<tidal_async.api.Playlist (dcbab999-7523-4e2f-adf4-57d10fc17516): Soundtracking: Need for Speed>",
        ),
        ("magnum ig", Album, "<tidal_async.api.Album (170232038): Magnum Ignotum>"),
    ),
)
async def test_search(sess: TidalSession, query, type, result_repr):
    assert repr(await sess.search(query, type, 1).__anext__()) == result_repr


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "object_url, cover_size, sha256sum",
    (
        (
            "http://www.tidal.com/track/50096997",
            (640, 640),
            "5c3b712621d6b3feb00ca0a4cab78b589dae63a1ab9a75c8c29618f0f94fa1f1",
        ),
        (
            "http://www.tidal.com/album/139475048",
            (320, 320),
            "d6fe27022ee874bb07527aac70b0ce34eab6f014d5d9e34b3803df074a79e5de",
        ),
        ("http://www.tidal.com/track/82804684", (1280, 1280), None),
    ),
)
async def test_cover_download(sess: TidalSession, object_url, cover_size, sha256sum):
    cover = (await sess.object_from_url(object_url)).cover

    if sha256sum is None:
        assert cover is None
        return

    file = await cover.get_async_file(size=cover_size)
    async with file:
        assert hashlib.sha256(await file.read()).hexdigest() == sha256sum


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "id_, required_quality, preferred_quality, file_size, mimetype, etag",
    (
        (
            152676390,
            AudioQuality.Master,
            AudioQuality.Master,
            57347313,
            "audio/flac",
            '"3bb27f3e6d8f7fd987bcc0d3cdc7c452"',
        ),
    ),
)
async def test_track_download_direct(
    sess: TidalSession, id_, required_quality, preferred_quality, file_size, mimetype, etag
):
    track = await sess.track(id_)
    file = await track.get_async_file(required_quality, preferred_quality)

    assert file.mimetype == mimetype and file.resp_headers["ETag"] == etag and len(file) == file_size


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "id_, required_quality, preferred_quality, codec, bandwidth, length, segments",
    (
        (
            152676390,
            AudioQuality.Normal,
            AudioQuality.Normal,
            "mp4a.40.5",
            96984,
            "PT4M17.614S",
            64,
        ),
        (
            152676390,
            AudioQuality.High,
            AudioQuality.High,
            "mp4a.40.2",
            321691,
            "PT4M17.545S",
            64,
        ),
        (
            152676390,
            AudioQuality.HiFi,
            AudioQuality.HiFi,
            "flac",
            957766,
            "PT4M17.499S",
            64,
        ),
    ),
)
async def test_track_download_dash(
    sess: TidalSession, id_, required_quality, preferred_quality, codec, bandwidth, length, segments
):
    track = await sess.track(id_)
    url = await track.get_file_url(required_quality, preferred_quality)
    mpd = dash_mpd_from_data_url(url)

    rep = mpd.periods[0].adaptation_sets[0].representations[0]

    assert rep.codecs == codec
    assert rep.bandwidth == bandwidth
    assert mpd.media_presentation_duration == length
    assert sum(s.r if s.r else 1 for s in rep.segment_templates[0].segment_timelines[0].Ss)


@pytest.mark.asyncio
async def test_client_id_extraction():
    from io import BytesIO

    import aiohttp

    apk_file = BytesIO()

    async with aiohttp.ClientSession() as session:
        async with session.get(os.getenv("TIDAL_APK_URL")) as resp:
            data = await resp.content.read(128 * 1024)  # 128kB chunk size
            while data:
                apk_file.write(data)
                data = await resp.content.read(128 * 1024)

    apk_file.seek(0)

    assert extract_client_id(apk_file) == os.getenv("TIDAL_CLIENT_ID")
