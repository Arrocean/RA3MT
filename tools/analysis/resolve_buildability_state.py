"""Read-only follow-ups:
1. full disassembly of the grid-cell buildability test 0xB322D0 and its wrapper
   0xB336E0 - what do return values 1/2/3 mean and which block placement?
2. keyword search restricted to likely archives (Core*/static manifests) with a
   visible progress line per archive.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_trace_sites import sections  # noqa: E402

IMAGE = Path(r'D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data\ra3_1.13.game')
BASE = 0x400000
GAME_DATA = Path(r'D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data')


def read(blob, secs, va, n):
    rva = va - BASE
    for name, sva, vs, raw, rs in secs:
        if sva <= rva < sva + max(vs, rs):
            return blob[raw + (rva - sva): raw + (rva - sva) + n]
    return None


def main():
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    blob = IMAGE.read_bytes()
    secs = sections(blob)

    for va, n, title in ((0xB322D0, 0x140, 'grid-cell buildability test'),
                         (0x5F09A0, 0x60, 'the vf called with the cell (context)')):
        print(f'\n===== {title} 0x{va:X} =====')
        code = read(blob, secs, va, n)
        if not code:
            print('  not mapped')
            continue
        for ins in md.disasm(code, va):
            print(f'  {ins.address:#010x}  {ins.bytes.hex(" "):<22} {ins.mnemonic} {ins.op_str}')
            if ins.mnemonic.startswith('ret'):
                break

    print('\n===== keyword search (Core*.big / static manifests only) =====')
    keys = (b'BuildingPlacementDistance', b'BuildabilityDistance',
            b'ProjectedBuildabilityInfo')
    for big in sorted(GAME_DATA.glob('Core*.big')):
        try:
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
                        if c == b'\x00' or not c:
                            break
                        name.extend(c)
                    entries.append((offset, size, name.decode('ascii', errors='replace')))
                found = {}
                for offset, size, name in entries:
                    if not name.lower().endswith(('.manifest', '.ini')):
                        continue
                    if size > 8_000_000:
                        continue
                    f.seek(offset)
                    data = f.read(size)
                    for k in keys:
                        if k in data:
                            found.setdefault(k.decode(), []).append((name, size))
                if found:
                    print(f'  {big.name} ({len(entries)} entries):')
                    for k, v in found.items():
                        print(f'    {k}: {len(v)} -> {v[:3]}')
                else:
                    print(f'  {big.name}: no hits ({len(entries)} entries scanned)')
        except Exception as exc:                       # noqa: BLE001
            print(f'  {big.name}: ERROR {exc}')


if __name__ == '__main__':
    main()
