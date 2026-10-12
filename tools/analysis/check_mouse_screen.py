"""Read-only: verify the repack mouse object (1.13 global 0xCE43BC).

Located statically: EA's registration site (mov [0xCDAEFC],esi followed by
the unique [esi+0x8C]/[esi+0x8D] capability check) matches exactly one site
per repack — 1.13 0x52C8D7 -> global 0xCE43BC, 1.12 0x544797 -> 0xCE009C.
FINAL3 reads this object's +0x3C/+0x40/+0x44 as mouse SCREEN floats and
converts through the game's own transform (0x60ECF0).

This watches the object live: circling the mouse in-game must make the
values change continuously (3 Hz sampling).

Usage: py tools/analysis/check_mouse_screen.py [seconds=12] [pid]
"""
import ctypes
import struct
import subprocess
import sys
import time

k32 = ctypes.windll.kernel32


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
    secs = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    pid = int(sys.argv[2], 0) if len(sys.argv) > 2 else None
    pname = None
    if not pid:
        pid, pname = find_game()
        if not pid:
            raise SystemExit('未找到游戏进程')
    global_va = 0xCE43BC if (pname or '1.13') == 'ra3_1.13.game' else 0xCE009C
    h = k32.OpenProcess(0x10 | 0x20, False, pid)
    if not h:
        raise SystemExit('OpenProcess failed')
    print(f'PID {pid}（{pname}）鼠标对象全局 0x{global_va:X}')
    print('游戏里【连续画圈动鼠标】——数值应持续滚动变化：')
    t0 = time.time()
    last = None
    changes = 0
    samples = 0
    try:
        while time.time() - t0 < secs:
            p = struct.unpack('<I', read(h, global_va, 4) or b'\0\0\0\0')[0]
            if p >= 0x10000:
                b = read(h, p + 0x3C, 12)
                x, y, z = struct.unpack('<3f', b) if b else (float('nan'),) * 3
                print(f'  obj=0x{p:X}  +3C/40/44 = ({x:8.1f}, {y:8.1f}, {z:6.1f})', flush=True)
                cur = (round(x, 1), round(y, 1))
                if last is not None and cur != last:
                    changes += 1
                last = cur
            else:
                print(f'  obj=null({p:#x})', flush=True)
            samples += 1
            time.sleep(0.3)
    finally:
        k32.CloseHandle(h)
        print(f'\n变化率：{changes}/{samples} 次采样 —— 跟手鼠标应为接近 samples')


if __name__ == '__main__':
    main()
