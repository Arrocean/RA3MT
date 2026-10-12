"""Read-only: differential-dump the mouse object itself.

The object behind 1.13 [0xCE43BC] is alive but +0x3C reads zero — the repack
layout differs from EA's. Watch the first 0x400 bytes of the object while
the mouse circles: whatever floats change are the real screen coords (or
whatever this object actually stores).

Usage: py tools/analysis/check_mouse_screen2.py [seconds=10] [pid]
  In game: circle the mouse continuously for the whole run.
"""
import ctypes
import struct
import subprocess
import sys
import time

k32 = ctypes.windll.kernel32
GLOBAL_VA = 0xCE43BC
OBJ_BYTES = 0x400


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
    secs = int(sys.argv[1]) if len(sys.argv) > 1 else 10
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
    print(f'鼠标对象 0x{obj:X}，连续画圈动鼠标……')
    print('3 秒后开始连续采样，列出变化的偏移：')
    time.sleep(3)

    counts = {}           # offset -> change count
    last = read(h, obj, OBJ_BYTES)
    t0 = time.time()
    while time.time() - t0 < secs:
        time.sleep(0.2)
        cur = read(h, obj, OBJ_BYTES)
        if cur is None or last is None:
            continue
        for off in range(0, OBJ_BYTES - 4, 4):
            if cur[off:off + 4] != last[off:off + 4]:
                counts[off] = counts.get(off, 0) + 1
        last = cur
    k32.CloseHandle(h)

    total_samples = int(secs / 0.2)
    print(f'\n采样约 {total_samples} 轮；对象内变化统计（次数>=3 才列出）：')
    for off in sorted(counts):
        c = counts[off]
        if c < 3:
            continue
        v = struct.unpack('<f', last[off:off + 4])[0]
        asint = struct.unpack('<I', last[off:off + 4])[0]
        print(f'  +0x{off:03X}: 变化 {c:3} 次, 当前 float={v:12.2f} / int=0x{asint:08X}')


if __name__ == '__main__':
    main()
