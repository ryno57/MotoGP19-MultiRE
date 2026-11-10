#!/usr/bin/env python3
"""Minimal UE4 .pak reader (versions 4-8 compatible enough for UE4.22).

Usage:
  python pak.py list <pak> [filter]
  python pak.py extract <pak> <entry-name> <outfile>
"""
import struct
import sys
import os

MAGIC = 0x5A6F12E1


class Reader:
    def __init__(self, data, pos=0):
        self.d = data
        self.p = pos

    def u8(self):
        v = self.d[self.p]
        self.p += 1
        return v

    def i32(self):
        v = struct.unpack_from("<i", self.d, self.p)[0]
        self.p += 4
        return v

    def u32(self):
        v = struct.unpack_from("<I", self.d, self.p)[0]
        self.p += 4
        return v

    def i64(self):
        v = struct.unpack_from("<q", self.d, self.p)[0]
        self.p += 8
        return v

    def skip(self, n):
        self.p += n

    def fstring(self):
        n = self.i32()
        if n == 0:
            return ""
        if n > 0:
            raw = self.d[self.p:self.p + n]
            self.p += n
            s = raw.decode("latin-1").rstrip("\x00")
        else:
            n = -n
            raw = self.d[self.p:self.p + n * 2]
            self.p += n * 2
            s = raw.decode("utf-16le").rstrip("\x00")
        return s


def read_footer(f, size):
    f.seek(max(0, size - 512))
    tail = f.read()
    idx = tail.rfind(struct.pack("<I", MAGIC))
    if idx < 0:
        raise SystemExit("pak magic not found")
    base = size - len(tail) + idx
    r = Reader(tail, idx)
    magic = r.u32()
    version = r.i32()
    index_off = r.i64()
    index_size = r.i64()
    r.skip(20)  # hash
    encrypted_index = False
    guid = None
    # Some UE4.22 builds use a 44-byte footer (no flags after the hash).
    if version >= 4 and r.p < len(r.d):
        encrypted_index = bool(r.u8())
    if version >= 7 and r.p + 16 <= len(r.d):
        guid = r.d[r.p:r.p + 16].hex()
    return version, index_off, index_size, encrypted_index, guid


def parse_index(data, version):
    r = Reader(data)
    mount = r.fstring()
    count = r.i32()
    entries = []
    for _ in range(count):
        try:
            name = r.fstring()
            offset = r.i64()
            size = r.i64()
            uncompressed = r.i64()
            method = r.u32()
            r.skip(20)  # sha1
            blocks = []
            block_size = 0
            encrypted = 0
            if version >= 3:
                nb = r.i32()
                for _ in range(nb):
                    bs = r.i64()
                    be = r.i64()
                    blocks.append((bs, be))
                if method != 0:
                    block_size = r.u32()
                encrypted = r.u8()
        except (struct.error, IndexError):
            print(f"# warning: index parse stopped after {len(entries)} entries", file=sys.stderr)
            break
        entries.append({
            "name": name, "offset": offset, "size": size,
            "uncompressed": uncompressed, "blocks": blocks,
            "block_size": block_size, "encrypted": bool(encrypted),
            "method": method,
        })
    return mount, entries


def load_index(path):
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        version, index_off, index_size, enc, guid = read_footer(f, size)
        if enc:
            raise SystemExit("index is AES-encrypted; key required")
        f.seek(index_off)
        data = f.read(index_size)
    return version, parse_index(data, version), guid


def decompress_entry(pak, entry):
    import zlib
    with open(pak, "rb") as f:
        if entry["method"] == 0:
            f.seek(entry["offset"])
            return f.read(entry["size"])
        f.seek(entry["offset"] + entry["blocks"][0][0])
        out = bytearray()
        for bs, be in entry["blocks"]:
            f.seek(entry["offset"] + bs)
            raw = f.read(be - bs)
            out += zlib.decompress(raw)
    return bytes(out)


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        raise SystemExit(1)
    cmd = sys.argv[1]
    pak = sys.argv[2]
    version, (mount, entries), guid = load_index(pak)
    if cmd == "list":
        flt = sys.argv[3].lower() if len(sys.argv) > 3 else ""
        print(f"# pak v{version} mount={mount!r} entries={len(entries)} guid={guid}")
        for e in entries:
            if flt in e["name"].lower():
                print(f"{e['size']:>12} {e['uncompressed']:>12} m{e['method']} {e['name']}")
    elif cmd == "extract":
        name = sys.argv[3]
        out = sys.argv[4]
        match = [e for e in entries if e["name"].lower() == name.lower()
                 or e["name"].lower().endswith("/" + name.lower())]
        if not match:
            raise SystemExit("entry not found")
        e = match[0]
        raw = decompress_entry(pak, e)
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        with open(out, "wb") as f:
            f.write(raw)
        print(f"wrote {out} ({len(raw)} bytes, method {e['method']})")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
