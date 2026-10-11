"""Read-only: does the RA3 UI "can-place" predicate mirror RA1's two-layer
proximity model (footprint clear + adjacency/proximity), and is there a cheap
"skip all rules" branch like RA1's Debug_Map / editor early-out?

Sites: RA3 1.13 UI can-place predicate 0x707880 (the placeui tracer target),
and the region-line predicate 0x5F0930.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_trace_sites import sections  # noqa: E402

IMAGE = Path(r'D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data\ra3_1.13.game')
BASE = 0x400000


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

    for va, n, title in ((0x707880, 0x120, 'UI can-place predicate (placeui)'),
                         (0x70B5F0, 0x80, 'StructurePlacementBehavior vtable[0] target')):
        print(f'\n===== {title} 0x{va:X} =====')
        code = read(blob, secs, va, n)
        if not code:
            print('  not mapped')
            continue
        for ins in md.disasm(code, va):
            print(f'  {ins.address:#010x}  {ins.bytes.hex(" "):<22} {ins.mnemonic} {ins.op_str}')
            if ins.mnemonic.startswith('ret'):
                break


if __name__ == '__main__':
    main()
