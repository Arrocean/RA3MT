"""Read-only: what does the placement manager's box actually contain, and is the
percell AABB a coarse pre-filter or the real permission test?

- manager object [0xCF2410] (1.13), array head/tail at +0x54/+0x58, stride 0x10,
  integers scaled by the float at .rdata 0xBED704
- vt+0x38 (0x5F07D0) = AABB of that array
- percell PASS path: playerRoot -> 0x8627D0 -> 0xB34740 (permission query?)
"""
import ctypes
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_trace_sites import sections  # noqa: E402

k32 = ctypes.windll.kernel32
PID = int(sys.argv[1]) if len(sys.argv) > 1 else 38552
BASE = 0x400000
IMAGE = Path(r'D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data\ra3_1.13.game')


def rd(h, va, n):
    buf = ctypes.create_string_buffer(n)
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(va), buf, n, ctypes.byref(got)):
        return None
    return buf.raw[:got.value]


def read(blob, secs, va, n):
    rva = va - BASE
    for name, sva, vs, raw, rs in secs:
        if sva <= rva < sva + max(vs, rs):
            return blob[raw + (rva - sva): raw + (rva - sva) + n]
    return None


def main():
    h = k32.OpenProcess(0x0410, False, PID)
    blob = IMAGE.read_bytes()
    secs = sections(blob)
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)

    scale = struct.unpack('<f', read(blob, secs, 0xBED704, 4))[0]
    print(f'.rdata 0xBED704 scaling constant = {scale!r}  (0x{struct.unpack("<I", read(blob, secs, 0xBED704, 4))[0]:08X})')

    mgr = struct.unpack('<I', rd(h, 0xCF2410, 4))[0]
    print(f'manager [0xCF2410] = 0x{mgr:X}')
    hdr = rd(h, mgr, 0x80)
    print('  manager head 0x00..0x7F:')
    for off in range(0, 0x80, 16):
        u = ' '.join(f'{struct.unpack_from("<I", hdr, off + k)[0]:08X}' for k in (0, 4, 8, 12))
        print(f'    +0x{off:02X}  {hdr[off:off+16].hex(" ")}  | {u}')

    beg = struct.unpack_from('<I', hdr, 0x54)[0]
    end = struct.unpack_from('<I', hdr, 0x58)[0]
    print(f'\n  array begin [+0x54] = 0x{beg:X}   end [+0x58] = 0x{end:X}   '
          f'count = {(end - beg) // 0x10}')
    if 0x10000 < beg < 0x7FFF0000 and end > beg and (end - beg) < 0x20000:
        n = min((end - beg) // 0x10, 24)
        data = rd(h, beg, n * 0x10)
        if data:
            print(f'  first {n} records (4 ints each, stride 0x10):')
            for i in range(n):
                rec = struct.unpack_from('<4i', data, i * 0x10)
                scaled = tuple(round(v * scale, 3) for v in rec)
                print(f'    [{i}] raw {rec}  scaled {scaled}')
    else:
        print('  (array not readable / empty)')

    print('\n===== percell PASS: 0x8627D0 and 0xB34740 =====')
    for va, n in ((0x8627D0, 0x50), (0xB34740, 0x90)):
        code = read(blob, secs, va, n)
        if not code:
            print(f'  0x{va:X}: not mapped')
            continue
        print(f'  --- 0x{va:X} ---')
        for ins in md.disasm(code, va):
            print(f'    {ins.address:#010x}  {ins.bytes.hex(" "):<22} {ins.mnemonic} {ins.op_str}')
            if ins.mnemonic.startswith('ret'):
                break


if __name__ == '__main__':
    main()
