import mutagen
from mutagen import id3
from mutagen.flac import Picture, FLAC
from mutagen.id3 import APIC

import tidal_async
from zip import DebugFile

with open('tmp/test.flac', 'rb') as in_f, open('tmp/outf.flac', 'wb') as out_f:
    while data := in_f.read(128*1024):
        out_f.write(data)

with open('tmp/outf.flac', 'rb+') as f:
    # name="DebugFile", proxied_file=None, print_write=False, print_read=False, seekable=False
    df = DebugFile(proxied_file=f, seekable=True, print_read=True, print_write=True)

    print("creating flac file")
    track = FLAC(df)

    print('<tag>')
    track['artist'] = "Twoja matka"
    track['title'] = "Sextapekurwa"
    print('</tags>')

    # cover_size = (640, 640)

    # # download album cover
    # if isinstance(track, FLAC):
    #     pic = Picture()
    #     pic.width, pic.height = cover_size
    # else:
    #     pic = APIC()
    # pic.type = id3.PictureType.COVER_FRONT
    # pic.mime = "image/jpeg"
    # pic.data = await (await track.cover.get_async_file(size=cover_size)).read()

    # track.add_picture(pic)

    print("saving flac")
    df.seek(0)
    track.save(df, padding=lambda info: 0)
