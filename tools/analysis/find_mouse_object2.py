"""Mouse-object hunt v2: assumption-free differential scan.

Pass 1: cursor at position A — collect every offset in committed heap pages
where two adjacent floats look like on-screen coordinates (0..w, 0..h).
Pass 2: cursor at position B — re-read those pages; the mouse object is the
offset whose pair moved to B (any scale).
Run as admin with the game window in the foreground.
"""
import ctypes
import ctypes.wintypes as wt
import struct
import sys
import time
from collections import defaultdict

k32 = ctypes.windll.kernel32
u32 = ctypes.windll.user32

SCAN_BEGIN, SCAN_END = 0x00400000, 0x30000000
BLOCK = 1 << 22


class MEMORY_BASIC_INFORMATION64(ctypes.Structure):
    _fields_ = [('BaseAddress', ctypes.c_uint64), ('AllocationBase', ctypes.c_uint64),
                ('AllocationProtect', ctypes.c_uint32), ('__alignment1', ctypes.c_uint32),
                ('RegionSize', ctypes.c_uint64), ('State', ctypes.c_uint32),
                ('Protect', ctypes.c_uint32), ('Type', ctypes.c_uint32)]


def find_game():
    class PE(ctypes.Structure):
        _fields_ = [('dwSize', ctypes.c_ulong), ('cntUsage', ctypes.c_ulong),
                    ('th32ProcessID', ctypes.c_ulong), ('th32ModuleID', ctypes.c_ulong),
                    ('cntThreads', ctypes.c_ulong), ('th32ParentProcessID', ctypes.c_ulong),
                    ('pcPriClassBase', ctypes.c_long), ('dwFlags', ctypes.c_ulong),
                    ('szExeFile', ctypes.c_char * 260)]
    procs = []
    lppe = PE()
    lppe.dwSize = ctypes.sizeof(PE)
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)
    if k32.Process32First(snap, ctypes.byref(lppe)):
        while k32.Process32Next(snap, ctypes.byref(lppe)):
            if lppe.szExeFile.decode().startswith('ra3_1.1'):
                procs.append(lppe.th32ProcessID)
    k32.CloseHandle(snap)
    return procs[0] if procs else None


def read(h, addr, size):
    buf = ctypes.create_string_buffer(size)
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, size, ctypes.byref(got)):
        return None
    return buf.raw[:got.value]


def regions(h):
    mbi = MEMORY_BASIC_INFORMATION64()
    addr = SCAN_BEGIN
    out = []
    while addr < SCAN_END:
        if not k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
            break
        if mbi.State == 0x1000 and mbi.Protect in (0x04, 0x02, 0x40):
            out.append((mbi.BaseAddress, mbi.RegionSize))
        addr = mbi.BaseAddress + mbi.RegionSize
    return out


def collect_pairs(h, w, hgt):
    """Return {(region_base): {offset: (x, y)}} for float pairs in screen range."""
    result = defaultdict(dict)
    mbi = MEMORY_BASIC_INFORMATION64()
    addr = SCAN_BEGIN
    total = 0
    while addr < SCAN_END:
        if not k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
            break
        base, size = mbi.BaseAddress, mbi.RegionSize
        if mbi.State == 0x1000 and mbi.Protect in (0x04, 0x02, 0x40) and size <= BLOCK:
            data = read(h, base, size)
            if data:
                pairs = result[base]
                for off in range(0, len(data) - 12, 4):
                    x, y, z = struct.unpack_from('<fff', data, off)
                    if abs(x) < 3000 and -50 < y < 800 and abs(z) < 3000                             and (abs(x) > 1 or abs(z) > 1):
                        pairs[off] = (x, z)   # track the ground plane pair
                        total += 1
        addr = base + size
    print(f'candidates at A: {total} pairs across {len(result)} regions')
    return result


def main():
    pid = int(sys.argv[1]) if len(sys.argv) > 1 else find_game()
    if not pid:
        raise SystemExit('game not running')
    h = k32.OpenProcess(0x0410, False, pid)
    if not h:
        raise SystemExit('OpenProcess failed (admin?)')

    hwnd = u32.FindWindowW(None, '終極動員令：紅色警戒3')
    rect = wt.RECT()
    u32.GetWindowRect(hwnd, ctypes.byref(rect))
    w, hgt = rect.right - rect.left, rect.bottom - rect.top
    ax, ay = rect.left + w // 4, rect.top + hgt // 4
    bx, by = rect.left + 3 * w // 4, rect.top + 3 * hgt // 4
    print(f'window {w}x{hgt}; A=({ax},{ay}) B=({bx},{by})')

    # force the game foreground: RA3 stops tracking the mouse when unfocused
    u32.SetForegroundWindow(hwnd)
    u32.SetFocus(hwnd)
    time.sleep(0.5)
    fg = u32.GetForegroundWindow()
    if fg != hwnd:
        print(f'WARNING: foreground is 0x{fg:X}, not the game; results may be empty')
    u32.SetCursorPos(ax, ay)
    time.sleep(1.0)
    snap_a = collect_pairs(h, w, hgt)

    u32.SetCursorPos(bx, by)
    time.sleep(0.8)

    winners = []
    for base, pairs in snap_a.items():
        if not pairs:
            continue
        size_needed = max(pairs) + 8
        data = read(h, base, size_needed)
        if not data:
            continue
        for off, (xa, ya) in pairs.items():
            x, y = struct.unpack_from('<ff', data, off)
            if abs(x - xa) < 0.01 and abs(y - ya) < 0.01:
                continue
            # moved toward B at any scale?
            if (x - xa) * (bx - ax) > 0 and (y - ya) * (by - ay) > 0:
                winners.append((base, off, (xa, ya), (x, y)))
    print(f'moved with cursor: {len(winners)}')
    for base, off, a, b in winners[:40]:
        obj = base + off - 0x3C
        print(f'  +0x3C@0x{base + off:X}  A=({a[0]:.0f},{a[1]:.0f}) B=({b[0]:.0f},{b[1]:.0f})'
              f'  scale={((b[0] - a[0]) / (bx - ax)):.3f}  obj=0x{obj:X}')
    k32.CloseHandle(h)


if __name__ == '__main__':
    main()
