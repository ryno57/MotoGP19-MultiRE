#!/usr/bin/env python3
"""Extract ASCII + UTF-16LE strings from a binary (strings(1) equivalent)."""
import re
import sys
import os

ASCII_RE = re.compile(rb"[\x20-\x7e]{5,}")
UTF16_RE = re.compile(rb"(?:[\x20-\x7e]\x00){5,}")


def extract(path):
    with open(path, "rb") as f:
        data = f.read()
    out = []
    for m in ASCII_RE.finditer(data):
        out.append(m.group().decode("ascii", "replace"))
    for m in UTF16_RE.finditer(data):
        out.append(m.group().decode("utf-16le", "replace"))
    return out


def main():
    if len(sys.argv) < 2:
        print("usage: strings_extract.py <binary> [output.txt]")
        raise SystemExit(1)
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(src)[0] + ".strings.txt"
    lines = extract(src)
    with open(dst, "w", encoding="utf-8", errors="replace") as f:
        f.write("\n".join(lines))
    print(f"{len(lines)} strings -> {dst}")


if __name__ == "__main__":
    main()
