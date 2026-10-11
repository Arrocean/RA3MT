# -*- coding: utf-8 -*-
"""硬件写监视点追踪 spawn 调用链。
DR0-3 = 征召兵 wrapper 计数字段（写监视）；排队征召兵触发；
捕获 #DB EIP + 栈内 .text 返回地址 = CreateUnit 调用链。
带 finally detach（调试器异常退出会终止被调试进程，必须保证脱离）。
用法: python watch_spawn.py <秒数>
"""
import ctypes, ctypes.wintypes as wt, struct, sys, time

k32 = ctypes.windll.kernel32
user32 = ctypes.windll.user32
user32.SetProcessDPIAware()
PID = 25492
BASE = 0x400000
WRAPPER = 0xFE7E6D0           # 征召兵共享 wrapper（ThingTemplateCountMap）
WATCH_OFFS = (0x4, 0x8, 0xC, 0x10)
TEXT_LO, TEXT_HI = BASE + 0x1000, BASE + 0x7D0000

DBG_CONTINUE = 0x00010002
DBG_EXCEPTION_NOT_HANDLED = 0x80010001
EXCEPTION_DEBUG_EVENT = 1
CREATE_PROCESS_DEBUG_EVENT = 3
CREATE_THREAD_DEBUG_EVENT = 2
EXIT_THREAD_DEBUG_EVENT = 4
EXIT_PROCESS_DEBUG_EVENT = 5
LOAD_DLL_DEBUG_EVENT = 6
UNLOAD_DLL_DEBUG_EVENT = 7
OUTPUT_DEBUG_STRING_EVENT = 8
RIP_EVENT = 9
EXCEPTION_SINGLE_STEP = 0x80000004


class CONTEXT(ctypes.Structure):
    _fields_ = [(f"_pad{i}", ctypes.c_uint32) for i in range(0)]  # placeholder
# 手工布局 x86 CONTEXT
CONTEXT = type("CONTEXT", (ctypes.Structure,), {
    "_fields_": [
        ("ContextFlags", ctypes.c_uint32),
        ("Dr0", ctypes.c_uint32), ("Dr1", ctypes.c_uint32),
        ("Dr2", ctypes.c_uint32), ("Dr3", ctypes.c_uint32),
        ("Dr6", ctypes.c_uint32), ("Dr7", ctypes.c_uint32),
        ("_fs", ctypes.c_uint32 * 28),           # FloatSave 112B
        ("SegGs", ctypes.c_uint32), ("SegFs", ctypes.c_uint32),
        ("SegEs", ctypes.c_uint32), ("SegDs", ctypes.c_uint32),
        ("Edi", ctypes.c_uint32), ("Esi", ctypes.c_uint32),
        ("Ebx", ctypes.c_uint32), ("Edx", ctypes.c_uint32),
        ("Ecx", ctypes.c_uint32), ("Eax", ctypes.c_uint32),
        ("Ebp", ctypes.c_uint32), ("Eip", ctypes.c_uint32),
        ("SegCs", ctypes.c_uint32), ("EFlags", ctypes.c_uint32),
        ("Esp", ctypes.c_uint32), ("SegSs", ctypes.c_uint32),
    ]})

class DEBUG_EVENT(ctypes.Structure):
    _fields_ = [
        ("dwDebugEventCode", ctypes.c_uint32),
        ("dwProcessId", ctypes.c_uint32),
        ("dwThreadId", ctypes.c_uint32),
        ("u", ctypes.c_uint8 * 176),
    ]

def read_mem(h, a, n):
    b = ctypes.create_string_buffer(n); g = ctypes.c_size_t()
    ok = k32.ReadProcessMemory(h, ctypes.c_void_p(a), b, n, ctypes.byref(g))
    return b.raw[:g.value] if ok else None

def threads_of(pid):
    class TE(ctypes.Structure):
        _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ThreadID", wt.DWORD),
                    ("th32OwnerProcessID", wt.DWORD), ("tpBasePri", ctypes.c_long),
                    ("tpDeltaPri", ctypes.c_long), ("dwFlags", wt.DWORD)]
    snap = k32.CreateToolhelp32Snapshot(0x4, pid)   # TH32CS_SNAPTHREAD
    te = TE(); te.dwSize = ctypes.sizeof(TE)
    out = []
    ok = k32.Thread32First(snap, ctypes.byref(te))
    while ok:
        if te.th32OwnerProcessID == pid:
            out.append(te.th32ThreadID)
        ok = k32.Thread32Next(snap, ctypes.byref(te))
    k32.CloseHandle(snap)
    return out

def set_watchpoints(on, addrs):
    """on=True: DR0..3=写监视(len4)；False: 清零。返回成功线程数。"""
    n = 0
    for tid in threads_of(PID):
        th = k32.OpenThread(0x1FFFFF, False, tid)   # THREAD_ALL_ACCESS
        if not th: continue
        ctx = CONTEXT()
        ctx.ContextFlags = 0x00110007               # FULL | DEBUG_REGISTERS | i386
        if k32.Wow64GetThreadContext(th, ctypes.byref(ctx)):
            if on:
                ctx.Dr7 = 0
                for i, a in enumerate(addrs[:4]):
                    setattr(ctx, f"Dr{i}", a)
                ctx.Dr7 = 0x0000000F | 0xDDDD0000   # L0-3 + 每槽 RW=01(write) LEN=11(4B)
            else:
                ctx.Dr0 = ctx.Dr1 = ctx.Dr2 = ctx.Dr3 = 0
                ctx.Dr7 = 0
            if k32.Wow64SetThreadContext(th, ctypes.byref(ctx)):
                n += 1
        k32.CloseHandle(th)
    return n

