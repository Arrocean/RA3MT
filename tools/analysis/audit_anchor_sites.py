"""Read-only audit of the placement anchors that the build-anywhere feature has
been pointed at, on the 1.13 disk image:

  0x7A14B0  "anchor search" (the 'anchor' SITES entry / features.json displaced)
  0x3A14B0  the address the 50bfcff hook actually used
  0x6424E0 / 0x642524  claimed place-structure command handler + call site
  0x642450 / 0x647300 / 0x120780  the "value toggle" chain anchors

For each: is it an instruction boundary, what does it return, and who calls it.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_trace_sites import sections  # noqa: E402

IMAGE = Path(r'D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data\ra3_1.13.game')
BASE = 0x400000

ANCHORS = [0x7A14B0, 0x3A14B0, 0x6424E0, 0x642524, 0x642450, 0x647300, 0x120780,
           0x5F0930, 0x3A14B0]


def read(blob, secs, va, n):
    rva = va - BASE
    for name, sva, vs, raw, rs in secs:
        if sva <= rva < sva + max(vs, rs):
            return blob[raw + (rva - sva): raw + (rva - sva) + n], name
    return None, None


def callers(blob, secs, target):
    out = []
    for name, sva, vs, raw, rs in secs:
        if name != '.text':
            continue
        data = blob[raw:raw + min(vs, rs)]
        for i in range(len(data) - 5):
            if data[i] != 0xE8:
                continue
            rel = struct.unpack_from('<i', data, i + 1)[0]
            if BASE + sva + i + 5 + rel == target:
                out.append(BASE + sva + i)
    return out


def main():
    blob = IMAGE.read_bytes()
    secs = sections(blob)
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)

    for va in dict.fromkeys(ANCHORS):
        code, sec = read(blob, secs, va, 0x60)
        print(f'\n===== 0x{va:X} (section {sec}) =====')
        if code is None:
            print('  NOT MAPPED')
            continue
        # boundary check: does an instruction start exactly here for some decode
        # of the preceding bytes? cheap proxy: is the byte before a terminator?
        prev, _ = read(blob, secs, va - 8, 8)
        print(f'  preceding bytes: {prev.hex(" ")}')
        n = 0
        for ins in md.disasm(code, va):
            print(f'    {ins.address:#010x}  {ins.bytes.hex(" "):<22} {ins.mnemonic} {ins.op_str}')
            n += 1
            if n >= 14 or ins.mnemonic.startswith('ret') or ins.mnemonic == 'int3':
                break
        cs = callers(blob, secs, va)
        print(f'  direct E8 callers: {len(cs)}' + ('  ' + ' '.join(f'0x{c:X}' for c in cs[:10]) if cs else ''))


if __name__ == '__main__':
    main()
