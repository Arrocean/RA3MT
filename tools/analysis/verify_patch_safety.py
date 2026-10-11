"""Read-only: is the proposed AABB patch (0xA2A25E: 76 23 -> EB 46) landing on a
sane instruction boundary, and what does the PASS path do with EVERY candidate
cell once the gate is forced?

Also: read the trampoline generator's actual skip logic from the checked-out
tracer to settle whether the saturated ring still copies 120 bytes per hit.
"""
import re
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

    print('===== patch arithmetic check =====')
    for site, tgt in ((0xA2A25E, 0xA2A2A6), (0xA2535E, 0xA253A6)):
        raw = read(blob, secs, site, 2)
        rel = tgt - (site + 2)
        print(f'  0x{site:X}: {raw.hex(" ")} -> EB {rel:02X}  ({rel} = 0x{rel:X}) '
              f'lands 0x{site + 2 + rel:X} target 0x{tgt:X}  '
              f'{"OK" if site + 2 + rel == tgt else "MISMATCH"}')
        nxt = read(blob, secs, tgt, 16)
        for ins in md.disasm(nxt, tgt):
            print(f'     PASS entry: {ins.address:#x} {ins.bytes.hex(" "):<20} {ins.mnemonic} {ins.op_str}')
            break

    print('\n===== PASS path closure (0xA2A2A6 onward) =====')
    code = read(blob, secs, 0xA2A2A6, 0x190)
    for ins in md.disasm(code, 0xA2A2A6):
        print(f'  {ins.address:#010x}  {ins.bytes.hex(" "):<24} {ins.mnemonic} {ins.op_str}')
        if ins.mnemonic.startswith('ret'):
            break

    print('\n===== what does 0x8627D0 do (called with ECX=playerRoot)? =====')
    code = read(blob, secs, 0x8627D0, 0x60)
    for ins in md.disasm(code, 0x8627D0):
        print(f'  {ins.address:#010x}  {ins.bytes.hex(" "):<24} {ins.mnemonic} {ins.op_str}')
        if ins.mnemonic.startswith('ret'):
            break

    print('\n===== tracer: is the copy inside or outside the skip branch? =====')
    src = Path(__file__).resolve().parent.joinpath('trace_trampoline.py').read_text(encoding='utf-8')
    m = re.search(r'def build_trampoline.*?return bytes\(code\)', src, re.S)
    if m:
        for line in m.group(0).splitlines():
            print('   ' + line)
    else:
        print('   build_trampoline not found')


if __name__ == '__main__':
    main()
