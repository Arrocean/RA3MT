"""Read-only probe for the v25 mouse-mode landing investigation.

1. Mouse object [0xCE43BC]: dump +0x3C/+0x40/+0x44 several times, both as int
   and as float bit-pattern, to confirm +0x44 is an integer depth like the
   pixel pair (FINAL3 forwards it as the unproject z at buffer+0xC).
2. A reinforced unit (0x68A0970 by default, the one the user selected after a
   near-(0,0) camera summon): scan its first 0x800 bytes for plausible world
   coordinate float triples, to see where it actually landed.
3. Screen-center ground projection 0xCE15B8 (float3) as the camera reference.

Usage: py tools/analysis/probe_spawn_landing.py [unit_hex=0x68A0970] [pid]
"""
import ctypes
import struct
import subprocess
import sys

MOUSE_GLOBAL_VA = 0xCE43BC
CENTER_GROUND_VA = 0xCE15B8


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
                    return int(line.split(b'","')[1])
                except (ValueError, IndexError):
                    pass
    return None


def main():
    unit = int(sys.argv[1], 16) if len(sys.argv) > 1 else 0x68A0970
    pid = int(sys.argv[2]) if len(sys.argv) > 2 else find_game()
    if not pid:
        print('game not running')
        return
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x10 | 0x20, False, pid)  # PROCESS_VM_READ | QUERY_INFORMATION
    if not h:
        print('OpenProcess failed')
        return

    def read(addr, n):
        buf = ctypes.create_string_buffer(n)
        got = ctypes.c_size_t()
        if not k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, n, ctypes.byref(got)):
            return None
        return buf.raw[:got.value]

    def f32(b, off=0):
        return struct.unpack_from('<f', b, off)[0]

    print(f'== mouse object samples ==')
    for _ in range(3):
        ptr = struct.unpack('<I', read(MOUSE_GLOBAL_VA, 4))[0]
        body = read(ptr + 0x3C, 12)
        xs, ys, zs = struct.unpack('<III', body)
        print(f'  obj=0x{ptr:X}  +3C={xs}(int) {f32(body,0):.1f}f | '
              f'+40={ys}(int) {f32(body,4):.1f}f | '
              f'+44={zs}(int) {f32(body,8):.3f}f(bits)')

    print('== screen-center ground (camera ref) 0xCE15B8 ==')
    c = read(CENTER_GROUND_VA, 12)
    if c:
        x, y, z = struct.unpack('<fff', c)
        print(f'  ({x:.0f}, {y:.0f}, {z:.0f})')

    print(f'== unit 0x{unit:X} float scan (0..0x800) ==')
    body = read(unit, 0x800)
    if not body:
        print('  unreadable')
        return
    hits = []
    for off in range(0, 0x800 - 12, 4):
        x, y, z = struct.unpack_from('<fff', body, off)
        if all(map(lambda v: -200.0 < v < 8000.0 and abs(v) > 0.01, (x, y, z))) and \
           max(x, y, z) > 50.0 and y < 2000.0:
            hits.append((off, x, y, z))
    for off, x, y, z in hits[:15]:
        print(f'  +0x{off:X}: ({x:.0f}, {y:.0f}, {z:.0f})')
    print(f'  ({len(hits)} candidates total)')
    k32.CloseHandle(h)


if __name__ == '__main__':
    main()
