import hashlib
import os

import pytest

from tidal_async import Album, AudioQuality, Playlist, TidalSession, Track, extract_client_id

# TODO [#19]: Unit tests!
#   - [_] login process (not sure how to do this - it's interactive oauth2)
#   - [x] session refreshing
#   - [x] loading track info
#   - [x] downloading tracks
#   - [_] track lyrics
#   - [_] track metadata generation
#   - [x] loading album info
#   - [x] listing tracks from albums
#   - [x] loading playlist info
#   - [x] listing tracks from playlists
#   - [_] loading artists (first we need artists)
#   - [_] listing albums from artists
#   - [_] loading cover arts
#   - [x] parsing URLs
#   - [_] searching (first we need search)
#   - [x] extracting client_id from Tidal Android `.apk`
#   - [_] TidalMultiSession tests (what kind of?)


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
    "id_, title",
    (
        (79580198, "Dogs Like Socks"),
        (22563749, "Own It"),
    ),
)
async def test_track_title(sess: TidalSession, id_, title):
    track = await sess.track(id_)
    assert track.title == title


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "id_, title",
    (
        (91969976, "Do"),
        (22563744, "Nothing Was The Same"),
    ),
)
async def test_album_title(sess: TidalSession, id_, title):
    album = await sess.album(id_)
    assert album.title == title


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
    "url_string, out_types, out_ids",
    (
        # just empty string
        ("", (), ()),
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
    assert [(obj.__class__, obj.id) async for obj in sess.parse_urls(url_string)] == list(zip(out_types, out_ids))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "id_, quality, sha256sum",
    (
        (22563745, AudioQuality.HiFi, "1bc70dd10381db1a6f7484f3b5e7e1e207bbfd70e31c42c437c88f82a752c26d"),
        (22563746, AudioQuality.HiFi, "6e7aceef2f8642a5a05b1d3d70d7ec5d7182b617abda5c35613611754d31ff81"),
    ),
)
async def test_track_download(sess: TidalSession, id_, quality, sha256sum):
    sha256 = hashlib.sha256()
    track = await sess.track(id_)
    file = await track.get_async_file(audio_quality=quality)
    async with file:
        while data := await file.read(128 * 1024):  # 128kB chunk size
            sha256.update(data)

    assert sha256.hexdigest() == sha256sum


@pytest.mark.asyncio
async def test_client_id_extraction():
    from io import BytesIO

    import aiohttp

    apk_file = BytesIO()

    async with aiohttp.ClientSession() as session:
        async with session.get(os.getenv("TIDAL_APK_URL")) as resp:
            while data := await resp.content.read(128 * 1024):  # 128kB chunk size
                apk_file.write(data)

    apk_file.seek(0)

    assert extract_client_id(apk_file) == os.getenv("TIDAL_CLIENT_ID")
