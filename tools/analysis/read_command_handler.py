"""Read-only: read the 0xA424E0 region from the start so we can decide whether
'force the anchor search to return 1' actually yields a placement, or just leaves
an empty anchor list behind.
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

    # find the start of the function containing 0xA424E0
    start = 0xA424E0
    for cand in range(0xA424E0 - 1, 0xA424E0 - 0x200, -1):
        prev = read(blob, secs, cand - 1, 1)
        if prev and prev[0] in (0xC3, 0xC2, 0xCC):
            start = cand
            break
    print(f'function start 0x{start:X}')
    code = read(blob, secs, start, 0x160)
    for ins in md.disasm(code, start):
        print(f'  {ins.address:#010x}  {ins.bytes.hex(" "):<22} {ins.mnemonic} {ins.op_str}')
        if ins.mnemonic.startswith('ret') and ins.address > 0xA424E0:
            break
        if ins.address > 0xA42580:
            break

    print('\n===== what is 0x7A14B0 called with? (arg order at the call site) =====')
    code = read(blob, secs, 0xA424E0, 0x70)
    md.detail = True
    for ins in md.disasm(code, 0xA424E0):
        print(f'  {ins.address:#010x}  {ins.bytes.hex(" "):<22} {ins.mnemonic} {ins.op_str}')
        if ins.address >= 0xA4252C:
            break

    print('\n===== entry of the anchor search: what does the 5th arg slot hold? =====')
    print('  call site: push [esp+8](restriction/out), push [esi] , push [esi+0xC], push [esp+0x20]')
    print('  => arg1=[esp+20h] at call time, arg2=[esi+0Ch], arg3=[esi], arg4=lea local')


if __name__ == '__main__':
    main()
