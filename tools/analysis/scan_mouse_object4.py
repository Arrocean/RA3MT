"""Read-only: locate the real mouse storage — three-snapshot differential.

scan3 produced 187k noise hits (8s windows let ordinary game state change).
This version adds the two filters noise cannot survive:
  1. A/B/A' protocol — mouse goes top-left, bottom-right, then BACK to the
     same top-left spot. A real mouse slot must return to its A value; one-shot
     state changes do not.
  2. FLOAT TRIPLES — FINAL3's EA layout is three consecutive floats
     (+0x3C/+0x40/+0x44 screen x/y/z): candidates are (x, y, z) triples whose
     x/y move corner-to-corner and whose z stays stable.

Camera must stay perfectly still the whole time (no edge scroll, no arrow
keys). Snapshot A is kept whole (~working set); B and A' are streamed.

Usage: py tools/analysis/scan_mouse_object4.py [pid]
"""
import ctypes
import ctypes.wintypes as wt
import struct
import subprocess
import sys
import time

k32 = ctypes.windll.kernel32

EXCLUDE_LO, EXCLUDE_HI = 0xCE15A0, 0xCE15C8   # known screen-center projection


def find_game():
    for name in ('ra3_1.13.game', 'ra3_1.12.game'):
        try:
            out = subprocess.run(['tasklist', '/FI', f'IMAGENAME eq {name}',
                                  '/FO', 'CSV', '/NH'], capture_output=True, timeout=10).stdout
        except Exception:
            continue
        for line in out.splitlines():
            if line.lower().startswith(b'"ra3_'):
                try:
                    return int(line.split(b'","')[1]), name
                except (ValueError, IndexError):
                    pass
    return None, None


class MBI(ctypes.Structure):
    _fields_ = [('BaseAddress', ctypes.c_void_p), ('AllocationBase', ctypes.c_void_p),
                ('AllocationProtect', wt.DWORD), ('RegionSize', ctypes.c_size_t),
                ('State', wt.DWORD), ('Protect', wt.DWORD), ('Type', wt.DWORD)]


def readable_regions(h):
    addr, mbi, regions = 0, MBI(), []
    while addr < 0x7FFF0000:
        if not k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
            break
        size = mbi.RegionSize or 0x1000
        prot = mbi.Protect & 0xFF
        if mbi.State == 0x1000 and prot in (0x02, 0x04, 0x06, 0x40, 0x20, 0x08) and mbi.Type != 0x1000000:
            regions.append((addr, size))
        addr += size
    return regions


def read(h, addr, size):
    buf = ctypes.create_string_buffer(size)
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, size, ctypes.byref(got)):
        return None
    return buf.raw[:got.value]


def chunk_list(regions, cap=1 << 24):
    out = []
    for base, size in regions:
        for off in range(0, size, cap):
            out.append((base + off, min(cap, size - off)))
    return out


def main():
    pid = int(sys.argv[1], 0) if len(sys.argv) > 1 else None
    if not pid:
        pid, _ = find_game()
        if not pid:
            raise SystemExit('未找到游戏进程')
    h = k32.OpenProcess(0x10 | 0x20 | 0x8, False, pid)
    if not h:
        raise SystemExit('OpenProcess failed（管理员？）')
    regions = readable_regions(h)
    chs = chunk_list(regions)
    total = sum(s for _, s in chs) / 1024 / 1024
    print(f'区域共 {total:.0f} MB。全程别动镜头，只动鼠标！')

    print('① 鼠标放到游戏画面【左上角】停住……5 秒后快照 A')
    time.sleep(5)
    snap_a = {}
    for addr, size in chs:
        d = read(h, addr, size)
        if d:
            snap_a[addr] = d
    print(f'   A 完成（{len(snap_a)} 块）')
    print('② 鼠标移到【右下角】停住……5 秒后快照 B')
    time.sleep(5)
    diffs = {}            # addr -> list of (dword_index, va_bits, vb_bits)
    for addr, a in snap_a.items():
        b = read(h, addr, len(a))
        if b is None:
            continue
        n = len(a) // 4
        for i in range(n):
            off = i * 4
            if a[off:off + 4] != b[off:off + 4]:
                diffs.setdefault(addr, []).append((i, a[off:off + 4], b[off:off + 4]))
    total_diffs = sum(len(v) for v in diffs.values())
    print(f'   A→B 变化 dword：{total_diffs}（含噪声，正常）')
    print('③ 鼠标移回【同一个左上角位置】停住……5 秒后快照 A2')
    time.sleep(5)

    screen_hits, world_hits = [], []
    for addr, lst in diffs.items():
        a2 = read(h, addr, len(snap_a[addr]))
        if a2 is None:
            continue
        idxset = {i for i, _, _ in lst}
        for i, va_raw, vb_raw in lst:
            if i + 2 not in idxset:
                continue
            ax, ay, az = struct.unpack('<3f', va_raw)
            bx, by, bz = struct.unpack('<3f', vb_raw)
            a2off = i * 4
            if a2[a2off:a2off + 12] != va_raw:
                continue    # did not return to A → noise
            va_addr = addr + i * 4
            if EXCLUDE_LO <= va_addr <= EXCLUDE_HI:
                continue
            if not all(v == v and abs(v) < 1e7 for v in (ax, ay, az, bx, by, bz)):
                continue
            dx, dy = bx - ax, by - ay
            if not (0 <= ax < 8192 and 0 <= ay < 8192 and 0 <= bx < 8192 and 0 <= by < 8192):
                continue
            if dx > 300 and dy > 150:
                screen_hits.append((va_addr, ax, ay, az, bx, by))
                continue
            if 0 <= ax < 5600 and 0 <= ay < 5600 and 0 <= bx < 5600 and 0 <= by < 5600 \
                    and abs(dx) + abs(dy) > 400:
                world_hits.append((va_addr, ax, ay, az, bx, by))

    k32.CloseHandle(h)
    print(f'\n=== 屏幕坐标型三元组（左上→右下 且 A 值恢复）: {len(screen_hits)} ===')
    for va_addr, ax, ay, az, bx, by in screen_hits[:30]:
        print(f'  0x{va_addr:X}  A=({ax:.1f},{ay:.1f},{az:.1f}) B=({bx:.1f},{by:.1f})')
    print(f'\n=== 世界坐标型三元组: {len(world_hits)} ===')
    for va_addr, ax, ay, az, bx, by in world_hits[:30]:
        print(f'  0x{va_addr:X}  A=({ax:.1f},{ay:.1f},{az:.1f}) B=({bx:.1f},{by:.1f})')
    print('\n把完整输出交回。')


if __name__ == '__main__':
    main()
