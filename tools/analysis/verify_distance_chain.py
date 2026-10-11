"""Read-only: re-audit the placement-distance chain with ONE addressing
convention (VA = RVA + 0x400000) everywhere.

The previous session's "dead device" verdict has three addressing mistakes in
it:
  1. find_gamedata_refs.py scanned .text for struct.pack('<I', 0x8F2CAC) --
     the RVA. Instructions encode the VA 0xCF2CAC (bytes AC 2C CF 00), so the
     scan was a guaranteed false negative (the control 0xCF30F0 was scanned
     as a VA, i.e. two different conventions in one comparison).
  2. "0x120780 is not in .text" -- VA 0x120780 < image base 0x400000, so it
     cannot be a module VA at all. It is an RVA: live VA 0x520780. The v18m
     notes mixed VA (0x642450) and RVA (0x120780) in one chain string.
  3. "no code path reads [obj+0xC]" contradicts the v18n live test: writing
     100000 there made the game crawl (full-map grid scan). An unread value
     cannot cause that.

This script scans the REAL operand bytes, disassembles the chain members at
their true function entries, and lists direct callers.

Usage: py tools/analysis/verify_distance_chain.py
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

# globals that hold the GameData pointer, per version, as VAs
GLOBAL_VA = {'1.13': 0xCF2CAC, '1.12': 0xCEE98C}

# chain members to disassemble, per version, VAs.
#   validator : the function that actually contains 0x642450 (a return address
#               into it, mislabeled as an entry in features.json)
#   worker    : the "0x120780" grid worker -- actually RVA 0x120780
#   regionpred: vf+0x48 region predicate (PLACEHUNT 0x5F0930)
#   sixiter   : the 6-iteration predicate (PLACEHUNT 0x64C970)
CHAIN = {
    '1.13': {
        'validator head': 0x6423FC,
        'worker head': 0x520780,
        'regionpred head': 0x5F0930,
        'sixiter head': 0x64C970,
        'top anchor (ret addr)': 0x647300,
    },
    '1.12': {
        'validator ref': 0x63D8E7,     # live return address inside validator
        'worker head': 0x538250,       # RVA 0x138250
    },
}

from capstone import Cs, CS_ARCH_X86, CS_MODE_32  # noqa: E402
md = Cs(CS_ARCH_X86, CS_MODE_32)


def text_of(blob, secs):
    for name, sva, vsize, raw, rsize in secs:
        if name == '.text':
            return IMAGE_BASE + sva, vsize, blob[raw:raw + min(vsize, rsize)]
    raise RuntimeError('no .text')


def scan_imm32(blob, secs, value, label):
    """All .text occurrences of the 4-byte operand `value` (VA), with the
    containing instruction disassembled."""
    tva, tsize, data = text_of(blob, secs)
    pat = struct.pack('<I', value)
    hits = []
    i = 0
    while True:
        i = data.find(pat, i)
        if i < 0:
            break
        i += 1
        hits.append(tva + i - 1)
    print(f'--- operand {label} 0x{value:X} ({pat.hex(" ")}): {len(hits)} raw hits in .text ---')
    for va in hits:
        # walk back up to 6 bytes, disassemble forward, keep the decoding whose
        # instruction bytes actually cover the operand offset
        for back in range(1, 7):
            ins_va = va - back
            code = data[ins_va - tva:ins_va - tva + 16]
            ins = next(iter(md.disasm(code, ins_va)), None)
            if ins and pat in ins.bytes:
                print(f'  0x{ins.address:X}  {ins.bytes.hex(" "):<24} {ins.mnemonic} {ins.op_str}')
                break
        else:
            print(f'  ~0x{va:X}  (no clean decode; raw {data[va-4-tva:va+4-tva].hex(" ")})')
    return hits


def func_start(blob, secs, va, window=0x600):
    """Nearest preceding plausible entry: preceded by ret/int3 padding."""
    for cand in range(va - 1, va - window, -1):
        prev = read_va(blob, secs, cand - 1, 5)[0]
        if prev is None:
            continue
        if prev[0] in (0xC3, 0xC2, 0xCC) or prev[:4] == b'\xCC\xCC\xCC\xCC':
            return cand
    return None


def disasm(blob, secs, va, max_bytes=0x200, mark=None, stop_at_ret=True):
    code, sec = read_va(blob, secs, va, max_bytes)
    print(f'--- disasm 0x{va:X} (sec {sec}) ---')
    for ins in md.disasm(code, va):
        tag = ''
        if mark and ins.address in mark:
            tag = f'   <== {mark[ins.address]}'
        print(f'  {ins.address:#010x}  {ins.bytes.hex(" "):<24} {ins.mnemonic} {ins.op_str}{tag}')
        if stop_at_ret and ins.mnemonic in ('ret', 'int3') or ins.mnemonic.startswith('ret'):
            break


def callers(blob, secs, target):
    """Direct E8 rel32 callers of target (VA)."""
    tva, tsize, data = text_of(blob, secs)
    out = []
    for i in range(len(data) - 5):
        if data[i] == 0xE8:
            rel = struct.unpack_from('<i', data, i + 1)[0]
            if tva + i + 5 + rel == target:
                out.append(tva + i)
    return out


def main():
    for ver, image in IMAGES.items():
        blob = image.read_bytes()
        secs = sections(blob)
        print(f'\n################ {ver}  {image.name} ################')

        # 1. THE decisive check: real operand references to the GameData global
        scan_imm32(blob, secs, GLOBAL_VA[ver], f'GameData global VA ({ver})')

        # 2. chain members
        for label, va in CHAIN[ver].items():
            if 'anchor' in label or 'ref' in label:
                # a return address: show its function start + context around it
                fs = func_start(blob, secs, va)
                print(f'\n=== {label} 0x{va:X} -> function start 0x{fs:X} ===' if fs
                      else f'\n=== {label} 0x{va:X} -> no start found ===')
                if fs:
                    disasm(blob, secs, fs, 0x160, mark={va: label})
            else:
                print(f'\n=== {label} 0x{va:X} ===')
                disasm(blob, secs, va, 0x160)

        # 3. direct callers of the interesting predicates (1.13 only for now)
        if ver == '1.13':
            for label, va in (('validator 0x6423FC', 0x6423FC),
                              ('regionpred 0x5F0930', 0x5F0930),
                              ('sixiter 0x64C970', 0x64C970),
                              ('worker 0x520780', 0x520780)):
                cs = callers(blob, secs, va)
                print(f'\n--- direct E8 callers of {label}: {len(cs)} ---')
                print('    ' + ' '.join(hex(c) for c in cs[:20]))


if __name__ == '__main__':
    main()
