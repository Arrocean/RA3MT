"""Read-only deep probe of the "placementDistance" global chain.

Reads field by field (a single 0x40-byte read fails if any page in range is
unreadable), then scans the whole address space for 4-byte values equal to the
object pointer, to see who actually holds it.
"""
import ctypes
import ctypes.wintypes as wt
import struct
import sys

k32 = ctypes.windll.kernel32
PID = int(sys.argv[1]) if len(sys.argv) > 1 else 38552
BASE = 0x400000
GVA = BASE + 0x8F2CAC


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


def region_of(h, va):
    mbi = MBI()
    if not k32.VirtualQueryEx(h, ctypes.c_void_p(va), ctypes.byref(mbi), ctypes.sizeof(mbi)):
        return None
    return mbi


def main():
    h = k32.OpenProcess(0x0410, False, PID)
    if not h:
        raise SystemExit('OpenProcess failed')

    raw = rd(h, GVA, 4)
    obj = struct.unpack('<I', raw)[0]
    print(f'[0x{GVA:X}] = 0x{obj:X}')
    mbi = region_of(h, obj)
    if mbi:
        print(f'  region 0x{mbi.BaseAddress or 0:X} size 0x{mbi.RegionSize:X} '
              f'prot 0x{mbi.Protect:X} type 0x{mbi.Type:X} alloc 0x{mbi.AllocationBase or 0:X}')

    print(f'\n--- object 0x{obj:X} fields ---')
    ok = 0
    for off in range(0, 0x80, 4):
        b = rd(h, obj + off, 4)
        if b is None:
            print(f'  +0x{off:02X}: <unreadable>')
            continue
        ok += 1
        u = struct.unpack('<I', b)[0]
        f = struct.unpack('<f', b)[0]
        tag = ''
        if 0x7CE000 <= u < 0x8B3000:
            tag = '  <- .rdata (vtable/const)'
        elif 0x400000 <= u < 0xD0C000:
            tag = '  <- in module image'
        elif u > 0x10000:
            r = region_of(h, u)
            if r:
                tag = f'  -> prot 0x{r.Protect:X} type 0x{r.Type:X}'
        print(f'  +0x{off:02X}: {u:08X}  float {f:>14.6g}{tag}')
    print(f'  ({ok}/32 fields readable)')

    print('\n--- who else holds a pointer to this object? (full address-space scan) ---')
    pat = struct.pack('<I', obj)
    addr = 0x10000
    hits = []
    mbi = MBI()
    scanned = 0
    while addr < 0x7FFF0000 and len(hits) < 40:
        if not k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
            break
        base = mbi.BaseAddress or addr
        size = mbi.RegionSize
        prot = mbi.Protect
        readable = (mbi.State == 0x1000 and not (prot & 0x100)
                    and (prot & 0xEE) != 0 and prot != 0x01)
        if readable and size <= 0x4000000:
            buf = rd(h, base, size)
            if buf:
                scanned += len(buf)
                i = 0
                while True:
                    i = buf.find(pat, i)
                    if i < 0:
                        break
                    hits.append(base + i)
                    i += 1
                    if len(hits) >= 40:
                        break
        addr = base + size
    print(f'  scanned {scanned/1048576:.0f} MB, {len(hits)} hits')
    for a in hits[:40]:
        r = region_of(h, a)
        kind = ''
        if r and r.Type == 0x1000000:
            kind = ' [module image]'
            kind += f' RVA 0x{a - BASE:X}' if BASE <= a < BASE + 0xD0C000 else ''
        elif r and r.Type == 0x20000:
            kind = ' [private/heap]'
        print(f'    0x{a:X}{kind}')


if __name__ == '__main__':
    main()
