"""Read-only: is the "90.0" config block that [0xCF2CAC] points at unique, or one
of several copies (one per side/player/difficulty)? Also dump its neighbours.
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
    obj = struct.unpack('<I', rd(h, BASE + 0x8F2CAC, 4))[0]
    print(f'config block [0x{BASE + 0x8F2CAC:X}] = 0x{obj:X}')

    print('\n--- the block with context (0x{0:X}-0x{1:X}) ---'.format(obj - 0x40, obj + 0x100))
    buf = rd(h, obj - 0x40, 0x140)
    for off in range(0, 0x140, 16):
        chunk = buf[off:off + 16]
        u = ' '.join(f'{struct.unpack_from("<I", chunk, k)[0]:08X}' for k in (0, 4, 8, 12))
        f = ' '.join(f'{struct.unpack_from("<f", chunk, k)[0]:>10.4g}' for k in (0, 4, 8, 12))
        print(f'  {obj - 0x40 + off:08X}  {chunk.hex(" ")}  | {u} | {f}')

    # full scan for the byte signature of the block head: block_self_ptr, 3f, 4f, 90f
    print('\n--- full address-space scan for the 16-byte head pattern ---')
    head = rd(h, obj, 16)
    pat = head[4:16]        # 3.0, 4.0, 90.0  (skip the self pointer)
    print(f'  pattern (12B): {pat.hex(" ")}')
    addr = 0x10000
    hits = []
    mbi = MBI()
    while addr < 0x7FFF0000:
        if not k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
            break
        b = mbi.BaseAddress or addr
        size = mbi.RegionSize
        prot = mbi.Protect
        readable = (mbi.State == 0x1000 and not (prot & 0x100) and (prot & 0xEE) != 0
                    and prot != 0x01 and size <= 0x4000000)
        if readable:
            chunk = rd(h, b, size)
            if chunk:
                i = 0
                while True:
                    i = chunk.find(pat, i)
                    if i < 0:
                        break
                    hits.append(b + i - 4)
                    i += 1
        addr = b + size
    print(f'  {len(hits)} candidate block heads')
    for a in hits[:20]:
        own = rd(h, a, 4)
        self_ref = struct.unpack('<I', own)[0] if own else 0
        note = ' (points to itself+0x38)' if self_ref == a + 0x38 else f' (first dword 0x{self_ref:X})'
        print(f'    0x{a:X}{note}')
    # how many float 90.0 exist at all
    n90 = 0
    addr = 0x10000
    p90 = struct.pack('<f', 90.0)
    while addr < 0x7FFF0000:
        if not k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
            break
        b = mbi.BaseAddress or addr
        size = mbi.RegionSize
        prot = mbi.Protect
        readable = (mbi.State == 0x1000 and not (prot & 0x100) and (prot & 0xEE) != 0
                    and prot != 0x01 and size <= 0x4000000)
        if readable:
            chunk = rd(h, b, size)
            if chunk:
                n90 += chunk.count(p90)
        addr = b + size
    print(f'\n  total 90.0f float slots in the process: {n90}')


if __name__ == '__main__':
    main()
