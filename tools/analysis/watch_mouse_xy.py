"""Read-only: live-watch the mouse object X/Y against the OS cursor.

To prove +0x3C/+0x40 IS the mouse, this prints both the game object values
and the real OS cursor position (GetCursorPos, screen pixels) side by side.
Move the mouse anywhere on screen — the two pairs must track.

Usage: py tools/analysis/watch_mouse_xy.py [seconds=15] [pid]
"""
import ctypes
import struct
import subprocess
import sys
import time

k32 = ctypes.windll.kernel32
u32 = ctypes.windll.user32
GLOBAL_VA = 0xCE43BC


class POINT(ctypes.Structure):
    _fields_ = [('x', ctypes.c_long), ('y', ctypes.c_long)]


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


def read(h, addr, n):
    buf = ctypes.create_string_buffer(n)
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, n, ctypes.byref(got)):
        return None
    return buf.raw[:got.value]


def main():
    secs = int(sys.argv[1]) if len(sys.argv) > 1 else 15
    pid = int(sys.argv[2], 0) if len(sys.argv) > 2 else None
    if not pid:
        pid, _ = find_game()
        if not pid:
            raise SystemExit('未找到游戏进程')
    h = k32.OpenProcess(0x10 | 0x20, False, pid)
    if not h:
        raise SystemExit('OpenProcess failed')
    obj = struct.unpack('<I', read(h, GLOBAL_VA, 4) or b'\0\0\0\0')[0]
    if obj < 0x10000:
        raise SystemExit('鼠标对象为空')
    print(f'对象 0x{obj:X}。随意移动鼠标（游戏画面内外都行），两列数值应同步：')
    print('格式: 对象(+0x3C,+0x40)  |  OS光标(GetCursorPos)')
    pt = POINT()
    t0 = time.time()
    last_print = 0.0
    try:
        while time.time() - t0 < secs:
            b = read(h, obj + 0x3C, 8)
            gx, gy = struct.unpack('<2I', b) if b else (0, 0)
            u32.GetCursorPos(ctypes.byref(pt))
            now = time.time()
            if now - last_print >= 0.25:
                print(f'  ({gx:5},{gy:5})  |  ({pt.x:5},{pt.y:5})', flush=True)
                last_print = now
            time.sleep(0.05)
    finally:
        k32.CloseHandle(h)


if __name__ == '__main__':
    main()
