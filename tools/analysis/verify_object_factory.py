"""Disk-only paired Object/Body factory evidence; NOT a callable spawn API resolver.
Requires pefile. Run: py tools/analysis/verify_object_factory.py [game Data directory]
This tool never opens a process or launches the game. No files are extracted/written.
"""
from pathlib import Path
import argparse
import struct
import pefile

DEFAULT = Path(r'D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data')
PAIRS = {
    '1.13': dict(factory=0x102410, allocator=0x3062E0, ctor=0x3EAF30,
                 tag_site=0x3EAF98, tag=0xC57340, component_init=0x3C6400),
    '1.12': dict(factory=0x11A210, allocator=0x31B610, ctor=0x3FFFE0,
                 tag_site=0x400048, tag=0xC54BB0,
                 component_init=0x3DC060),
}


def verify(image, pair):
    start = pair['factory']
    code = bytes(image[start:start + 0x9A])
    def exact(offset, hex_bytes):
        expected = bytes.fromhex(hex_bytes)
        if code[offset:offset + len(expected)] != expected:
            raise ValueError(f'Unexpected instruction at RVA 0x{start + offset:X}')
    def call(offset, target):
        if code[offset] != 0xE8:
            raise ValueError('Expected CALL rel32')
        actual = start + offset + 5 + struct.unpack_from('<i', code, offset + 1)[0]
        if actual != target:
            raise ValueError(f'Unexpected call target 0x{actual:X}')
    exact(0, '56 8B 74 24 08 83 3E 00 75 04 33 C0 5E C3 57 68 FC 04 00 00')
    call(0x14, pair['allocator'])
    exact(0x19, '83 C4 04 85 C0 74 0E 6A 01 56 8B C8')
    call(0x25, pair['ctor'])
    exact(0x2A, '8B F8 EB 02 33 FF 8B B7 10 03 00 00')
    call(0x62, pair['component_init'])
    exact(0x95, '8B C7 5F 5E C3')
    tag = bytes(image[pair['tag_site']:pair['tag_site'] + 7])
    if tag != b'\xC7\x45\x00' + struct.pack('<I', pair['tag']):
        raise ValueError('Unexpected constructor Body tag write')
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('data', nargs='?', type=Path, default=DEFAULT)
    args = parser.parse_args()
    for version, pair in PAIRS.items():
        pe = pefile.PE(str(args.data / f'ra3_{version}.game'))
        image = pe.get_memory_mapped_image()
        verify(image, pair)
        print(f'PASS {version}: factory RVA 0x{pair["factory"]:X}, '
              f'constructor RVA 0x{pair["ctor"]:X}, allocation 0x4FC, Body tag 0x{pair["tag"]:X}')
        # Check independent refusal of all code anchors and each call edge.
        for rva in [pair['factory'] + n for n in (0, 0x15, 0x26, 0x63, 0x95)] + [pair['tag_site'] + 3]:
            changed = bytearray(image)
            changed[rva] ^= 1
            try:
                verify(changed, pair)
            except ValueError:
                pass
            else:
                raise AssertionError(f'Accepted mutated anchor RVA 0x{rva:X}')
        print('PASS six mutated factory/constructor anchors rejected')
    print('Static identity only: request semantics, position, ownership and lifecycle safety remain unverified.')


if __name__ == '__main__':
    main()
