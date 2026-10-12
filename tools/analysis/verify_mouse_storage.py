"""Read-only: confirm the mouse-ground candidates and find their .data root.

scan4 world-type winners (A/B/A' verified, ground-height z stable):
  0x71014F0 / 0x710178C   (height 280 pair — two copies of one value)
  0x790C258 / 0x7AC9628   (height 190, A/B mirrored — a from/to pair)
Heap addresses change every match, so the deliverable is the .data global
that POINTS at these objects: scan .data for pointers into [cand-0x400,
cand+0x400] and report (global, offset-from-object).

Usage: py tools/analysis/verify_mouse_storage.py [seconds=15] [pid]
  In game: move the mouse around, then hover it over ONE selected friendly
  unit — the winning candidate should read that unit's (x, z) with its
  standing height.
"""
import ctypes
import struct
import subprocess
import sys
import time

k32 = ctypes.windll.kernel32

CANDS = [0x71014F0, 0x710178C, 0x790C258, 0x7AC9628]
DATA_LO, DATA_HI = 0xCE0000, 0xD00000     # 1.13 .data (image regions excluded from scan4)


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


def selected_body(h):
    root = read_u32(h, 0xCE4BFC)
    if root < 0x10000:
        return 0
    count = read_u32(h, root + 0x5C)
    head = read_u32(h, root + 0x50)
    if count == 0 or head < 0x10000:
        return 0
    node = read_u32(h, head)
    if node < 0x10000:
        return 0
    wrapper = read_u32(h, node + 8)
    return read_u32(h, wrapper + 0x138) if wrapper >= 0x10000 else 0


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
    print('游戏里动动鼠标，然后悬停到一个选中的己方单位上……')
    try:
        t0 = time.time()
        while time.time() - t0 < secs:
            line = []
            for c in CANDS:
                b = read(h, c, 12)
                x, y, z = struct.unpack('<3f', b) if b else (float('nan'),) * 3
                line.append(f'0x{c:X}=({x:7.1f},{y:7.1f},{z:5.1f})')
            body = selected_body(h)
            if body >= 0x10000:
                ub = read(h, body + 0x38, 12)
                ux, uy, uz = struct.unpack('<3f', ub)
                line.append(f'| 单位({ux:7.1f},{uy:7.1f},{uz:5.1f})')
            print(' '.join(line), flush=True)
            time.sleep(1)
    finally:
        # .data pointer hunt: which global points near each candidate?
        print('\n=== .data 指针反查（指向候选 ±0x400 的全局）===')
        data = read(h, DATA_LO, DATA_HI - DATA_LO) or b''
        for c in CANDS:
            found = []
            for off in range(0, len(data) - 4, 4):
                p = struct.unpack_from('<I', data, off)[0]
                if c - 0x400 <= p <= c + 0x400:
                    found.append((DATA_LO + off, p))
            for g, p in found[:6]:
                print(f'  cand 0x{c:X} <- .data 0x{g:X} = 0x{p:X} (对象+0x{p - (c - 0x400) - 0x400 + 0x400:X})'
                      if False else f'  cand 0x{c:X} <- .data 0x{g:X} -> 0x{p:X} (偏移 {p - c:+#x} 从候选)')
            if not found:
                print(f'  cand 0x{c:X} <- 无 .data 直接指针（可能经二级指针）')
        k32.CloseHandle(h)


if __name__ == '__main__':
    main()
