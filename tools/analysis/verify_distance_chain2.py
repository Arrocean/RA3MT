"""Read-only: find the REAL distance consumer via v18m's instruction
fingerprint, now that we know the v18m chain addresses (0x647300 -> 0x642450
-> 0x120780) were recorded as RVAs, not VAs (PLACEHUNT labels do the same:
'0x63AAB0' == VA 0xA3AAB0).

Fingerprint from v18m notes (claimed to sit at RVA 0x642484 = VA 0xA42484):
    mov edx,[GameData global]     ; 8B 15 AC 2C CF 00   (or A1 form)
    fld [edx+0xC]                 ; D9 42 0C / D9 40 0C
    ...
    or ecx, 0xC4020               ; 81 C9 20 40 0C 00
    mov ecx, [ThePlacementGrid]   ; 8B 0D CC 21 CE 00
    call worker                   ; E8 ... (worker = VA 0x520780, RVA 0x120780)

This script scans the 1.13 image for every reference to ThePlacementGrid
(0xCE21CC) and to the 0xC4020 immediate, cross-references them, and
disassembles the winning context. Then it does the same for 1.12
(ThePlacementGrid 0xCDDEAC, worker RVA 0x138250 = VA 0x538250).
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_trace_sites import sections, read_va  # noqa: E402

IMAGES = {
    '1.13': Path(r'D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data\ra3_1.13.game'),
    '1.12': Path(r'D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data\ra3_1.12.game'),
}
IMAGE_BASE = 0x400000

from capstone import Cs, CS_ARCH_X86, CS_MODE_32  # noqa: E402
md = Cs(CS_ARCH_X86, CS_MODE_32)


def text_of(blob, secs):
    for name, sva, vsize, raw, rsize in secs:
        if name == '.text':
            return IMAGE_BASE + sva, vsize, blob[raw:raw + min(vsize, rsize)]
    raise RuntimeError('no .text')


def find_all(data, base, pat):
    out, i = [], 0
    while True:
        i = data.find(pat, i)
        if i < 0:
            return out
        out.append(base + i)
        i += 1


def context(blob, secs, va, before=0x40, after=0x60, marks=None):
    """Disassemble a window around va, one clean stream from va-before."""
    start = va - before
    code, _ = read_va(blob, secs, start, before + after)
    lines = []
    for ins in md.disasm(code, start):
        tag = ''
        if marks and ins.address in marks:
            tag = '   <== ' + marks[ins.address]
        arrow = '  <<<' if ins.address <= va < ins.address + ins.size else ''
        lines.append(f'  {ins.address:#010x}  {ins.bytes.hex(" "):<24} {ins.mnemonic} {ins.op_str}{tag}{arrow}')
    return '\n'.join(lines)


def main():
    for ver, image in IMAGES.items():
        blob = image.read_bytes()
        secs = sections(blob)
        tva, tsize, data = text_of(blob, secs)
        print(f'\n################ {ver}  {image.name} ################')

        if ver == '1.13':
            grid_global, gamedata_global = 0xCE21CC, 0xCF2CAC
        else:
            grid_global, gamedata_global = 0xCDDEAC, 0xCEE98C

        # 1. every reference to ThePlacementGrid global
        pat = struct.pack('<I', grid_global)
        refs = find_all(data, tva, pat)
        print(f'\n--- ThePlacementGrid 0x{grid_global:X} operand bytes in .text: {len(refs)} hits ---')

        # 2. every 0xC4020 immediate (or ecx/lea form) near those refs
        orpat = bytes.fromhex('81c920400c00')       # or ecx,0xC4020
        ors = find_all(data, tva, orpat)
        print(f'--- or ecx,0xC4020 sites: {len(ors)} ---  ' + ' '.join(hex(a) for a in ors[:20]))

        # 3. union: disassemble around every grid-global ref AND every or-site
        marks = {a: 'or ecx,0xC4020' for a in ors}
        # mark gamedata refs too
        gdpat = struct.pack('<I', gamedata_global)
        for a in find_all(data, tva, gdpat):
            marks[a] = marks.get(a, '') + ' GameDataGlobal'
        for a in refs:
            print(f'\n=== context around ThePlacementGrid ref 0x{a:X} ===')
            print(context(blob, secs, a, 0x50, 0x50, marks))

        # 4. the three gamedata-global instruction refs from the first pass
        print(f'\n--- GameData global 0x{gamedata_global:X} full contexts ---')
        for a in find_all(data, tva, gdpat):
            print(f'\n=== context around GameData ref 0x{a:X} ===')
            print(context(blob, secs, a, 0x50, 0x60, marks))


if __name__ == '__main__':
    main()
