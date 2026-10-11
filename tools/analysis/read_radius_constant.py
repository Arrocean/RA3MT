"""Read-only: the placement radius constant.

0x70FB20 computes dx*dx + dz*dz and compares it against the float at
0xC26114 (VA) / 0xC26114-0x400000 = 0x826114 (RVA). Identify that constant,
and disassemble the compare/jump so we know the exact branch to patch.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_trace_sites import sections  # noqa: E402

IMAGE = Path(r'D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data\ra3_1.13.game')
IMAGE_112 = Path(r'D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data\ra3_1.12.game')
BASE = 0x400000
CONST_VA = 0xC26114


def read(blob, secs, va, n):
    rva = va - BASE
    for name, sva, vs, raw, rs in secs:
        if sva <= rva < sva + max(vs, rs):
            return blob[raw + (rva - sva): raw + (rva - sva) + n]
    return None


def main():
    blob = IMAGE.read_bytes()
    secs = sections(blob)
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)

    raw = read(blob, secs, CONST_VA, 4)
    f = struct.unpack('<f', raw)[0]
    print(f'constant at 0x{CONST_VA:X} = {raw.hex(" ")} = {f}   '
          f'(squared -> radius {f ** 0.5:.3f})')

    print('\n===== .rdata neighbourhood =====')
    for k in range(-3, 6):
        p = CONST_VA + k * 4
        b = read(blob, secs, p, 4)
        u = struct.unpack('<I', b)[0]
        print(f'  0x{p:08X}  {b.hex(" ")}  u32 {u:08X}  float {struct.unpack("<f", b)[0]:.6g}')

    print('\n===== full predicate 0x70FB20 =====')
    code = read(blob, secs, 0x70FB20, 0x80)
    for ins in md.disasm(code, 0x70FB20):
        print(f'  {ins.address:#010x}  {ins.bytes.hex(" "):<24} {ins.mnemonic} {ins.op_str}')
        if ins.mnemonic.startswith('ret'):
            break

    print('\n===== 1.12 twin: same constant + same code shape? =====')
    blob2 = IMAGE_112.read_bytes()
    secs2 = sections(blob2)
    # search 1.12 .text for the same instruction sequence as 0x70FB20's head
    pat = bytes.fromhex('f30f104804f30f5c4904f30f1000f30f5c01')
    for name, sva, vs, raw_, rs in secs2:
        if name != '.text':
            continue
        data = blob2[raw_:raw_ + min(vs, rs)]
        i = data.find(pat)
        while i >= 0:
            print(f'  1.12 candidate predicate at VA 0x{BASE + sva + i:X} (RVA 0x{sva + i:X})')
            i = data.find(pat, i + 1)
    # the float constant
    p = struct.pack('<f', f)
    for name, sva, vs, raw_, rs in secs2:
        data = blob2[raw_:raw_ + min(vs, rs)]
        j = data.find(p)
        hits = []
        while j >= 0 and len(hits) < 8:
            hits.append(BASE + sva + j)
            j = data.find(p, j + 1)
        if hits:
            print(f'  1.12 float {f} in {name}: ' + ' '.join(f'0x{h:X}' for h in hits))


if __name__ == '__main__':
    main()
