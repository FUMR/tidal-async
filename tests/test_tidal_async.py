import asyncio
import os

import pytest

from tidal_async import Album, Playlist, TidalSession, Track

# TODO [#19]: Unit tests!
#   - [_] login process (not sure how to do this - it's interactive oauth2)
#   - [x] session refreshing
#   - [x] loading track info
#   - [_] downloading tracks
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
#   - [_] extracting client_id from Tidal Android `.apk`


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
