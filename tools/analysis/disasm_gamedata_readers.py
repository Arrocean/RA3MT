"""Read-only: disassemble every site that references the placement-distance
global 0x8F2CAC (1.13) and its 1.12 counterpart 0x8EE98C, and work out which
field offset each site actually reads.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_trace_sites import sections  # noqa: E402

IMAGE = Path(r'D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data\ra3_1.13.game')
IMAGE_112 = Path(r'D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data\ra3_1.12.game')
BASE = 0x400000


def find_refs(blob, secs, gva):
    pat = struct.pack('<I', gva)
    out = []
    for n, sva, vs, raw, rs in secs:
        if n not in ('.text',):
            continue
        data = blob[raw:raw + min(vs, rs)]
        i = 0
        while True:
            i = data.find(pat, i)
            if i < 0:
                break
            out.append(BASE + sva + i)
            i += 1
    return out


def main():
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)

    for path, gva, label in ((IMAGE, 0x8F2CAC, '1.13'), (IMAGE_112, 0x8EE98C, '1.12')):
        blob = path.read_bytes()
        secs = sections(blob)
        refs = find_refs(blob, secs, gva)
        print(f'\n######## {label} global 0x{gva:X}: {len(refs)} immediate refs ########')
        for va in refs:
            # step back to the instruction start
            for back in range(0, 7):
                start = va - back
                rva = start - BASE
                code = None
                for n, sva, vs, raw, rs in secs:
                    if sva <= rva < sva + min(vs, rs):
                        code = blob[raw + (rva - sva): raw + (rva - sva) + 48]
                        break
                if not code:
                    continue
                ins = next(iter(md.disasm(code, start)), None)
                if ins and ins.size > back and struct.pack('<I', gva) in ins.bytes:
                    print(f'  0x{ins.address:X}  {ins.bytes.hex(" "):<20} {ins.mnemonic} {ins.op_str}')
                    rva2 = ins.address + ins.size - BASE
                    for n, sva, vs, raw, rs in secs:
                        if sva <= rva2 < sva + min(vs, rs):
                            code2 = blob[raw + (rva2 - sva): raw + (rva2 - sva) + 64]
                            for k, nxt in enumerate(md.disasm(code2, ins.address + ins.size)):
                                if k >= 8:
                                    break
                                print(f'        {nxt.address:#010x}  {nxt.bytes.hex(" "):<20} '
                                      f'{nxt.mnemonic} {nxt.op_str}')
                            break
                    print()
                    break


if __name__ == '__main__':
    main()
