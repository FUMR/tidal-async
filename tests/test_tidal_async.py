import asyncio
import os

import pytest

from tidal_async import TidalSession

# TODO [#19]: Unit tests!
#   - [_] login process (not sure how to do this - it's interactive oauth2)
#   - [x] session refreshing
#   - [x] loading track info
#   - [_] downloading tracks
#   - [_] track lyrics
#   - [_] track metadata generation
#   - [_] loading album info
#   - [_] listing tracks from albums
#   - [_] loading playlist info
#   - [_] listing tracks from playlists
#   - [_] loading artists (first we need artists)
#   - [_] listing albums from artists
#   - [_] loading cover arts
#   - [_] parsing URLs
#   - [_] searching (first we need search)
#   - [_] extracting client_id from Tidal Android `.apk`


@pytest.fixture(scope="module")
def event_loop():
    # needed to redefine scope
    loop = asyncio.get_event_loop()
    yield loop
    loop.close()


@pytest.mark.asyncio
@pytest.fixture(scope="module")
async def sess():
    client_id = os.getenv("TIDAL_CLIENT_ID")
    async with TidalSession(client_id) as sess:
        sess._refresh_token = os.getenv("TIDAL_REFRESH_TOKEN")
        yield sess


@pytest.mark.asyncio
async def test_session_refresh(sess: TidalSession):
    await sess.refresh_session()


@pytest.mark.asyncio
async def test_track_info(sess: TidalSession):
    track = await sess.track(79580198)
    assert track.title == "Dogs Like Socks"
