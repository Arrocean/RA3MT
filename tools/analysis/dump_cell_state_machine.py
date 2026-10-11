"""Read-only: the grid-cell buildability test 0xB322D0 is bigger than one basic
block - the first 'ret 4' at 0xB322DB is the early-out. Decode the whole function
and map the return-value states (1/2/3/0) that percell's 'cmp eax,1' consumes.
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

    code = read(blob, secs, 0xB322D0, 0x1C0)
    for ins in md.disasm(code, 0xB322D0):
        mark = ''
        if ins.mnemonic == 'ret':
            mark = '   <=== return'
        if ins.mnemonic == 'mov' and ins.op_str.startswith('eax, '):
            mark = '   <=== state value'
        print(f'  {ins.address:#010x}  {ins.bytes.hex(" "):<22} {ins.mnemonic} {ins.op_str}{mark}')


if __name__ == '__main__':
    main()
