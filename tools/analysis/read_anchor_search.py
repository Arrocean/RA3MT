"""Read-only: finish disassembling the anchor search 0x7A14B0. Does it take a
distance bound argument and compare against it? That would be the real
"placement distance" limit and a much better patch target than the dead
[0x8F2CAC]+0xC field.
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
    blob = IMAGE.read_bytes()
    secs = sections(blob)
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)

    code = read(blob, secs, 0x7A14B0, 0x120)
    for ins in md.disasm(code, 0x7A14B0):
        print(f'  {ins.address:#010x}  {ins.bytes.hex(" "):<24} {ins.mnemonic} {ins.op_str}')
        if ins.mnemonic.startswith('ret'):
            print('  --- end of function ---')
            break

    print('\n===== what is 0x70FB20 (the per-candidate predicate)? =====')
    code = read(blob, secs, 0x70FB20, 0x60)
    for ins in md.disasm(code, 0x70FB20):
        print(f'  {ins.address:#010x}  {ins.bytes.hex(" "):<24} {ins.mnemonic} {ins.op_str}')
        if ins.mnemonic.startswith('ret'):
            break

    print('\n===== callers of the anchor search 0x7A14B0 =====')
    import struct
    for name, sva, vs, raw, rs in secs:
        if name != '.text':
            continue
        data = blob[raw:raw + min(vs, rs)]
        for i in range(len(data) - 5):
            if data[i] != 0xE8:
                continue
            rel = struct.unpack_from('<i', data, i + 1)[0]
            if BASE + sva + i + 5 + rel == 0x7A14B0:
                print(f'  0x{BASE + sva + i:X}')


if __name__ == '__main__':
    main()
