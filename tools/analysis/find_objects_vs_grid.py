"""Read-only: find live buildings by their template name strings and compare the
grid cells under them against empty ground.

The trainer's own notes established: body+0x3CC -> tracker -> +4 wrapper -> +0x14
template, and the template carries "Name:<Type>" text within ~0x300 bytes. So
scanning readable memory for known structure names tells us where buildings are,
without any clicking.
"""
import collections
import ctypes
import re
import struct
import sys

k32 = ctypes.windll.kernel32
PID = int(sys.argv[1]) if len(sys.argv) > 1 else 38552

NAMES = [b'SovietConstructionYard', b'AlliedConstructionYard', b'JapanConstructionYard',
         b'SovietPowerPlant', b'AlliedPowerPlant', b'JapanPowerPlant',
         b'SovietBarracks', b'AlliedBarracks', b'JapanBarracks', b'SovietRefinery']


def rd(h, va, n):
    buf = ctypes.create_string_buffer(n)
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(va), buf, n, ctypes.byref(got)):
        return None
    return buf.raw[:got.value]


def u32(h, va):
    b = rd(h, va, 4)
    return struct.unpack('<I', b)[0] if b and len(b) == 4 else None


def main():
    h = k32.OpenProcess(0x0410, False, PID)

    # 1) find template name strings
    print('--- scanning for structure template name strings ---')
    hits = {}
    addr = 0x10000
    while addr < 0x7FFF0000 and len(hits) < 40:
        buf = rd(h, addr, 0x100000)
        if buf:
            for nm in NAMES:
                i = buf.find(b'Name:' + nm)
                if i >= 0:
                    hits.setdefault(nm.decode(), []).append(addr + i)
        addr += 0x100000
    for k, v in hits.items():
        print(f'  {k}: {len(v)} hit(s) e.g. ' + ' '.join(f'0x{a:X}' for a in v[:3]))

    # 2) from each template string, walk back to a plausible template base and
    #    read the wrapper chain the notes describe; then read the object position
    print('\n--- trying to resolve objects from the template hits ---')
    grid = u32(h, u32(h, 0xCEC450) + 0x28)
    data = u32(h, grid + 0x44)
    w, ht = u32(h, grid + 0x3C), u32(h, grid + 0x40)
    scale = struct.unpack('<f', rd(h, grid + 0x38, 4))[0]
    ox, oz = struct.unpack('<ff', rd(h, grid + 4, 8))
    raw = rd(h, data, w * ht * 0x34)
    print(f'grid {w}x{ht} origin=({ox},{oz}) scale={scale}')

    def cell_words(x, z):
        cx, cy = int((x - ox) * scale), int((z - oz) * scale)
        if not (0 <= cx < w and 0 <= cy < ht):
            return None
        i = cy * w + cx
        rec = raw[i * 0x34:(i + 1) * 0x34]
        return (cx, cy, struct.unpack_from('<16H', rec, 4))

    # 3) scan the heap for bodies: objects whose +0x38/+0x3C hold sane world floats
    print('\n--- scanning for object positions (bodies with sane +0x38/+0x3C) ---')
    samples = []
    addr = 0x10000
    while addr < 0x7FFF0000 and len(samples) < 6:
        buf = rd(h, addr, 0x200000)
        if buf:
            for off in range(0, len(buf) - 0x420, 4):
                x = struct.unpack_from('<f', buf, off + 0x38)[0]
                z = struct.unpack_from('<f', buf, off + 0x3C)[0]
                if 0 <= x < (w / scale) and 0 <= z < (ht / scale) and x > 50 and z > 50:
                    # require a plausible side pointer at +0x418 within the block
                    if off + 0x41C <= len(buf):
                        side = struct.unpack_from('<I', buf, off + 0x418)[0]
                        if 0x10000 < side < 0x7FFF0000:
                            samples.append((addr + off, x, z))
                            if len(samples) >= 6:
                                break
        addr += 0x200000
    print(f'  {len(samples)} candidate bodies')
    for va, x, z in samples:
        res = cell_words(x, z)
        if res is None:
            print(f'  0x{va:X} ({x:.1f},{z:.1f}) -> outside grid')
            continue
        cx, cy, words = res
        print(f'  0x{va:X} ({x:7.1f},{z:7.1f}) cell=({cx:3},{cy:3}) words={[hex(v) for v in words[:8]]}')


if __name__ == '__main__':
    main()
