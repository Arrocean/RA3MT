"""Read-only: is 0xCE15B8 really a WORLD position?

Live report (2026-10-12, v24): reinforcements anchored at the logged
mouse-ground value spawn at a fixed southern spot instead, suggesting the
"mouse ground" global may be a scaled/screen-space value rather than world
coordinates. FINAL3 converts the mouse object's screen floats through the
game's own transform (EA 0x1ED4A0) before using them as a spawn position.

Calibration method: the selected unit's body position (body+0x38/0x3C/0x40)
is ground truth. Hover the mouse exactly over one selected friendly unit:
if 0xCE15B8 (x, z) equals that unit's (x, z), the global IS world-space and
the bug is downstream; if the values differ systematically (scaled/offset),
the global is not world-space and the spawn chain needs the transform.

Usage: py tools/analysis/check_mouseworld.py [seconds=20] [pid]
  In game: select ONE unit, hover the mouse right on it, and watch the lines.
"""
import ctypes
import struct
import subprocess
import sys
import time

k32 = ctypes.windll.kernel32

MOUSEGROUND_VA = 0xCE15B8     # 1.13 .data (features.json mouseGround RVA 0x8E15B8)
SEL_ROOT_VA = 0xCE4BFC        # 1.13 selection list global (RVA 0x8E4BFC)


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


def read_u32(h, addr):
    b = read(h, addr, 4)
    return struct.unpack('<I', b)[0] if b else 0


def read_f32(h, addr):
    b = read(h, addr, 4)
    return struct.unpack('<f', b)[0] if b else float('nan')


def selected_body(h):
    """First entry of the selection linked list (root+0x50 head, node+0x138 body)."""
    root = read_u32(h, SEL_ROOT_VA)
    if root < 0x10000:
        return 0
    count = read_u32(h, root + 0x5C)
    head = read_u32(h, root + 0x50)
    if count == 0 or head < 0x10000:
        return 0
    node = read_u32(h, head)          # first node
    if node < 0x10000:
        return 0
    wrapper = read_u32(h, node + 8)
    if wrapper < 0x10000:
        return 0
    return read_u32(h, wrapper + 0x138)


def main():
    secs = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    pid = int(sys.argv[2], 0) if len(sys.argv) > 2 else None
    pname = None
    if not pid:
        pid, pname = find_game()
        if not pid:
            raise SystemExit('未找到游戏进程（ra3_1.13.game / ra3_1.12.game）')
    print(f'PID {pid}（{pname or "?"}）——校准方法：选中一个己方单位，'
          '把鼠标悬停在该单位正上方，观察两行数值是否一致。')
    h = k32.OpenProcess(0x10 | 0x20, False, pid)
    if not h:
        raise SystemExit('OpenProcess failed（管理员？）')
    try:
        t0 = time.time()
        while time.time() - t0 < secs:
            mg_x = read_f32(h, MOUSEGROUND_VA)
            mg_z = read_f32(h, MOUSEGROUND_VA + 4)
            mg_y = read_f32(h, MOUSEGROUND_VA + 8)
            body = selected_body(h)
            if body >= 0x10000:
                u_x = read_f32(h, body + 0x38)
                u_y = read_f32(h, body + 0x3C)
                u_z = read_f32(h, body + 0x40)
                unit = f'单位(0x{body:X}) x={u_x:8.1f} y={u_y:7.1f} z={u_z:8.1f}'
            else:
                unit = '单位=（无选中）'
            dx = mg_x - read_f32(h, body + 0x38) if body >= 0x10000 else float('nan')
            dz = mg_z - read_f32(h, body + 0x40) if body >= 0x10000 else float('nan')
            print(f'鼠标全局 x={mg_x:8.1f} z={mg_z:8.1f} h={mg_y:7.1f} | {unit}'
                  + (f' | Δx={dx:+7.1f} Δz={dz:+7.1f}' if body >= 0x10000 else ''), flush=True)
            time.sleep(1)
    finally:
        k32.CloseHandle(h)


if __name__ == '__main__':
    main()
