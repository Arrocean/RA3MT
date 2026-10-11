"""Read-only: map the live module layout (VirtualQueryEx) and re-read the
documented globals, so we can tell whether the RVA -> VA assumption holds.
"""
import ctypes
import ctypes.wintypes as wt
import struct
import sys

k32 = ctypes.windll.kernel32
PID = int(sys.argv[1]) if len(sys.argv) > 1 else 38552
BASE = 0x400000


class MBI(ctypes.Structure):
    _fields_ = [('BaseAddress', ctypes.c_void_p), ('AllocationBase', ctypes.c_void_p),
                ('AllocationProtect', wt.DWORD), ('RegionSize', ctypes.c_size_t),
                ('State', wt.DWORD), ('Protect', wt.DWORD), ('Type', wt.DWORD)]


def rd(h, va, n):
    buf = ctypes.create_string_buffer(n)
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(va), buf, n, ctypes.byref(got)):
        return None
    return buf.raw[:got.value]


def main():
    h = k32.OpenProcess(0x0410, False, PID)
    if not h:
        raise SystemExit('OpenProcess failed')

    print('--- module regions (type=IMAGE) around 0x400000..0x950000 ---')
    addr = 0x400000
    mbi = MBI()
    while addr < 0x960000:
        if not k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
            break
        size = mbi.RegionSize
        if mbi.Type == 0x1000000 and mbi.State == 0x1000:
            print(f'  0x{mbi.BaseAddress or 0:X}-0x{(mbi.BaseAddress or 0)+size:X}  '
                  f'size 0x{size:X}  prot 0x{mbi.Protect:X}')
        addr = (mbi.BaseAddress or addr) + size
        if addr <= 0x400000:
            break

    print('\n--- documented globals ---')
    for name, rva in (('selectionList 1.13', 0x8E4BFC), ('playerRoot 1.13', 0x8F214C),
                      ('placementDistance 1.13', 0x8F2CAC), ('ThePlacementGrid 1.13', 0xCE21CC)):
        va = BASE + rva
        raw = rd(h, va, 8)
        print(f'  {name}: VA 0x{va:X} -> {raw.hex(" ") if raw else "unreadable"}'
              + (f'  (u32 0x{struct.unpack("<I", raw[:4])[0]:X})' if raw else ''))

    print('\n--- end of .data per disk image vs live bytes ---')
    for probe in (0x938000, 0x938E00, 0x939000, 0x93A000):
        raw = rd(h, probe, 8)
        print(f'  0x{probe:X}: {raw.hex(" ") if raw else "unreadable"}')


if __name__ == '__main__':
    main()
