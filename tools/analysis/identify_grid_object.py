"""Read-only: identify the real grid object behind the cell accessors.

The accessors (0xB32360 / 0xB336E0) treat ECX as an object with:
  +0x04 base pointer, +0x08 origin.x, +0x0C origin.z, +0x38 grid scale,
  +0x3C width, +0x40 height, +0x44 data pointer, stride 0x34 per cell.
They are reached from 0xB34740 via [0xCEC450]; 0x8627D0 reads [playerRoot+0x28]+0x28.
Resolve all of those and print the layout.
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


def u32(h, va):
    b = rd(h, va, 4)
    return struct.unpack('<I', b)[0] if b and len(b) == 4 else None


def dump_obj(h, va, label, size=0x60):
    print(f'\n===== {label} 0x{va:X} =====')
    raw = rd(h, va, size)
    if raw is None:
        print('  unreadable')
        return
    for off in range(0, size, 16):
        ints = ' '.join(f'{struct.unpack_from("<i", raw, off + k)[0]:>11}' for k in (0, 4, 8, 12))
        print(f'  +0x{off:02X}  {raw[off:off+16].hex(" ")}  | {ints}')
    for off in (0x04, 0x08, 0x0C, 0x38, 0x3C, 0x40, 0x44):
        b = rd(h, va + off, 4)
        if b:
            print(f'    [+0x{off:02X}] i32={struct.unpack("<i", b)[0]:>12}  '
                  f'f32={struct.unpack("<f", b)[0]:.6g}')


def main():
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    blob = IMAGE.read_bytes()
    secs = sections(blob)

    h = k32.OpenProcess(0x0410, False, PID)
    root = u32(h, 0xCF214C)
    print(f'playerRoot [0xCF214C] = 0x{root:X}')
    if root:
        dump_obj(h, root, 'playerRoot object')

    print('\n===== 0x8627D0 (what percell dereferences first) =====')
    code = read(blob, secs, 0x8627D0, 0x40)
    for ins in md.disasm(code, 0x8627D0):
        print(f'  {ins.address:#010x}  {ins.bytes.hex(" "):<22} {ins.mnemonic} {ins.op_str}')
        if ins.mnemonic.startswith('ret'):
            break

    g1 = u32(h, 0xCEC450)
    print(f'\n[0xCEC450] = {("0x%X" % g1) if g1 else None}')
    if g1 and g1 > 0x10000:
        dump_obj(h, g1, '[0xCEC450] object')
        g2 = u32(h, g1 + 0x28)
        print(f'\n  [+0x28] = {("0x%X" % g2) if g2 else None}')
        if g2 and g2 > 0x10000:
            dump_obj(h, g2, '[0xCEC450]+0x28 (candidate grid)')
            w = u32(h, g2 + 0x3C)
            ht = u32(h, g2 + 0x40)
            data = u32(h, g2 + 0x44)
            scale = struct.unpack('<f', rd(h, g2 + 0x38, 4))[0] if rd(h, g2 + 0x38, 4) else None
            print(f'\n  width={w} height={ht} data=0x{data:X} scale={scale}')
            if w and ht and w < 20000 and ht < 20000 and data and 0x10000 < data < 0x7FFF0000:
                print(f'  cells={w*ht} bytes={w*ht*0x34}')


if __name__ == '__main__':
    main()
