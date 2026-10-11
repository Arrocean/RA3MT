"""Verify FINAL3 spawn identifiers from the installed BIG4 hash-table asset.
Disk-only; no native APIs, process discovery, game writes or archive extraction.
Run: py tools/analysis/verify_spawn_hashes.py [path/to/WBStringHashes.big]
"""
from pathlib import Path
import argparse
import struct
import xml.etree.ElementTree as ET

EXPECTED = {0x28DA574E: 'AlliedMCV', 0xAF4C0DA5: 'SovietMCV',
            0x1C2EF767: 'JapanMCV', 0x6586A5A0: 'JapanCommandoTech1'}
DEFAULT = Path(r'D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data\WBStringHashes.big')


def read_entry(path, wanted):
    with path.open('rb') as f:
        header = f.read(16)
        if len(header) != 16 or header[:4] != b'BIG4':
            raise ValueError('Expected BIG4 archive')
        count, index_end = struct.unpack('>II', header[8:16])
        file_size = path.stat().st_size
        if count > 1000000 or not 16 <= index_end <= file_size:
            raise ValueError('Invalid archive index limits')
        matches = []
        for _ in range(count):
            pair = f.read(8)
            if len(pair) != 8:
                raise ValueError('Truncated entry')
            offset, size = struct.unpack('>II', pair)
            name = bytearray()
            while True:
                char = f.read(1)
                if not char or f.tell() > index_end or len(name) > 4096:
                    raise ValueError('Invalid archive filename')
                if char == b'\0':
                    break
                name.extend(char)
            if offset + size > file_size:
                raise ValueError('Entry exceeds archive')
            if name.decode('ascii').replace('\\', '/').lower() == wanted.lower():
                matches.append((offset, size))
        if len(matches) != 1:
            raise ValueError('Expected exactly one hash-table entry')
        offset, size = matches[0]
        if offset < index_end or size > 64 * 1024 * 1024:
            raise ValueError('Unsafe hash-table bounds')
        f.seek(offset)
        data = f.read(size)
        if len(data) != size:
            raise ValueError('Truncated payload')
        return offset, size, data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', nargs='?', type=Path, default=DEFAULT)
    args = parser.parse_args()
    offset, size, data = read_entry(args.archive, 'data/stringhashes.xml')
    root = ET.fromstring(data)
    found = {key: set() for key in EXPECTED}
    counts = dict.fromkeys(EXPECTED, 0)
    for node in root.iter():
        if node.tag.rsplit('}', 1)[-1] != 'StringAndHash':
            continue
        value = int(node.attrib['Hash'])
        if value in found:
            found[value].add(node.attrib['Text'])
            counts[value] += 1
    print(f'BIG4 XML offset=0x{offset:X} size={size}; disk-only identifier evidence')
    for value, name in EXPECTED.items():
        if found[value] != {name}:
            raise ValueError(f'Hash 0x{value:08X} missing or ambiguous: {found[value]}')
        print(f'PASS 0x{value:08X} = {name} ({counts[value]} records)')
    print('Does not verify CreateUnit ABI, ownership, coordinates or gameplay effects.')


if __name__ == '__main__':
    main()
