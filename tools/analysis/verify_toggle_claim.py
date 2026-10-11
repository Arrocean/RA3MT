"""Read-only: verify the ONE live claim left standing — commit 434f7e1 says
"0x642450 loads the distance bound from [[0xCF2CAC]+0xC]". Disassemble the real
function that contains 0x642450 and look for that load. Also disassemble the
sole caller of the anchor search 0x7A14B0 at 0xA42524 to see what the return
value means.
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

    # 1) the function containing 0x642450 -- walk back to its prologue
    print('===== function containing 0x642450 (walk back to a terminator) =====')
    start = 0x642450
    for cand in range(0x642450 - 1, 0x642450 - 0x200, -1):
        prev = read(blob, secs, cand - 1, 1)
        if prev and prev[0] in (0xC3, 0xC2, 0xCC):
            start = cand
            break
    print(f'  start 0x{start:X}')
    code = read(blob, secs, start, 0x180)
    for ins in md.disasm(code, start):
        mark = ''
        if ins.address <= 0x642450 < ins.address + ins.size:
            mark = '   <== 0x642450 lands here (mid-instruction)'
        if ins.address == 0x642450:
            mark = '   <== 0x642450 lands here (boundary)'
        print(f'    {ins.address:#010x}  {ins.bytes.hex(" "):<22} {ins.mnemonic} {ins.op_str}{mark}')
        if ins.mnemonic.startswith('ret'):
            break
    print('  any operand equal to 0x8F2CAC in this range?',
          b'\xac\x2c\x8f\x00' in code)

    # 2) what the anchor search returns, and how its caller consumes it
    print('\n===== caller of anchor search 0x7A14B0: 0xA42524 =====')
    code = read(blob, secs, 0xA424C0, 0x120)
    for ins in md.disasm(code, 0xA424C0):
        mark = '   <== call anchor' if ins.address == 0xA42524 else ''
        print(f'    {ins.address:#010x}  {ins.bytes.hex(" "):<22} {ins.mnemonic} {ins.op_str}{mark}')
        if ins.address > 0xA42580:
            break


if __name__ == '__main__':
    main()
