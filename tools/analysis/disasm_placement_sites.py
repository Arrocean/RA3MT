"""Read-only follow-ups:
1) find 4-byte little-endian pointers anywhere in the image that land inside a
   given heap object range (who else holds the GameData object);
2) disassemble the PLACEHUNT candidates far enough to judge how hot they are
   and what they iterate.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_trace_sites import sections  # noqa: E402

IMAGE = Path(r'D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data\ra3_1.13.game')
IMAGE_BASE = 0x400000


def main():
    blob = IMAGE.read_bytes()
    secs = sections(blob)
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)

    print('===== section map =====')
    for n, va, vs, raw, rs in secs:
        print(f'  {n:<10} RVA 0x{va:<8X} vsize 0x{vs:<8X} raw 0x{raw:<8X} rsize 0x{rs:X}')

    print('\n===== hotspot disassembly =====')
    for va, n in ((0x818A00, 0x50), (0x82B890, 0x60), (0xA3AAB0, 0x70),
                  (0x5F0930, 0x70), (0x64C970, 0x40), (0x86F310, 0x50)):
        rva = va - IMAGE_BASE
        code = None
        for name, sva, vs, raw, rs in secs:
            if sva <= rva < sva + max(vs, rs):
                code = blob[raw + (rva - sva): raw + (rva - sva) + n]
                sec = name
                break
        print(f'\n-- 0x{va:X} ({sec}) --')
        for ins in md.disasm(code, va):
            print(f'  {ins.address:#010x}  {ins.bytes.hex(" "):<22} {ins.mnemonic} {ins.op_str}')

    print('\n===== E8 callers of the hottest-looking site 0x818A00 =====')
    text = [(sva, raw, min(vs, rs)) for n, sva, vs, raw, rs in secs if n == '.text']
    target = 0x818A00
    callers = []
    for sva, raw, size in text:
        data = blob[raw:raw + size]
        for i in range(len(data) - 5):
            if data[i] != 0xE8:
                continue
            rel = struct.unpack_from('<i', data, i + 1)[0]
            if IMAGE_BASE + sva + i + 5 + rel == target:
                callers.append(IMAGE_BASE + sva + i)
    print(f'  {len(callers)} callers: ' + ' '.join(f'0x{c:X}' for c in callers))


if __name__ == '__main__':
    main()
