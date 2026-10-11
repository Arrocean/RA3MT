"""Read-only: try to find any code path that consumes the placement-distance
value at [0x8F2CAC]->(+0xC).

Strategy: the pointer is only ever stored at 0xCF2CAC, so a consumer must
a) load [0xCF2CAC] with an absolute operand,
b) get the pointer as a struct field (requires step a somewhere), or
c) index through a global array/vtable in .rdata whose entries point at the
   block.

We check (a) exactly, (c) by scanning .rdata/.data for the live object pointer,
and cross-check the scanner against a known constant (0xCF30F0, referenced at
0x5F0933) to prove the method works.
"""
import ctypes
import struct
import sys
from pathlib import Path

k32 = ctypes.windll.kernel32
PID = int(sys.argv[1]) if len(sys.argv) > 1 else 38552
BASE = 0x400000
IMAGE = Path(r'D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data\ra3_1.13.game')

SECS = [('.text', 0x1000, 0x7CCB0A, 0x1000, 0x7CD000),
        ('.rdata', 0x7CE000, 0xE4C1A, 0x7CE000, 0xE5000),
        ('.data', 0x8B3000, 0x85EC0, 0x8B3000, 0x2B000)]


def rd(h, va, n):
    buf = ctypes.create_string_buffer(n)
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(va), buf, n, ctypes.byref(got)):
        return None
    return buf.raw[:got.value]


def scan(data, pat, label):
    hits = []
    i = 0
    while True:
        i = data.find(pat, i)
        if i < 0:
            break
        hits.append(i)
        i += 1
    print(f'  {label}: {len(hits)} hits')
    return hits


def main():
    disk = IMAGE.read_bytes()
    h = k32.OpenProcess(0x0410, False, PID)
    obj = struct.unpack('<I', rd(h, BASE + 0x8F2CAC, 4))[0]
    print(f'live block pointer = 0x{obj:X}')

    print('\n[control] does the scanner see the known constant 0xCF30F0 in .text?')
    ctrl = struct.pack('<I', 0xCF30F0)
    rva, vs, raw, rs = SECS[0][1], SECS[0][2], SECS[0][3], SECS[0][4]
    text = disk[raw:raw + vs]
    hits = scan(text, ctrl, '0xCF30F0 in disk .text')
    for off in hits[:5]:
        print(f'     VA 0x{BASE + rva + off:X}  ctx {text[max(0, off - 4):off + 8].hex(" ")}')

    print('\n[a] operand 0x8F2CAC anywhere in .text (disk):')
    glob = struct.pack('<I', 0x8F2CAC)
    for name, sva, vs, raw, rs in SECS:
        data = disk[raw:raw + min(vs, rs)]
        for off in scan(data, glob, f'0x8F2CAC in {name}'):
            print(f'     VA 0x{BASE + sva + off:X}')

    print('\n[b] the live block pointer as a 4-byte value in any section:')
    pat = struct.pack('<I', obj)
    for name, sva, vs, raw, rs in SECS:
        data = disk[raw:raw + min(vs, rs)]
        for off in scan(data, pat, f'0x{obj:X} in {name}'):
            print(f'     VA 0x{BASE + sva + off:X}')

    print('\n[c] .rdata/.data entries pointing anywhere inside the block neighbourhood:')
    lo, hi = obj - 0x2000, obj + 0x2000
    found = 0
    for name, sva, vs, raw, rs in SECS[1:]:
        data = disk[raw:raw + min(vs, rs)]
        for off in range(0, len(data) - 4, 4):
            v = struct.unpack_from('<I', data, off)[0]
            if lo <= v < hi:
                print(f'     {name} VA 0x{BASE + sva + off:X} -> 0x{v:X}')
                found += 1
                if found > 20:
                    break
        if found > 20:
            break
    if not found:
        print('     none')

    print('\n[d] is 90.0 stored in .data/.rdata as a config default? (float scan)')
    p90 = struct.pack('<f', 90.0)
    for name, sva, vs, raw, rs in SECS[1:]:
        data = disk[raw:raw + min(vs, rs)]
        for off in scan(data, p90, f'90.0f in {name}'):
            print(f'     VA 0x{BASE + sva + off:X}  ctx {data[max(0, off - 12):off + 12].hex(" ")}')


if __name__ == '__main__':
    main()
