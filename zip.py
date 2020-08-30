from io import RawIOBase


class DebugFile(RawIOBase):
    def __init__(self, name="DebugFile", proxied_file=None, print_write=False, print_read=False, seekable=False):
        self.name = name
        self.print_write = print_write
        self.print_read = print_read
        self.proxied_file = proxied_file
        self._seekable = seekable

        self.written = 0
        self.writes = 0
        self._read = 0
        self.reads = 0
        self.pos = 0

        print(f"{name} CREATED")

    def toggle_print_write(self):
        self.print_write = not self.print_write
        print(f"{self.name} PRINT WRITE: {self.print_write}")

    def toggle_print_read(self):
        self.print_read = not self.print_read
        print(f"{self.name} PRINT READ: {self.print_read}")

    def seekable(self) -> bool:
        return self._seekable

    def seek(self, offset, whence=0):
        if not self.seekable():
            print(f"{self.name} SEEKING TO {offset}, {whence}, OOPS")
            raise OSError
        else:
            print(f"{self.name} SEEKING TO {offset}, {whence}")
            out = self.proxied_file.seek(offset, whence)
            self.pos = out
            return out

    def tell(self):
        n = self.pos
        print(f"{self.name} TELL {n}")
        return n

    def write(self, data):
        n = len(data)
        self.written += n
        self.pos += n
        self.writes += 1
        if self.print_write:
            print(f"{self.name} WRITE {n} B")

        if self.proxied_file is not None:
            return self.proxied_file.write(data)
        else:
            return n

    def read(self, size=-1):
        if self.proxied_file is not None:
            data = self.proxied_file.read(size)
        else:
            raise OSError
        n = len(data)
        self._read += n
        self.pos += n
        self.reads += 1
        if self.print_read:
            print(f"{self.name} READ {n} B")
        return data

    def close(self):
        print(f"{self.name} CLOSING - WRITTEN {self.written} B IN {self.writes} WRITES, READ {self._read} B IN {self.reads} READS")

    def __enter__(self):
        print(f"{self.name} ENTERING")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        print(f"{self.name} EXITING")
        self.close()
