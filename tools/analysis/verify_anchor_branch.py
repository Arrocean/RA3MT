"""Read-only: what happens on the anchor-found branch?

0xA424E0: hash 0x9590538A -> 0x80BF10; then anchor(0x7A14B0); test al,al;
  al!=0 -> call 0xA415C0(ECX=this+0x10, arg1=1, out)
  al==0 -> call 0xA3AAB0(ECX=this+0x10, arg1=0)

If 0xA415C0 consumes the float3 the anchor wrote into the local out-param, the
building is placed at the ANCHOR (own base); if it consumes the mouse position,
the anchor is only a permission gate. Which is it?
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
    blob = IMAGE.read_bytes()
    secs = sections(blob)
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)

    for va, n, title in ((0xA415C0, 0xC0, 'anchor-found branch 0xA415C0'),
                         (0x7A14B0, 0x120, 'anchor search 0x7A14B0 (full-ish)')):
        print(f'\n===== {title} =====')
        code = read(blob, secs, va, n)
        if not code:
            print('  not mapped')
            continue
        for ins in md.disasm(code, va):
            print(f'  {ins.address:#010x}  {ins.bytes.hex(" "):<22} {ins.mnemonic} {ins.op_str}')
            if ins.mnemonic.startswith('ret'):
                break

    print('\n===== who calls 0xA415C0 / 0xA3AAB0 =====')
    for target in (0xA415C0, 0xA3AAB0):
        cs = []
        for name, sva, vs, raw, rs in secs:
            if name != '.text':
                continue
            data = blob[raw:raw + min(vs, rs)]
            for i in range(len(data) - 5):
                if data[i] != 0xE8:
                    continue
                rel = struct.unpack_from('<i', data, i + 1)[0]
                if BASE + sva + i + 5 + rel == target:
                    cs.append(BASE + sva + i)
        print(f'  0x{target:X}: {len(cs)} callers  ' + ' '.join(f'0x{c:X}' for c in cs[:12]))


if __name__ == '__main__':
    main()
