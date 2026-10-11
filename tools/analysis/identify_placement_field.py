"""Read-only: identify the object the trainer treats as "placementDistance".

Reads the pointer chain from the .data global and dumps the object header so we
can tell whether [obj+0xC] is really a distance/radius field or unrelated data.
Also locates ThePlacementGrid and the local-controller chain.
"""
import ctypes
import ctypes.wintypes as wt
import struct
import sys

k32 = ctypes.windll.kernel32
PID = int(sys.argv[1]) if len(sys.argv) > 1 else 38552

GLOBALS = {
    'placementDistance 1.13': 0x8F2CAC,
    'placementDistance 1.12': 0x8EE98C,
    'playerRoot 1.13': 0x8F214C,
    'ThePlacementGrid 1.13': 0xCE21CC,
    'regionGlobal 0xCF30F0': 0xCF30F0,
    'protoCool / CE21A4': 0xCE21A4,
    'CECF24 (0x64C970 reads)': 0xCECF24,
    'CED2E0 (0x818A00 reads)': 0xCED2E0,
    'C2CF48 (StructurePlacementBehavior vt)': 0xC2CF48,
    'C2CE18 (StructurePlacementBehavior vt)': 0xC2CE18,
    'region vt 0xC2CF48+? 0xC2CE18': 0xC2CE18,
}


def open_proc():
    h = k32.OpenProcess(0x0410, False, PID)
    if not h:
        raise SystemExit(f'OpenProcess({PID}) failed')
    return h


def rd(h, va, n):
    buf = ctypes.create_string_buffer(n)
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(va), buf, n, ctypes.byref(got)):
        return None
    return buf.raw[:got.value]


def u32(h, va):
    b = rd(h, va, 4)
    return struct.unpack('<I', b)[0] if b and len(b) == 4 else None


def f32(h, va):
    b = rd(h, va, 4)
    return struct.unpack('<f', b)[0] if b and len(b) == 4 else None


def main():
    h = open_proc()
    print(f'--- globals (PID {PID}) ---')
    for name, va in GLOBALS.items():
        v = u32(h, va)
        print(f'  [{name}] 0x{va:X} = {("0x%X" % v) if v is not None else "unreadable"}')

    for name, va in (('placementDistance 1.13', 0x8F2CAC), ('placementDistance 1.12', 0x8EE98C)):
        obj = u32(h, va)
        print(f'\n--- {name}: [0x{va:X}] = 0x{obj:X} ---' if obj else f'\n--- {name}: null ---')
        if not obj or obj < 0x10000:
            continue
        head = rd(h, obj, 0x40)
        print(f'  bytes: {head.hex(" ")}')
        print('  dwords: ' + ' '.join(f'{struct.unpack_from("<I", head, i)[0]:08X}' for i in range(0, 0x40, 4)))
        print('  floats: ' + ' '.join(f'{struct.unpack_from("<f", head, i)[0]:.4g}' for i in range(0, 0x40, 4)))
        print(f'  [obj+0x0C] = {f32(h, obj + 0xC)}   raw {rd(h, obj + 0xC, 4).hex(" ")}')

    # who does [0x8F2CAC] point at -- is the object tagged like a GameData? look
    # for a vtable-looking first dword inside .rdata
    obj = u32(h, 0x8F2CAC)
    if obj and obj > 0x10000:
        vt = u32(h, obj)
        print(f'\n  [0x8F2CAC] object first dword (maybe vtable) = 0x{vt:X} '
              f'{"(.rdata range)" if vt and 0x7CE000 <= vt < 0x8B3000 else ""}')

    # ThePlacementGrid singleton structure
    grid = u32(h, 0xCE21CC)
    if grid and grid > 0x10000:
        g = rd(h, grid, 0x60)
        print(f'\n--- ThePlacementGrid 0x{grid:X} ---')
        print(f'  bytes: {g.hex(" ")}')
        print('  dwords: ' + ' '.join(f'{struct.unpack_from("<I", g, i)[0]:08X}' for i in range(0, 0x60, 4)))
        gv = u32(h, grid)
        if gv and 0x7CE000 <= gv < 0x8B6000:
            slots = [u32(h, gv + i * 4) for i in range(24)]
            print(f'  vtable 0x{gv:X}: ' + ' '.join(f'{s:08X}' for s in slots))

    # search .data for the float 90.0 and 300.0 near our globals
    print('\n--- float scan in .data (0x8B3000..0x939000) for 90.0 / 300.0 / 100000.0 ---')
    base, size = 0x8B3000, 0x85EC0
    chunk = 0x10000
    for want, label in ((90.0, '90.0'), (300.0, '300.0'), (100000.0, '100000.0')):
        pat = struct.pack('<f', want)
        found = []
        off = 0
        while off < size:
            n = min(chunk, size - off)
            data = rd(h, base + off, n)
            if not data:
                break
            i = 0
            while True:
                i = data.find(pat, i)
                if i < 0:
                    break
                found.append(base + off + i)
                i += 1
            off += n - 3
        print(f'  {label}: {len(found)} hits' + ('' if not found else '  e.g. ' +
              ' '.join(f'0x{a:X}' for a in found[:10])))
        for a in found[:6]:
            around = rd(h, a - 16, 0x30)
            if around:
                print(f'    0x{a:X}: -16.. {around.hex(" ")}')


if __name__ == '__main__':
    main()
