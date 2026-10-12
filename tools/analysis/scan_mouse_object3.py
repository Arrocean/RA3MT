"""Read-only: locate the REAL mouse position storage by differential scan.

Settled (2026-10-12): 0xCE15B8 is the SCREEN-CENTER ground projection (it
tracks the camera, not the mouse) — v18g's SetCursorPos validation was fooled
by edge scrolling. FINAL3 instead reads the mouse object's screen floats
(EA [0x8DAEFC]+0x3C/40/44) and converts them through the game's transform
(EA 0x1ED4A0 == repack 1.13 0x60ECF0, located).

This scan hunts, in one experiment:
  (a) a pair of adjacent floats that behave like mouse SCREEN coordinates
      (0..8192, large delta between corners), and
  (b) any pair that behaves like mouse WORLD coordinates (0..5600 x/z),
      in case the UI also caches the true mouse ground point.

Protocol (mouse moves, camera MUST stay perfectly still — do not touch the
screen edges, no arrow keys): snapshot A = mouse at top-left of the screen;
snapshot B = mouse at bottom-right. Only slots changing between A and B with
matching ranges are reported.

Usage: py tools/analysis/scan_mouse_object3.py [pid]
"""
import ctypes
import ctypes.wintypes as wt
import struct
import subprocess
import sys
import time

k32 = ctypes.windll.kernel32

EXCLUDE = {0xCE15B8, 0xCE15BC, 0xCE15C0}   # known screen-center projection


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
    """MEM_COMMIT, readable, non-image regions (heap/data), chunked to 16MB."""
    addr = 0
    mbi = MBI()
    regions = []
    while addr < 0x7FFF0000:
        if not k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
            break
        size = mbi.RegionSize or 0x1000
        prot = mbi.Protect & 0xFF
        if mbi.State == 0x1000 and prot in (0x02, 0x04, 0x06, 0x40, 0x20, 0x08) \
                and not (mbi.Type == 0x1000000):   # skip MEM_IMAGE (.text etc.)
            regions.append((addr, size))
        addr += size
    return regions


def read(h, addr, size):
    buf = ctypes.create_string_buffer(size)
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, size, ctypes.byref(got)):
        return None
    return buf.raw[:got.value]


def snapshot(h, regions):
    data = {}
    for base, size in regions:
        for off in range(0, size, 1 << 24):
            chunk = read(h, base + off, min(1 << 24, size - off))
            if chunk:
                data[base + off] = chunk
    return data


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
    total = sum(s for _, s in regions) / 1024 / 1024
    print(f'扫描区域 {len(regions)} 块共 {total:.0f} MB')
    print('步骤：①把鼠标移到游戏画面【左上角】停住（别碰边缘/别动镜头）——8 秒后拍快照 A')
    time.sleep(8)
    print('拍照 A ...')
    a = snapshot(h, regions)
    print('②现在把鼠标移到游戏画面【右下角】停住（同样别动镜头）——8 秒后拍快照 B')
    time.sleep(8)
    print('拍照 B ...')
    b = snapshot(h, regions)

    screen_hits, world_hits = [], []
    for base, chunk_a in a.items():
        chunk_b = b.get(base)
        if chunk_b is None or len(chunk_a) != len(chunk_b):
            continue
        n = len(chunk_a) // 4
        va = struct.unpack_from(f'<{n}I', chunk_a)
        vb = struct.unpack_from(f'<{n}I', chunk_b)
        fa = struct.unpack_from(f'<{n}f', chunk_a)
        fb = struct.unpack_from(f'<{n}f', chunk_b)
        for i in range(n - 1):
            if va[i] == vb[i] or va[i + 1] == vb[i + 1]:
                continue
            x0, y0, x1, y1 = fa[i], fa[i + 1], fb[i], fb[i + 1]
            if not all(map(lambda v: v == v and abs(v) < 1e7, (x0, y0, x1, y1))):
                continue
            addr = base + i * 4
            if addr in EXCLUDE or addr - 4 in EXCLUDE or addr + 4 in EXCLUDE:
                continue
            # (a) screen-like: both coords grow toward bottom-right, big delta
            if 0 <= x0 < 8192 and 0 <= x1 < 8192 and 0 <= y0 < 8192 and 0 <= y1 < 8192 \
                    and x1 - x0 > 300 and y1 - y0 > 150:
                screen_hits.append((addr, x0, y0, x1, y1))
            # (b) world-like x/z pair: values in map range, large movement
            elif 0 <= x0 < 5600 and 0 <= x1 < 5600 and 0 <= y0 < 5600 and 0 <= y1 < 5600 \
                    and abs(x1 - x0) + abs(y1 - y0) > 400:
                world_hits.append((addr, x0, y0, x1, y1))

    k32.CloseHandle(h)
    print(f'\n=== 屏幕坐标型候选（x,y 都变大, Δ大）: {len(screen_hits)} ===')
    for addr, x0, y0, x1, y1 in screen_hits[:25]:
        print(f'  0x{addr:X}  A=({x0:.0f},{y0:.0f}) -> B=({x1:.0f},{y1:.0f})')
    print(f'\n=== 世界坐标型候选（x/z 对大幅移动）: {len(world_hits)} ===')
    for addr, x0, y0, x1, y1 in world_hits[:25]:
        print(f'  0x{addr:X}  A=({x0:.0f},{y0:.0f}) -> B=({x1:.0f},{y1:.0f})')
    print('\n把以上完整输出交回。')


if __name__ == '__main__':
    main()