def ui_queue_conscript():
    """选兵营 + 点征召兵图标（坐标由截图标定，失败不影响调试泵）。"""
    best = [0, 0]
    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(hwnd, l):
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == PID and user32.IsWindowVisible(hwnd):
            r = wt.RECT(); user32.GetWindowRect(hwnd, ctypes.byref(r))
            a = (r.right-r.left)*(r.bottom-r.top)
            if a > best[1]: best[0], best[1] = hwnd, a
        return True
    user32.EnumWindows(cb, 0)
    r = wt.RECT(); user32.GetWindowRect(best[0], ctypes.byref(r))
    def click(rx, ry):
        px, py = r.left + rx*(r.right-r.left)//1280, r.top + ry*(r.bottom-r.top)//720
        user32.SetCursorPos(px, py); time.sleep(0.2)
        lp = (py << 16) | (px & 0xFFFF)
        user32.PostMessageW(best[0], 0x201, 1, lp); time.sleep(0.08)
        user32.PostMessageW(best[0], 0x202, 0, lp); time.sleep(0.6)
    click(770, 330)    # 兵营
    click(1165, 295)   # 生产面板 征召兵大图标（截图标定）
    click(1165, 295)   # 排两个，多一次写

def main():
    duration = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    h = k32.OpenProcess(0x1F0FFF, False, PID)
    addrs = [WRAPPER + off for off in WATCH_OFFS]
    if not k32.DebugActiveProcess(PID):
        print("DebugActiveProcess 失败", k32.GetLastError()); return 1
    attached = True
    hits = []
    try:
        ev = DEBUG_EVENT()
        # 吸收附加初始事件
        for _ in range(200):
            if not k32.WaitForDebugEvent(ctypes.byref(ev), 200): break
            k32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, DBG_CONTINUE)
            if ev.dwDebugEventCode == EXCEPTION_DEBUG_EVENT:
                # 附加断点已过
                pass
        n = set_watchpoints(True, addrs)
        print(f"监视点已设 {n} 线程: " + " ".join(hex(a) for a in addrs))
        time.sleep(0.3)
        ui_queue_conscript()
        t0 = time.time()
        while time.time() - t0 < duration and len(hits) < 6:
            if not k32.WaitForDebugEvent(ctypes.byref(ev), 30):
                continue
            code = ev.dwDebugEventId if False else ev.dwDebugEventCode
            cont = DBG_CONTINUE
            if code == EXCEPTION_DEBUG_EVENT:
                erec = struct.unpack_from('<II', ev.u, 8)  # ExceptionCode, ExceptionFlags @ u+4? 布局：u=EXCEPTION_DEBUG_INFO{EXCEPTION_RECORD{Code,Flags,Record,PAddress,NumParams,Info[15]}, FirstChance}
                exc_code = struct.unpack_from('<I', ev.u, 0)[0]
                first_chance = struct.unpack_from('<I', ev.u, 84)[0]
                if exc_code == EXCEPTION_SINGLE_STEP:
                    tid = ev.dwThreadId
                    th = k32.OpenThread(0x1FFFFF, False, tid)
                    ctx = CONTEXT(); ctx.ContextFlags = 0x00110007
                    if th and k32.GetThreadContext(th, ctypes.byref(ctx)):
                        eip, esp, dr6 = ctx.Eip, ctx.Esp, ctx.Dr6
                        stack = read_mem(h, esp, 0x180) or b''
                        rets = [struct.unpack_from('<I', stack, i)[0]
                                for i in range(0, len(stack)-4, 4)]
                        rets = [v for v in rets if TEXT_LO <= v < TEXT_HI]
                        hits.append((eip, esp, dr6, rets[:24]))
                        print(f"★ #DB EIP=0x{eip:X} DR6={dr6:#x} 栈内返回地址 {len(rets)}")
                    if th: k32.CloseHandle(th)
                else:
                    cont = DBG_EXCEPTION_NOT_HANDLED
            k32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, cont)
    finally:
        try:
            set_watchpoints(False, [])
            time.sleep(0.05)
            k32.DebugActiveProcessStop(PID)
            print("已脱离调试器")
        except Exception as ex:
            print("detach 失败!", ex)
    for i, (eip, esp, dr6, rets) in enumerate(hits):
        print(f"\n命中{i}: EIP=0x{eip:X} (RVA 0x{eip-BASE:X}) DR6={dr6:#x}")
        print("  调用链(栈内 .text 地址):", " ".join(hex(r) for r in rets[:16]))
    k32.CloseHandle(h)
    return 0

if __name__ == "__main__":
    sys.exit(main())
