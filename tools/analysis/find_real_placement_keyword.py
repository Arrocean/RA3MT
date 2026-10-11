"""Read-only: confirm the grid-cell buildability field and find the real
"placement distance" definition in the shipped data.

1. 0xB322D0 - the per-cell test the buildability query lands in.
2. Search the game's packed XML manifests on disk (BIG4 archives) for
   BuildingPlacementDistance / PlacementDistance / BuildabilityDistance, to see
   whether the live 90.0 is a player placement radius or just AI data.
"""
import re
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


def big_entries(path):
    """Yield (offset, size, name) from a BIG4 archive."""
    with path.open('rb') as f:
        header = f.read(16)
        if header[:4] != b'BIG4':
            return
        count, _ = struct.unpack('>II', header[8:16])
        for _ in range(count):
            offset, size = struct.unpack('>II', f.read(8))
            name = bytearray()
            while True:
                c = f.read(1)
                if c == b'\x00' or not c:
                    break
                name.extend(c)
            yield offset, size, name.decode('ascii', errors='replace')


def main():
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    blob = IMAGE.read_bytes()
    secs = sections(blob)

    print('===== per-cell test 0xB322D0 =====')
    code = read(blob, secs, 0xB322D0, 0x90)
    for ins in md.disasm(code, 0xB322D0):
        print(f'  {ins.address:#010x}  {ins.bytes.hex(" "):<22} {ins.mnemonic} {ins.op_str}')
        if ins.mnemonic.startswith('ret'):
            break

    print('\n===== keyword search in shipped BIG4 archives =====')
    keys = [b'BuildingPlacementDistance', b'PlacementDistance', b'BuildabilityDistance',
            b'ProjectedBuildabilityInfo', b'StructurePlacementBehavior']
    for big in sorted(GAME_DATA.glob('*.big')):
        hits = {}
        try:
            entries = list(big_entries(big))
        except Exception as exc:                       # noqa: BLE001
            print(f'  {big.name}: unreadable ({exc})')
            continue
        if not entries:
            continue
        with big.open('rb') as f:
            for offset, size, name in entries:
                if not name.lower().endswith(('.xml', '.ini', '.manifest')):
                    continue
                if size > 4_000_000:
                    continue
                f.seek(offset)
                data = f.read(size)
                for k in keys:
                    if k in data:
                        hits.setdefault(k.decode(), []).append(name)
        if hits:
            print(f'  {big.name}:')
            for k, names in hits.items():
                print(f'    {k}: {len(names)} file(s) e.g. {names[:4]}')


if __name__ == '__main__':
    main()
