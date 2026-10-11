"""Independent verification of the claims in the GLM report.

1. VA-form scan of .text for 0xCF2CAC (the address form actually encoded in
   instructions) - my previous scan used the RVA byte pattern and was a false
   negative. Control: 0xCF30F0.
2. Disassemble the "verifier" at VA 0xA42450 and the worker call.
3. Disassemble percell VA 0xA2A1E0 and check the AABB branches + the proposed
   patch site 0xA2A25E.
4. 1.12 twin checks: 0xA3D8E0 verifier, 0xA252E0 percell.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_trace_sites import sections  # noqa: E402

IMAGES = {
    '1.13': Path(r'D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data\ra3_1.13.game'),
    '1.12': Path(r'D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data\ra3_1.12.game'),
}
BASE = 0x400000


def read(blob, secs, va, n):
    rva = va - BASE
    for name, sva, vs, raw, rs in secs:
        if sva <= rva < sva + max(vs, rs):
            return blob[raw + (rva - sva): raw + (rva - sva) + n]
    return None


def text_of(blob, secs):
    for name, sva, vs, raw, rs in secs:
        if name == '.text':
            return sva, blob[raw:raw + min(vs, rs)]
    return None, None


def scan_va(blob, secs, va_target, label):
    sva, text = text_of(blob, secs)
    pat = struct.pack('<I', va_target)
    hits = []
    i = 0
    while True:
        i = text.find(pat, i)
        if i < 0:
            break
        hits.append(BASE + sva + i - 2)   # instruction start candidate (opcode A1 / 8B xx)
        i += 1
    print(f'  [{label}] VA-form operand 0x{va_target:X}: {len(hits)} hits')
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    for va in hits[:10]:
        best = None
        for back in range(0, 7):
            start = va - back
            code = read(blob, secs, start, 16)
            if not code:
                continue
            ins = next(iter(md.disasm(code, start)), None)
            if ins and struct.pack('<I', va_target) in ins.bytes:
                best = ins
                break
        if best:
            print(f'      0x{best.address:X}  {best.bytes.hex(" "):<20} {best.mnemonic} {best.op_str}')
    return hits


def main():
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)

    for ver, path in IMAGES.items():
        blob = path.read_bytes()
        secs = sections(blob)
        print(f'\n############ {ver} ############')

        print('\n-- 1) VA-form scan --')
        scan_va(blob, secs, 0xCF2CAC if ver == '1.13' else 0xCEE98C,
                f'{ver} GameData global (VA)')
        scan_va(blob, secs, 0xCF30F0, 'control 0xCF30F0 (VA)')
        scan_va(blob, secs, 0x8F2CAC if ver == '1.13' else 0x8EE98C,
                f'{ver} GameData global (RVA form - expect 0)')

        print('\n-- 2) verifier --')
        va = 0xA42450 if ver == '1.13' else 0xA3D8E0
        code = read(blob, secs, va, 0x90)
        for ins in md.disasm(code, va):
            print(f'    0x{ins.address:X}  {ins.bytes.hex(" "):<24} {ins.mnemonic} {ins.op_str}')
            if ins.mnemonic.startswith('ret'):
                break

        print('\n-- 3) percell + AABB branch --')
        va = 0xA2A1E0 if ver == '1.13' else 0xA252E0
        code = read(blob, secs, va, 0x110)
        for ins in md.disasm(code, va):
            print(f'    0x{ins.address:X}  {ins.bytes.hex(" "):<24} {ins.mnemonic} {ins.op_str}')
            if ins.address >= va + 0xC8:
                break

        patch = 0xA2A25E if ver == '1.13' else 0xA2535E
        raw = read(blob, secs, patch, 8)
        print(f'\n    proposed patch site 0x{patch:X}: {raw.hex(" ")}')
        ins = next(iter(md.disasm(raw, patch)), None)
        if ins:
            target = ins.op_str
            print(f'      decodes as: {ins.mnemonic} {target}')
            if '0x' in target:
                tgt = int(target, 16)
                print(f'      -> jump to 0x{tgt:X}; bytes at target: '
                      f'{read(blob, secs, tgt, 12).hex(" ")}')
        print(f'      patched (EB 46): would be eb 46 -> 0x{patch + 2 + 0x46:X}')

        print('\n-- 4) or ecx,0xC4020 uniqueness --')
        sva, text = text_of(blob, secs)
        pat2 = bytes.fromhex('81 c9 20 40 0c 00')      # or ecx,0xC4020
        pat3 = bytes.fromhex('0d 20 40 0c 00')         # or eax,0xC4020
        for p, lbl in ((pat2, 'or ecx,0xC4020'), (pat3, 'or eax,0xC4020')):
            n, i, locs = 0, 0, []
            while True:
                i = text.find(p, i)
                if i < 0:
                    break
                locs.append(BASE + sva + i)
                n += 1
                i += 1
            print(f'      {lbl}: {n} hits ' + ' '.join(f'0x{a:X}' for a in locs[:6]))


if __name__ == '__main__':
    main()
