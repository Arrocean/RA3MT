"""Read-only: who reads the placement-distance config block?

The block lives at 0x133CC3D0 (+0xC = 90.0) and exactly one pointer to it exists
(the .data global 0xCF2CAC). If the game consumes it, some instruction must
either load [0xCF2CAC] or embed an absolute address in the block's range.
"""
import ctypes
import ctypes.wintypes as wt
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_trace_sites import sections  # noqa: E402

k32 = ctypes.windll.kernel32
PID = int(sys.argv[1]) if len(sys.argv) > 1 else 38552
IMAGE = Path(r'D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data\ra3_1.13.game')
BASE = 0x400000


def rd(h, va, n):
    buf = ctypes.create_string_buffer(n)
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(va), buf, n, ctypes.byref(got)):
        return None
    return buf.raw[:got.value]


def main():
    h = k32.OpenProcess(0x0410, False, PID)
    obj = struct.unpack('<I', rd(h, BASE + 0x8F2CAC, 4))[0]
    lo, hi = obj - 0x400, obj + 0x1800
    print(f'block 0x{obj:X}; scanning module image for absolute operands in '
          f'[0x{lo:X}, 0x{hi:X}) and for the global 0x{BASE + 0x8F2CAC:X}')

    blob = IMAGE.read_bytes()
    secs = sections(blob)
    text = [(n, sva, raw, min(vs, rs)) for n, sva, vs, raw, rs in secs if n == '.text']
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)

    hits = []
    for name, sva, raw, size in text:
        data = blob[raw:raw + size]
        for i in range(0, len(data) - 4):
            v = struct.unpack_from('<I', data, i)[0]
            if lo <= v < hi:
                hits.append((BASE + sva + i, v))
    print(f'\n{len(hits)} absolute-operand candidates in .text')
    seen = set()
    for va, v in hits:
        # disassemble a window starting a few bytes before so the instruction lines up
        for back in range(0, 7):
            start = va - back
            rva = start - BASE
            code = None
            for name, sva, raw, size in text:
                if sva <= rva < sva + size:
                    code = blob[raw + (rva - sva): raw + (rva - sva) + 24]
                    break
            if not code:
                continue
            ins = next(iter(md.disasm(code, start)), None)
            if ins and ins.size > back and struct.pack('<I', v) in ins.bytes:
                key = (ins.address, ins.bytes)
                if key in seen:
                    break
                seen.add(key)
                print(f'  0x{ins.address:X}  {ins.bytes.hex(" "):<24} {ins.mnemonic} {ins.op_str}')
                # context: next 3 instructions
                rva2 = ins.address + ins.size - BASE
                code2 = blob[raw + (rva2 - sva): raw + (rva2 - sva) + 40]
                for k, nxt in enumerate(md.disasm(code2, ins.address + ins.size)):
                    if k >= 4:
                        break
                    print(f'        {nxt.address:#010x}  {nxt.bytes.hex(" "):<20} {nxt.mnemonic} {nxt.op_str}')
                break

    print('\n--- disassemble the function that owns [0xCF2CAC] usage, if any ---')
    gva = BASE + 0x8F2CAC
    pat = struct.pack('<I', gva)
    for name, sva, raw, size in text:
        data = blob[raw:raw + size]
        i = 0
        while True:
            i = data.find(pat, i)
            if i < 0:
                break
            print(f'  operand at RVA 0x{sva + i:X} (VA 0x{BASE + sva + i:X})')
            i += 1
    print('  (no output above = the global is never referenced by an immediate)')


if __name__ == '__main__':
    main()
