"""Read-only: locate real function boundaries for the addresses that
assets/features.json calls the "placement verification chain"
(0x647300 -> 0x642450 -> 0x120780). Both addresses land mid-instruction, so the
note is a bad anchor; this walks backward to the nearest function boundary and
disassembles forward.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_trace_sites import sections, read_va  # noqa: E402

IMAGE = Path(r'D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data\ra3_1.13.game')
IMAGE_BASE = 0x400000


def nearest_start(blob, secs, va, window=0x400):
    """Largest address <= va (within window) whose preceding byte is a
    terminator (C3/C2/CC/int3 padding/90 padding) or which follows 4+ CC."""
    best = va - window
    for cand in range(va - 1, va - window, -1):
        prev = read_va(blob, secs, cand - 1, 4)[0]
        if prev is None:
            continue
        p0 = prev[0]
        if p0 in (0xC3, 0xCB, 0xCC) or (p0 == 0xC2):
            return cand
        if prev[:4] == b'\xCC\xCC\xCC\xCC':
            return cand
    return best


def main():
    blob = IMAGE.read_bytes()
    secs = sections(blob)
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)

    for va in (0x647300, 0x642450, 0x120780):
        code, sec = read_va(blob, secs, va, 8)
        print(f'\n===== anchor 0x{va:X} (section {sec}) bytes {code.hex(" ") if code else None} =====')
        if sec == '.rdata':
            print('  -> .rdata, not code. Treat as data/vtable slot, not a function.')
            continue
        start = nearest_start(blob, secs, va)
        print(f'  nearest plausible function start: 0x{start:X}  (anchor is +0x{va - start:X} inside)')
        code, _ = read_va(blob, secs, start, 0x180)
        for ins in md.disasm(code, start):
            mark = '   <== features.json anchor' if ins.address == va else ''
            print(f'  {ins.address:#010x}  {ins.bytes.hex(" "):<22} {ins.mnemonic} {ins.op_str}{mark}')
            if ins.mnemonic.startswith('ret') or ins.mnemonic == 'int3':
                break


if __name__ == '__main__':
    main()
