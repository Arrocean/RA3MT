"""Diff-scan the two live objects captured in the placement samples while the
user moves the mouse: whichever floats track the cursor are the mouse world
coordinates, and the containing object tells us where to read them from."""
import ctypes
import struct
import sys
import time
import ctypes.wintypes as wt

k32 = ctypes.windll.kernel32
u32 = ctypes.windll.user32

PID = int(sys.argv[1]) if len(sys.argv) > 1 else 38552
WATCH = [0x782A0B0, 0x1AF324]     # ecx (cell-query this) and esi from the samples
SPAN = 0x120                        # dump a window around each

def read(h, a, n):
    buf = ctypes.create_string_buffer(n); got = ctypes.c_size_t()
    ok = k32.ReadProcessMemory(h, ctypes.c_void_p(a), buf, n, ctypes.byref(got))
    return buf.raw[:got.value] if ok else None

def snapshot(h):
    out = {}
    for base in WATCH:
        lo = base - SPAN // 2
        data = read(h, lo, SPAN)
        if data:
            for off in range(0, len(data) - 4, 4):
                x, y, z = struct.unpack_from('<fff', data, off) if off + 12 <= len(data) else (None,) * 3
                if x is None:
                    continue
                if abs(x) < 3000 and -50 < y < 800 and abs(z) < 3000 and (abs(x) > 1 or abs(z) > 1):
                    out[lo + off] = (x, y, z)
    return out

def main():
    h = k32.OpenProcess(0x0410, False, PID)
    if not h:
        raise SystemExit('cannot open game')
    hwnd = u32.FindWindowW(None, '終極動員令：紅色警戒3')
    u32.SetForegroundWindow(hwnd)
    time.sleep(0.5)
    u32.SetCursorPos(600, 500)
    time.sleep(0.8)
    snap_a = snapshot(h)
    print(f'position A: {len(snap_a)} world-like triples')
    u32.SetCursorPos(1500, 900)
    time.sleep(0.8)
    snap_b = snapshot(h)
    moved = []
    for addr, va in snap_a.items():
        vb = snap_b.get(addr)
        if vb and (abs(vb[0]-va[0]) > 0.5 or abs(vb[2]-va[2]) > 0.5):
            moved.append((addr, va, vb))
    print(f'tracked the cursor: {len(moved)}')
    for addr, va, vb in moved:
        print(f'  0x{addr:X}: A=({va[0]:.1f},{va[1]:.1f},{va[2]:.1f}) B=({vb[0]:.1f},{vb[1]:.1f},{vb[2]:.1f})')
    k32.CloseHandle(h)

if __name__ == '__main__':
    main()
