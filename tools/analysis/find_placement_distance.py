"""Locate BuildingPlacementDistance in the compiled INI manifests (BIG archives)
and report its default value / context. Disk-only; no game process involved.
Run: py tools/analysis/find_placement_distance.py
"""
import re
import struct
from pathlib import Path

DEFAULT = Path(r'D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data')


def read_big_entry(path: Path, wanted: str):
    with path.open('rb') as f:
        header = f.read(16)
        if header[:4] != b'BIG4':
            return None
        count, _ = struct.unpack('>II', header[8:16])
        for _ in range(count):
            offset, size = struct.unpack('>II', f.read(8))
            name = bytearray()
            while True:
                c = f.read(1)
                if c == b'\x00':
                    break
                name.extend(c)
            normalized = name.decode('ascii', errors='replace').replace('\\', '/').lower()
            if normalized == wanted.lower():
                f.seek(offset)
                return f.read(size)
        return None


def main():
    for big_name in ('Core5.big', 'Core6.big', 'Core7.big', 'Core8.big', 'Core9.big',
                     'Core10.big', 'Core11.big', 'Core12.big', 'Misc.big', 'GlobalStream.big'):
        big = DEFAULT / big_name
        if not big.exists():
            continue
        with big.open('rb') as f:
            header = f.read(16)
            if header[:4] != b'BIG4':
                continue
            count, _ = struct.unpack('>II', header[8:16])
            entries = []
            for _ in range(count):
                offset, size = struct.unpack('>II', f.read(8))
                name = bytearray()
                while True:
                    c = f.read(1)
                    if c == b'\x00':
                        break
                    name.extend(c)
                entries.append((offset, size, name.decode('ascii', errors='replace')))
        for offset, size, name in entries:
            if not name.lower().endswith(('.manifest', '.ini')):
                continue
            with big.open('rb') as f:
                f.seek(offset)
                blob = f.read(size)
            idx = blob.find(b'BuildingPlacementDistance')
            if idx < 0:
                continue
            print(f'== {big_name} :: {name} (0x{offset:X}, {size}B) hit at +0x{idx:X}')
            s = max(0, idx - 240)
            chunk = blob[s:idx + 400]
            text = re.sub(rb'[^\x20-\x7e]', b'.', chunk).decode()
            print(text)
            print()


if __name__ == '__main__':
    main()
