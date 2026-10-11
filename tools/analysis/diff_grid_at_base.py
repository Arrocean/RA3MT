"""Read-only: is the grid the BUILDABILITY field, or just terrain classification?

Take the player's own live objects (walked from the side pointer exactly like the
trainer's discovery code does), convert their world positions into grid cells via
the grid's own origin/scale, and compare the cell contents there against cells
far away. A buildability field must diverge around the base.
"""
import collections
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


def f32(h, va):
    b = rd(h, va, 4)
    return struct.unpack('<f', b)[0] if b and len(b) == 4 else None


def main():
    h = k32.OpenProcess(0x0410, False, PID)
    holder = u32(h, 0xCEC450)
    grid = u32(h, holder + 0x28)
    ox, oz = struct.unpack('<ff', rd(h, grid + 4, 8))
    scale = struct.unpack('<f', rd(h, grid + 0x38, 4))[0]
    w, ht = u32(h, grid + 0x3C), u32(h, grid + 0x40)
    data = u32(h, grid + 0x44)
    print(f'grid 0x{grid:X} origin=({ox}, {oz}) scale={scale} size={w}x{ht} data=0x{data:X}')
    raw = rd(h, data, w * ht * 0x34)

    def cell(x, z):
        cx = int((x - ox) * scale)
        cy = int((z - oz) * scale)
        if not (0 <= cx < w and 0 <= cy < ht):
            return None, None, None
        i = cy * w + cx
        rec = raw[i * 0x34:(i + 1) * 0x34]
        if len(rec) < 0x34:
            return cx, cy, None
        return cx, cy, rec

    # side graph -> own objects (same walk as the trainer's discovery code)
    root = u32(h, 0xCF214C)
    side = u32(h, root + 0x28) if root else None
    print(f'playerRoot 0x{root:X} side 0x{side:X}')
    bodies = []
    if side:
        # breadth-first walk: collect objects whose [+0x418] == side
        seen = set()
        queue = [side]
        while queue and len(seen) < 4000:
            node = queue.pop()
            if node in seen or not (0x10000 < node < 0x7FFF0000):
                continue
            seen.add(node)
            node_side = u32(h, node + 0x418)
            x, z = f32(h, node + 0x38), f32(h, node + 0x40)
            if node_side == side and x is not None and z is not None and abs(x) < 100000 and abs(z) < 100000:
                bodies.append((node, x, z))
            blk = rd(h, node, 0x100)
            if blk:
                for off in range(0, 0x100, 4):
                    v = struct.unpack_from('<I', blk, off)[0]
                    if 0x10000 < v < 0x7FFF0000 and (v & 3) == 0:
                        queue.append(v)
        print(f'  found {len(bodies)} candidate own objects')

    print('\n--- cells at own-object positions ---')
    near_word = collections.Counter()
    found = 0
    for node, x, z in bodies[:20]:
        cx, cy, rec = cell(x, z)
        if rec is None:
            continue
        found += 1
        words = struct.unpack_from('<16H', rec, 4)
        print(f'  0x{node:X} world=({x:8.1f},{z:8.1f}) cell=({cx:3},{cy:3}) '
              f'words[0..15]={[hex(v) for v in words]}')
        near_word[words[0]] += 1
    print(f'  ({found} objects mapped into the grid)')
    if near_word:
        print('  first-word histogram at object positions: ' +
              ' '.join(f'{hex(k)}:{v}' for k, v in near_word.most_common()))

    print('\n--- reference cells far from any object ---')
    for label, (x, z) in (('origin corner', (ox + 10, oz + 10)),
                          ('map centre', (ox + (w / scale) / 2, oz + (ht / scale) / 2)),
                          ('far corner', (ox + (w / scale) - 10, oz + (ht / scale) - 10))):
        cx, cy, rec = cell(x, z)
        if rec is None:
            print(f'  {label}: out of grid')
            continue
        words = struct.unpack_from('<16H', rec, 4)
        print(f'  {label:<14} cell=({cx:3},{cy:3}) words[0..15]={[hex(v) for v in words]}')


if __name__ == '__main__':
    main()
