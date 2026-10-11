"""Read-only: find the REAL buildability gate.

Facts so far: the manager box (vt+0x38) is a single 5000x5600 rectangle = world
bounds, NOT the local buildable area. ProjectedBuildabilityInfo is a *circle*
(Radius=600 on a ConYard). So percell's AABB is a coarse world-bounds reject and
the real test must be a finer one on the PASS path:

  percell PASS 0xA2A2A6 -> [0xCF214C] -> 0x8627D0 (body+0x28)
              -> [0xCEC450] -> 0xB34740 -> jmp 0xB336E0

Dump 0xB336E0 and look for distance/radius comparisons and any loop over
buildability regions; also identify the helper 0xB32360.
"""
import struct
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

    for va, n, title in ((0xB32360, 0x80, 'helper 0xB32360 (distance?)'),
                         (0xB336E0, 0x220, 'buildability query 0xB336E0')):
        print(f'\n===== {title} =====')
        code = read(blob, secs, va, n)
        if not code:
            print('  not mapped')
            continue
        for ins in md.disasm(code, va):
            note = ''
            if ins.mnemonic.startswith(('comiss', 'ucomiss', 'mulss', 'addss', 'subss')):
                note = '   <<< float math'
            if ins.mnemonic in ('fcomp', 'fcompp', 'fcom'):
                note = '   <<< x87 compare'
            print(f'  {ins.address:#010x}  {ins.bytes.hex(" "):<22} {ins.mnemonic} {ins.op_str}{note}')
            if ins.mnemonic.startswith('ret') and ins.address > va:
                break


if __name__ == '__main__':
    main()
