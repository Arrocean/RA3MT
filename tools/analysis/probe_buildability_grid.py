"""Read-only: settle whether the per-cell buildability state is PERSISTENT data
(so build-anywhere can be a data patch) or only computed transiently during a
placement attempt.

We know:
  grid object: [0xCE21CC], width +0x3C, height +0x40, data +0x44, stride 0x34
  cell state : word [cell + idx*2 + 4]  (0 = empty, 0xFFFF = global default,
               other = covered by a buildability provider)
  cell block : byte [cell + 0x32]

If the words are non-zero around the player's base and zero far away, the
information is persistent and readable at rest - no placement needed.
"""
import ctypes
import collections
import struct
import sys

k32 = ctypes.windll.kernel32
PID = int(sys.argv[1]) if len(sys.argv) > 1 else 38552
BASE = 0x400000


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
    if not h:
        raise SystemExit('OpenProcess failed')
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(0xCE21CC), ctypes.create_string_buffer(4), 4, None):
        raise SystemExit('unreadable')

    grid = u32(h, 0xCE21CC)
    print(f'ThePlacementGrid [0xCE21CC] = 0x{grid:X}')
    w, ht = u32(h, grid + 0x3C), u32(h, grid + 0x40)
    data = u32(h, grid + 0x44)
    print(f'  width +0x3C = {w}   height +0x40 = {ht}   data +0x44 = 0x{data:X}')
    print(f'  cells = {w * ht}   grid bytes = {w * ht * 0x34} ({w * ht * 0x34 / 1048576:.1f} MB)')
    if not (0x10000 < data < 0x7FFF0000) or w == 0 or ht == 0:
        raise SystemExit('grid not initialised')

    # player base centre for orientation
    root = u32(h, 0xCF214C)
    side = u32(h, root + 0x28) if root else None
    print(f'  playerRoot 0x{root:X}  side 0x{side:X}' if root and side else '  (no player root)')

    print('\n--- full-grid histogram of the state word and the block byte ---')
    total = w * ht
    chunk_cells = 0x8000                      # 32k cells per read
    word_hist = collections.Counter()
    byte_hist = collections.Counter()
    first_nonzero = None
    done = 0
    while done < total:
        n = min(chunk_cells, total - done)
        base_va = data + done * 0x34
        raw = rd(h, base_va, n * 0x34)
        if raw is None:
            # read cell by cell for this chunk
            raw = b''.join(rd(h, base_va + i * 0x34, 0x34) or b'\x00' * 0x34 for i in range(n))
        for i in range(n):
            off = i * 0x34
            wv = struct.unpack_from('<H', raw, off + 4)[0]
            bv = raw[off + 0x32]
            word_hist[wv] += 1
            byte_hist[bv] += 1
            if wv != 0 and first_nonzero is None:
                first_nonzero = done + i
        done += n

    print(f'  state word distinct values: {len(word_hist)}')
    for v, c in word_hist.most_common(12):
        print(f'    0x{v:04X} : {c:>9} cells ({c * 100.0 / total:.2f}%)')
    print(f'  block byte distinct values: {len(byte_hist)}')
    for v, c in byte_hist.most_common(8):
        print(f'    0x{v:02X} : {c:>9} cells ({c * 100.0 / total:.2f}%)')
    if first_nonzero is not None:
        cx, cy = first_nonzero % w, first_nonzero // w
        print(f'  first non-zero state word at cell ({cx}, {cy})')

    print('\n--- sanity: read a few cells raw ---')
    for idx in (0, w // 2, total // 2):
        raw = rd(h, data + idx * 0x34, 0x34)
        if raw:
            print(f'  cell #{idx}: {raw.hex(" ")}')


if __name__ == '__main__':
    main()
