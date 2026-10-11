"""Locate the mouse-state object (FINAL3 EA global 0x8DAEFC equivalent) live.

Strategy: move the OS cursor to two known screen positions, block-scan the
game heap each time for float pairs at +0x3C/+0x40 that track the cursor,
then find the .data global pointing at the winning object.
Read-only for the game; moves the user's cursor briefly. Run as admin.
"""
import ctypes
import ctypes.wintypes as wt
import struct
import sys
import time

k32 = ctypes.windll.kernel32
u32 = ctypes.windll.user32

PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400

SCAN_BEGIN, SCAN_END = 0x00400000, 0x20000000   # image + heap
BLOCK = 1 << 22
WINDOW_TITLE = 'Red Alert'


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


def scan_for(h, x, y):
    """Return {offset: page} for float pairs equal to (x, y) at some +0x3C-ish offset."""
    hits = []
    mbi = MEMORY_BASIC_INFORMATION64()
    addr = SCAN_BEGIN
    while addr < SCAN_END:
        if not k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
            break
        region = mbi.BaseAddress
        size = mbi.RegionSize
        if mbi.State == 0x1000 and mbi.Protect in (0x04, 0x02, 0x40, 0x20) and size <= BLOCK:
            data = read(h, region, size)
            if data:
                # slide a window: find x then verify y at +4, then record the
                # object candidate address as (hit - 0x3C)
                off = 0
                while True:
                    off = data.find(struct.pack('<f', x), off)
                    if off < 0 or off + 8 > len(data):
                        break
                    if struct.unpack_from('<f', data, off + 4)[0] == y:
                        hits.append(region + off - 0x3C)
                    off += 4
        addr = region + size
    return hits


def main():
    pid = int(sys.argv[1]) if len(sys.argv) > 1 else find_game()
    if not pid:
        raise SystemExit('game not running')
    h = k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
    if not h:
        raise SystemExit('OpenProcess failed (admin?)')

    hwnd = u32.FindWindowW(None, '命令与征服：红色警报3')
    if not hwnd:
        hwnd = u32.FindWindowW(None, 'Red Alert 3')
    rect = wt.RECT()
    if hwnd:
        u32.GetWindowRect(hwnd, ctypes.byref(rect))
        print(f'game window: {rect.left},{rect.top} .. {rect.right},{rect.bottom}')
    else:
        rect.left, rect.top, rect.right, rect.bottom = 0, 0, 1920, 1080
        print('window not found; using full screen')

    ax = rect.left + (rect.right - rect.left) // 3
    ay = rect.top + (rect.bottom - rect.top) // 3
    bx = rect.left + 2 * (rect.right - rect.left) // 3
    by = rect.top + 2 * (rect.bottom - rect.top) // 3

    u32.SetCursorPos(ax, ay)
    time.sleep(0.7)
    hits_a = set(scan_for(h, float(ax), float(ay)))
    print(f'position A ({ax},{ay}): {len(hits_a)} object candidates')
    u32.SetCursorPos(bx, by)
    time.sleep(0.7)
    hits_b = set(scan_for(h, float(bx), float(by)))
    print(f'position B ({bx},{by}): {len(hits_b)} object candidates')

    # A real mouse object appears in both scans: its +0x3C tracked A at scan A
    # and B at scan B, so it is a candidate in both lists.
    common = hits_a & hits_b
    print(f'tracked in both: {len(common)}')
    for obj in sorted(common)[:20]:
        data = read(h, obj, 0x50)
        if not data:
            continue
        x3c, y40, z44 = struct.unpack_from('<fff', data, 0x3C)
        # only keep ones whose current values equal B (they should have moved)
        if abs(x3c - bx) <= 2 and abs(y40 - by) <= 2:
            print(f'  MOUSE OBJECT 0x{obj:X}: +3C=({x3c:.1f},{y40:.1f},{z44:.1f})')
    k32.CloseHandle(h)


if __name__ == '__main__':
    main()
