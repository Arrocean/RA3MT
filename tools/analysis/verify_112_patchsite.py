"""Read-only: settle the 1.12 AABB patch-site bytes and check both versions'
branch instructions byte for byte, straight from the two images.
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

# (version, percell entry, branch addresses in order, FAIL, PASS)
CASES = {
    '1.13': (0xA2A1E0, [0xA2A25E, 0xA2A269, 0xA2A276, 0xA2A281], 0xA2A283, 0xA2A2A6),
    '1.12': (0xA252E0, [0xA2535E, 0xA25369, 0xA25376, 0xA25381], 0xA25383, 0xA253A6),
}


def read(blob, secs, va, n):
    rva = va - BASE
    for name, sva, vs, raw, rs in secs:
        if sva <= rva < sva + max(vs, rs):
            return blob[raw + (rva - sva): raw + (rva - sva) + n]
    return None


def main():
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)

    for ver, path in IMAGES.items():
        blob = path.read_bytes()
        secs = sections(blob)
        entry, branches, fail, pas = CASES[ver]
        print(f'\n===== {ver} percell 0x{entry:X} =====')
        # whole-function byte comparison: entry .. fail
        head = read(blob, secs, entry, fail - entry + 0x20)
        print(f'  function head bytes (entry..FAIL): {head.hex(" ")}')
        for i, bva in enumerate(branches):
            raw = read(blob, secs, bva, 2)
            ins = next(iter(md.disasm(raw, bva)), None)
            print(f'  branch[{i}] 0x{bva:X}: {raw.hex(" ")}  {ins.mnemonic} {ins.op_str}'
                  if ins else f'  branch[{i}] 0x{bva:X}: {raw.hex(" ")}')
        # what the first branch SHOULD be patched to
        rel = pas - (branches[0] + 2)
        print(f'  first-branch patch: {read(blob, secs, branches[0], 2).hex(" ")} -> '
              f'eb {rel:02x}  => 0x{branches[0] + 2 + rel:X} (target 0x{pas:X})')

        # verify the pass entry is a real instruction boundary by linear decode
        # from the function entry
        code = read(blob, secs, entry, pas - entry + 8)
        boundaries = set()
        consumed = 0
        for ins in md.disasm(code, entry):
            boundaries.add(ins.address)
            consumed = ins.address + ins.size
            if ins.mnemonic.startswith('ret'):
                break
        print(f'  linear decode reached 0x{consumed:X}; PASS 0x{pas:X} is a boundary: '
              f'{pas in boundaries}')

    print('\n===== cross-version byte identity of the whole gate region =====')
    b13, b12 = IMAGES['1.13'].read_bytes(), IMAGES['1.12'].read_bytes()
    s13, s12 = sections(b13), sections(b12)
    r13 = read(b13, s13, CASES['1.13'][0], CASES['1.13'][3] - CASES['1.13'][0])
    r12 = read(b12, s12, CASES['1.12'][0], CASES['1.12'][3] - CASES['1.12'][0])
    print(f'  identical: {r13 == r12}')
    if r13 != r12:
        for i, (x, y) in enumerate(zip(r13, r12)):
            if x != y:
                print(f'    first diff at +0x{i:X}: 1.13={x:02x} 1.12={y:02x}')


if __name__ == '__main__':
    main()
