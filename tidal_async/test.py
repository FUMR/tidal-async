import asyncio
import sys
from zipfile import ZipFile

from tidal_async import TidalSession, extract_client_id, cli_auth_url_getter
from zip import DebugFile


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
        fname = lambda t: f"{t.track_number:02d}. {t.title}.flac".replace('/', '|').replace('\\', '|')
        files = (await t.get_async_file(filename=fname) for t in await album.tracks())
        coversizes = len(await album.cover.get_async_file()) * len(await album.tracks())

        # zip file overhead
        # per file
        #     30 + len(filename) (file header)
        #     file
        #     16
        #
        # footer
        #     per file
        #         46 (central directory)
        #         len(filename)
        #         0 (extra data)
        #         0 (comment)
        #     22 (end-of-zip-archive record)
        #     0 (eoz comment)
        #
        # sum(30 + 16 + 46 + 2*len(f.name) for f in files) + 22
        zip_data = 22

        filesizes = 0

        chunk_size = 128*1024  # 128kB
        with open('tmp/wtf.zip', 'wb') as outf:
            nf = DebugFile(proxied_file=outf)
            nf.toggle_print_write()
            with ZipFile(nf, 'w', allowZip64=False) as zipf:
                async for f in files:
                    filesizes += len(f)
                    zip_data += 30 + 16 + 46 + 2 * len(f.name)
                    with zipf.open(f.name, mode='w') as fz:
                        print(f.name)
                        nf.toggle_print_write()
                        async with f:
                            while data := await f.read(chunk_size):
                                fz.write(data)
                        nf.toggle_print_write()
                zipf.comment = b'\0'*65535

        print(f"calculated zip data: {zip_data}")
        print(f"audio files: {filesizes} B")
        print(f"cover files: {coversizes} B")

        # pprint(album.dict)
        # print()
        # tracks = await album.tracks()
        # pprint([t.dict for t in tracks])
        # print()
        # pprint([await t.stream_url(audio_quality=AudioQuality.Master) for t in tracks])
        # print()
        # pprint([(t.title, t.audio_quality) for t in tracks])


if __name__ == '__main__':
    asyncio.get_event_loop().run_until_complete(main(sys.argv[1]))
