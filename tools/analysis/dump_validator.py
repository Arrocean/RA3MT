"""Read-only: dump the real placement validator around VA 0xA42496
(the unique 'or ecx,0xC4020' site in 1.13) and find its true entry + what
global the distance actually comes from. Also dump the 1.12 counterpart.
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


def func_start(blob, secs, va, window=0x800):
    for cand in range(va - 1, va - window, -1):
        prev = read_va(blob, secs, cand - 1, 5)[0]
        if prev is None:
            continue
        if prev[0] in (0xC3, 0xC2, 0xCC) or prev[:4] == b'\xCC\xCC\xCC\xCC':
            return cand
    return None


def disasm_range(blob, secs, lo, hi, marks=None):
    code, sec = read_va(blob, secs, lo, hi - lo)
    print(f'--- 0x{lo:X}..0x{hi:X} (sec {sec}) ---')
    for ins in md.disasm(code, lo):
        tag = ''
        if marks and ins.address in marks:
            tag = '   <== ' + marks[ins.address]
        print(f'  {ins.address:#010x}  {ins.bytes.hex(" "):<26} {ins.mnemonic} {ins.op_str}{tag}')


def callers(blob, secs, target):
    for name, sva, vsize, raw, rsize in secs:
        if name != '.text':
            continue
        base = IMAGE_BASE + sva
        data = blob[raw:raw + min(vsize, rsize)]
        out = []
        for i in range(len(data) - 5):
            if data[i] == 0xE8:
                rel = struct.unpack_from('<i', data, i + 1)[0]
                if base + i + 5 + rel == target:
                    out.append(base + i)
        return out
    return []


def main():
    for ver, image in IMAGES.items():
        blob = image.read_bytes()
        secs = sections(blob)
        print(f'\n################ {ver} ################')

        if ver == '1.13':
            anchor = 0xA42496          # or ecx,0xC4020
            grid = 0xCE21CC
        else:
            # 1.12: find its own or ecx,0xC4020 site
            grid = 0xCDDEAC
            orpat = bytes.fromhex('81c920400c00')
            hits = []
            for name, sva, vsize, raw, rsize in secs:
                if name == '.text':
                    data = blob[raw:raw + min(vsize, rsize)]
                    base = IMAGE_BASE + sva
                    i = 0
                    while True:
                        i = data.find(orpat, i)
                        if i < 0:
                            break
                        hits.append(base + i)
                        i += 1
            print(f'1.12 or ecx,0xC4020 sites: {[hex(h) for h in hits]}')
            if not hits:
                continue
            anchor = hits[0]

        fs = func_start(blob, secs, anchor)
        print(f'anchor 0x{anchor:X} -> function start 0x{fs:X} (RVA 0x{fs - IMAGE_BASE:X})')
        marks = {anchor: 'or ecx,0xC4020'}
        disasm_range(blob, secs, fs, anchor + 0x90, marks)

        cs = callers(blob, secs, fs)
        print(f'\ndirect E8 callers of 0x{fs:X}: {len(cs)}: ' + ' '.join(hex(c) for c in cs[:24]))


if __name__ == '__main__':
    main()
