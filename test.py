import asyncio
import sys
from pprint import pprint

from api import TidalSession, AudioQuality, extract_client_id, cli_auth_url_getter


async def main(apk_file):
    async with TidalSession(extract_client_id(apk_file), cli_auth_url_getter) as sess:
        await sess.login()

        # for name, track, region in tracks:
        #     print(f"{name} - INFO")
        #     pprint(await sess.track(track))
        #     print(f"\n{name} - INFO - Region: {region}")
        #     pprint(await sess.track(track, region))
        #     print(f"\n{name} - URL")
        #     pprint(await sess.track_url(track, "PL"))
        #     print(f"\n{name} - URL - Region: {region}")
        #     pprint(await sess.track_url(track, region))
        #     print("\n")

        album = await sess.album(22563744)
        pprint(album.dict)
        print()
        tracks = await album.tracks()
        pprint([t.dict for t in tracks])
        print()
        pprint([await t.stream_url(audio_quality=AudioQuality.Master) for t in tracks])
        print()
        pprint([(t.title, t.audio_quality) for t in tracks])


if __name__ == '__main__':
    asyncio.get_event_loop().run_until_complete(main(sys.argv[1]))
