"""Read-only: histogram the REAL buildability grid ([0xCEC450]+0x28, 125x140
cells, stride 0x34, data at +0x44).

cell layout observed: word [+0x04] = state (0 empty / 0xFFFF global default /
other = covered), byte [+0x32] = block flag.

If the state words are non-zero around bases at rest, the buildability data is
persistent and readable without a placement attempt -> "build anywhere" can be a
data patch. If everything is zero at rest, it is computed on demand.
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


def main():
    h = k32.OpenProcess(0x0410, False, PID)
    if not h:
        raise SystemExit('OpenProcess failed')

    holder = u32(h, 0xCEC450)
    grid = u32(h, holder + 0x28)
    origin = struct.unpack('<ff', rd(h, grid + 4, 8))
    scale = struct.unpack('<f', rd(h, grid + 0x38, 4))[0]
    w, ht = u32(h, grid + 0x3C), u32(h, grid + 0x40)
    data = u32(h, grid + 0x44)
    print(f'grid 0x{grid:X}  origin=({origin[0]}, {origin[1]})  scale={scale} '
          f'({1/scale:.1f} world units/cell)')
    print(f'  width={w} height={ht} cells={w*ht} data=0x{data:X} '
          f'({w*ht*0x34/1048576:.2f} MB)')

    total = w * ht
    word = collections.Counter()
    byte32 = collections.Counter()
    byte33 = collections.Counter()
    nonzero_cells = []
    raw_all = rd(h, data, total * 0x34)
    if raw_all is None:
        print('  full read failed; chunking')
        raw_all = b''.join(rd(h, data + i * 0x34, 0x34) or b'\x00' * 0x34 for i in range(total))
    for i in range(total):
        off = i * 0x34
        wv = struct.unpack_from('<H', raw_all, off + 4)[0]
        word[wv] += 1
        byte32[raw_all[off + 0x32]] += 1
        byte33[raw_all[off + 0x33]] += 1
        if wv != 0:
            nonzero_cells.append((i % w, i // w, wv))

    print(f'\n--- state word [+0x04] histogram ({len(word)} distinct) ---')
    for v, c in word.most_common(10):
        print(f'  0x{v:04X} : {c:>7} cells ({c*100.0/total:6.2f}%)')
    print(f'  non-zero cells: {len(nonzero_cells)}')
    if nonzero_cells:
        xs = [c[0] for c in nonzero_cells]
        ys = [c[1] for c in nonzero_cells]
        print(f'  bounding box of non-zero cells: x {min(xs)}..{max(xs)}  y {min(ys)}..{max(ys)}')
        print('  first 12: ' + ' '.join(f'({x},{y})=0x{v:04X}' for x, y, v in nonzero_cells[:12]))

    print(f'\n--- block byte [+0x32] histogram ---')
    for v, c in byte32.most_common(8):
        print(f'  0x{v:02X} : {c:>7} cells ({c*100.0/total:6.2f}%)')
    print(f'--- byte [+0x33] histogram ---')
    for v, c in byte33.most_common(8):
        print(f'  0x{v:02X} : {c:>7} cells ({c*100.0/total:6.2f}%)')

    print('\n--- sample cells: map centre, and a corner ---')
    for idx, label in ((total // 2, 'centre'), (0, 'origin'), (total - 1, 'last')):
        raw = raw_all[idx * 0x34:(idx + 1) * 0x34]
        print(f'  {label:<8} #{idx:<6} {raw.hex(" ")}')


if __name__ == '__main__':
    main()
