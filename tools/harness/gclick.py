# -*- coding: utf-8 -*-
"""向游戏窗口发送真实点击（光栅 1280x720 坐标 → 原生 ×3）。用法: gclick.py x y [x y ...]"""
import ctypes, time, sys
import ctypes.wintypes as wt
u32 = ctypes.windll.user32
u32.SetProcessDPIAware()
PID = 26444
target = None
@ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
def cb(hwnd, lp):
    global target
    pid = wt.DWORD()
    u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == PID and u32.IsWindowVisible(hwnd):
        target = hwnd; return False
    return True
u32.EnumWindows(cb, 0)
u32.SetForegroundWindow(target)
time.sleep(0.4)
args = [int(a) for a in sys.argv[1:]]
for i in range(0, len(args), 2):
    rx, ry = args[i], args[i+1]
    u32.SetCursorPos(rx*3//1, ry*3//1)
    time.sleep(0.15)
    u32.mouse_event(2,0,0,0,0); time.sleep(0.06); u32.mouse_event(4,0,0,0,0)
    time.sleep(1.0)
print(f"点击完成: {args}")
