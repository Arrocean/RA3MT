# -*- coding: utf-8 -*-
"""活体差分扫描：定位重打包 1.13 的真·选中存储。
唤起窗口 → 点击清空 → 快照 S0 → 点击画面中某点 → 快照 S1 → 差分+结构验证。
用法: python diffsel.py [x y ...]  (光栅1280x720坐标，默认多点盲扫)
"""
import ctypes, ctypes.wintypes as wt, struct, sys, time

user32 = ctypes.windll.user32
k32 = ctypes.windll.kernel32
user32.SetProcessDPIAware()
PID = 43776
BASE = 0x400000
SCAN_LO, SCAN_HI = 0x8D0000, 0xD10000   # .data/.rdata 全局区 (VA 偏移)

h_proc = k32.OpenProcess(0x1F0FFF, False, PID)
assert h_proc


def rd(addr, n):
    buf = ctypes.create_string_buffer(n)
    got = ctypes.c_size_t()
    ok = k32.ReadProcessMemory(h_proc, ctypes.c_void_p(addr), buf, n, ctypes.byref(got))
    return buf.raw[:got.value] if ok else None


def ru32(a):
    b = rd(a, 4)
    return struct.unpack("<I", b)[0] if b and len(b) == 4 else 0


# ---- 找窗口并唤起 ----
best = [0, 0]
@ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
def cb(hwnd, lp):
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == PID and user32.IsWindowVisible(hwnd):
        rr = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rr))
        area = (rr.right - rr.left) * (rr.bottom - rr.top)
        if area > best[1]:
            best[0], best[1] = hwnd, area
    return True
user32.EnumWindows(cb, 0)
target = best[0] or None
assert target, "游戏窗口未找到"
if user32.IsIconic(target):
    user32.ShowWindow(target, 9)  # SW_RESTORE
    time.sleep(0.8)
user32.keybd_event(0x12, 0, 0, 0)
user32.SetForegroundWindow(target)
user32.keybd_event(0x12, 0, 2, 0)
time.sleep(0.6)
fg = user32.GetForegroundWindow()
print(f"窗口 0x{target:X} 前台化: {'OK' if fg == target else '失败(前台=0x%X)' % fg}")

r = wt.RECT()
user32.GetWindowRect(target, ctypes.byref(r))
W, H = r.right - r.left, r.bottom - r.top
print(f"窗口 rect: {r.left},{r.top} {W}x{H}")


def click(rx, ry):
    px = r.left + rx * W // 1280
    py = r.top + ry * H // 720
    user32.SetCursorPos(px, py)
    time.sleep(0.15)
    user32.mouse_event(2, 0, 0, 0, 0); time.sleep(0.05)
    user32.mouse_event(4, 0, 0, 0, 0)
    time.sleep(1.2)


def snapshot():
    out = bytearray()
    CH = 0x10000
    for a in range(BASE + SCAN_LO, BASE + SCAN_HI, CH):
        b = rd(a, CH)
        out += b if b else bytes(CH)
    return bytes(out)


def unit_ok(p):
    if p < 0x1000000: return False
    vt = ru32(p)
    if not (0x400000 < vt < 0xD00000): return False
    hp = ru32(p + 0x33C)
    return hp > 0x1000000 and 0x400000 < ru32(hp) < 0xD00000


def entry_like(p):
    if p < 0x1000000: return False
    vt = ru32(p)
    if not (0x400000 < vt < 0xD00000): return False
    a = ru32(p + 8)
    if a > 0x1000000:
        if unit_ok(ru32(a + 0x10)): return "chain+8+10"
        if unit_ok(ru32(a + 0x138)): return "chain+8+138"
    if unit_ok(ru32(p + 0x138)): return "direct+138"
    return None


def diff_validate(s0, s1, label):
    print(f"\n---- {label} 差分 ----")
    n = len(s0)
    found = []
    for i in range(0, n - 4, 4):
        v0 = struct.unpack_from("<I", s0, i)[0]
        v1 = struct.unpack_from("<I", s1, i)[0]
        if v0 == v1: continue
        va = BASE + SCAN_LO + i
        if v1 > 0x1000000 and unit_ok(v1):
            found.append((va, v0, v1, "unit-ptr"))
        elif v1 > 0x1000000 and entry_like(v1):
            found.append((va, v0, v1, "entry:" + entry_like(v1)))
    print(f"结构命中 {len(found)} 处:")
    for va, v0, v1, k in found[:40]:
        print(f"  0x{va:X}: 0x{v0:X} -> 0x{v1:X}  [{k}]")
    return found


click(300, 120)
s0 = snapshot()
print(f"S0 快照 {len(s0):#x}B")
all_found = {}
for pt in [(400, 660), (770, 620), (430, 560)]:
    click(*pt)
    s1 = snapshot()
    fs = diff_validate(s0, s1, f"点击 {pt}")
    for va, v0, v1, k in fs:
        all_found.setdefault(va, []).append((hex(v0), hex(v1), k))
    click(300, 120)
    s2 = snapshot()
    kept = []
    for va, v0, v1, k in fs:
        cur = struct.unpack_from("<I", s2, va - BASE - SCAN_LO)[0]
        if cur != v1:
            kept.append((hex(va), hex(cur)))
    print(f"  清空后仍变化的: {kept}")
    s0 = s2
print("\n==== 汇总（多次点击反复命中 = 强候选）====")
for va, recs in sorted(all_found.items()):
    if len(recs) >= 2:
        print(f"0x{va:X}: {recs}")
