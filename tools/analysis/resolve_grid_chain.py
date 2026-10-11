"""Read-only: the accessor at 0xB34740 loads [0xCEC450] and uses +0x28 as the
grid. Resolve that chain properly (the grid may hang off playerRoot, not the
manager) and print the real layout.
"""
import ctypes
import struct
import sys

k32 = ctypes.windll.kernel32
PID = int(sys.argv[1]) if len(sys.argv) > 1 else 38552


def rd(h, va, n):
    buf = ctypes.create_string_buffer(n)
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(va), buf, n, ctypes.byref(got)):
        return None
    return buf.raw[:got.value]


def u32(h, va):
    b = rd(h, va, 4)
    return struct.unpack('<I', b)[0] if b and len(b) == 4 else None


def show(h, va, label, size=0x50):
    raw = rd(h, va, size)
    print(f'\n--- {label} 0x{va:X} ---')
    if raw is None:
        print('   unreadable')
        return
    for off in range(0, size, 16):
        vals = ' '.join(f'{struct.unpack_from("<I", raw, off + k)[0]:08X}' for k in (0, 4, 8, 12))
        print(f'   +0x{off:02X}  {raw[off:off+16].hex(" ")}  | {vals}')


def main():
    h = k32.OpenProcess(0x0410, False, PID)

    chain = [('global 0xCEC450', 0xCEC450), ('global 0xCF214C playerRoot', 0xCF214C),
             ('global 0xCE21CC ThePlacementGrid', 0xCE21CC),
             ('global 0xCF2410 placement manager', 0xCF2410)]
    for label, ga in chain:
        v = u32(h, ga)
        print(f'{label:<34} = {("0x%X" % v) if v else None}')

    root = u32(h, 0xCF214C)
    holder = u32(h, 0xCEC450)
    grid_a = u32(h, holder + 0x28)
    print(f'\n[0xCEC450]+0x28 = 0x{grid_a:X}  (the address 0xB34740 hands to 0xB336E0)')

    for label, va in (('playerRoot', root),
                      ('playerRoot+0x28 (side)', u32(h, root + 0x28) if root else 0),
                      ('[0xCEC450]', holder),
                      ('[0xCEC450]+0x28 (grid candidate)', grid_a)):
        if va and va > 0x10000:
            show(h, va, label, 0x50 if 'grid' not in label else 0x60)

    if grid_a and grid_a > 0x10000:
        vals = [u32(h, grid_a + off) for off in (0x04, 0x08, 0x0C, 0x38, 0x3C, 0x40, 0x44)]
        fl = [struct.unpack('<f', rd(h, grid_a + off, 4))[0] for off in (0x38,)]
        print(f'\n  grid candidate fields: +04={vals[0]} +08={vals[1]} +0C={vals[2]} '
              f'+38f={fl[0]} +3C={vals[4]} +40={vals[5]} +44=0x{vals[6]:X}')
        print(f'  -> cells {vals[4]}x{vals[5]}, data 0x{vals[6]:X}, '
              f'{vals[4]*vals[5]*0x34/1048576:.2f} MB')


if __name__ == '__main__':
    main()
