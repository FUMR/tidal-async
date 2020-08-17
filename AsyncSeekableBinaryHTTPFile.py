import cgi

import aiohttp

# TODO: fallback file name from url


class AsyncSeekableBinaryHTTPFile(object):
    # https://github.com/JuniorJPDJ/pyChomikBox/blob/master/ChomikBox/utils/SeekableHTTPFile.py
    def __init__(self, url, name, aiohttp_session, timeout):
        # DON'T USE THIS DIRECTLY, USE .create()
        self.url = url
        self.sess = aiohttp.ClientSession() if aiohttp_session is None else aiohttp_session
        self._local_session = aiohttp_session is None
        self._seekable = False
        self.timeout = timeout
        self._init_called = False
        self.name = name
        self.len = None
        self.closed = True

        self._pos = 0
        self._r = None

    @classmethod
    async def create(cls, url, name=None, aiohttp_session=None, timeout=30):
        self = cls(url, name, aiohttp_session, timeout)

        f = await self.sess.head(self.url, headers={'Range': 'bytes=0-'}, timeout=self.timeout)
        if (f.status == 206 and 'Content-Range' in f.headers) or (f.status == 200 and 'Accept-Ranges' in f.headers):
            self._seekable = True
        self.len = int(f.headers["Content-Length"])
        if self.name is None:
            if "Content-Disposition" in f.headers:
                value, params = cgi.parse_header(f.headers["Content-Disposition"])
                if "filename" in params:
                    self.name = params["filename"]
        await f.release()

        self.closed = False

        return self

    async def seekable(self):
        return self._seekable

    def __len__(self):
        return self.len

    async def tell(self):
        return self._pos

    async def readable(self):
        return not self.closed

    async def writable(self):
        return False

    async def _reopen_stream(self):
        if self._r is not None:
            await self._r.release()
        if self._seekable:
            self._r = await self.sess.get(self.url, headers={'Range': 'bytes={}-'.format(self._pos)}, timeout=30)
        else:
            self._pos = 0
            self._r = await self.sess.get(self.url, timeout=self.timeout)

    async def seek(self, offset, whence=0):
        if not await self.seekable():
            raise OSError
        if whence == 0:
            self._pos = 0
        elif whence == 1:
            pass
        elif whence == 2:
            self._pos = self.len
        self._pos += offset
        await self._r.release()
        return self._pos

    async def read(self, amount=-1):
        if not await self.readable():
            raise OSError
        if self._r is None or self._r.closed:  # or self._r.raw.closed:
            await self._reopen_stream()
        if amount < 0:
            content = await self._r.content.read()
        else:
            content = await self._r.content.read(amount)
        self._pos += len(content)
        return content

    async def write(self, *args, **kwargs):
        raise OSError

    async def close(self):
        await self._r.release()
        if self._local_session:
            await self.sess.close()
        self.closed = True
