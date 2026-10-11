"""Read-only: find the Steam repack (1.13 / 1.12) counterpart of the EA 1.12
free-build gate function (pirated copy @ 0x4E74B0..0x4E7580, FINAL3 patch at
0x4E7565: jne->jmp kills the 'return 2 = out of buildable range' path).

Searches distinctive byte signatures from the EA function body in the Steam
repack .text sections, then disassembles the hits for structural match
(loop + mov bl,al + test bl,bl + fail-code epilogue + ret 0x10).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_trace_sites import sections, read_va  # noqa: E402

EA = Path(r'D:\BaiduNetdiskDownload\Red Alert 3\Data\ra3_1.12.game')
STEAM = {
    '1.13': Path(r'D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data\ra3_1.13.game'),
    '1.12': Path(r'D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data\ra3_1.12.game'),
}
BASE = 0x400000

from capstone import Cs, CS_ARCH_X86, CS_MODE_32  # noqa: E402
md = Cs(CS_ARCH_X86, CS_MODE_32)

# signatures from the EA function body (order: most distinctive first)
SIGS = [
    ('test al,al; sete al; test al,al', bytes.fromhex('84c00f94c084c0')),
    ('mov eax,2; pop ebx; add esp,0xC; ret 0x10', bytes.fromhex('b8020000005b83c40cc21000')),
    ('test edx,0x8000', bytes.fromhex('f7c200800000')),
    ('mov bl,al; ... test bl,bl; jne +0x19', bytes.fromhex('8ad884db7519')),
]


def text_bytes(blob, secs):
    for name, sva, vsize, raw, rsize in secs:
        if name == '.text':
            return BASE + sva, blob[raw:raw + min(vsize, rsize)]
    raise RuntimeError('no .text')


def main():
    for ver, path in STEAM.items():
        blob = path.read_bytes()
        secs = sections(blob)
        tva, data = text_bytes(blob, secs)
        print(f'\n################ Steam repack {ver} ({path.name}) ################')
        for label, pat in SIGS:
            hits = []
            i = 0
            while True:
                i = data.find(pat, i)
                if i < 0:
                    break
                hits.append(tva + i)
                i += 1
            print(f'--- {label}: {len(hits)} hits ---')
            for h in hits[:12]:
                print(f'    0x{h:X}')

    # For each sete-sig hit in 1.13, dump context to eyeball the loop+epilogue
    print('\n################ context checks (1.13) ################')
    blob = STEAM['1.13'].read_bytes()
    secs = sections(blob)
    pat = SIGS[0][1]
    tva, data = text_bytes(blob, secs)
    i = 0
    while True:
        i = data.find(pat, i)
        if i < 0:
            break
        va = tva + i
        print(f'\n=== hit at 0x{va:X} (context -0x40..+0x30) ===')
        code, _ = read_va(blob, secs, va - 0x40, 0x78)
        for ins in md.disasm(code, va - 0x40):
            print(f'  {ins.address:#010x}  {ins.bytes.hex(" "):<22} {ins.mnemonic} {ins.op_str}')
        i += 1


if __name__ == '__main__':
    main()
