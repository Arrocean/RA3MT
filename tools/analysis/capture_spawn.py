# -*- coding: utf-8 -*-
"""等待用户真实点选一个征召兵 → 提取活 wrapper → 自动排兵 → 守页抓生成调用链。
后台运行：python capture_spawn.py（游戏窗口前台，请用户点一下任意征召兵）
结果写入 capture_result.txt
"""
import ctypes, ctypes.wintypes as wt, struct, time, sys, re, json

k32 = ctypes.windll.kernel32
user32 = ctypes.windll.user32
user32.SetProcessDPIAware()
PID = 35364
BASE = 0x400000
TEXT_LO, TEXT_HI = BASE + 0x1000, BASE + 0x7D0000
GAME = json.load(open(r"D:\RiderProject\RA3MT\tools\analysis\gamewin3.json"))[0]

src = open(r"D:\RiderProject\RA3MT\tools\analysis\watch_spawn.py", encoding="utf-8").read()
ns = {}
exec(src.split("def main")[0], ns)
DEBUG_EVENT, CONTEXT = ns["DEBUG_EVENT"], ns["CONTEXT"]

h = k32.OpenProcess(0x1F0FFF, False, PID)
def rd(a, n):
    b = ctypes.create_string_buffer(n); g = ctypes.c_size_t()
    ok = k32.ReadProcessMemory(h, ctypes.c_void_p(a), b, n, ctypes.byref(g))
    return b.raw[:g.value] if ok else None
def ru32(a):
    b = rd(a, 4)
    return struct.unpack('<I', b)[0] if b and len(b) == 4 else None
out = open(r"D:\RiderProject\RA3MT\tools\analysis\capture_result.txt", "w", encoding="utf-8")
def log(s):
    print(s); out.write(s + "\n"); out.flush()

# 1) 轮询选中（用户真实点击）
log("等待解锁（最长 1800 秒）：真实点选征召兵 或 启动修改器(UAC)")
bodies = []
t0 = time.time()
while time.time() - t0 < 1800:
    root = ru32(BASE + 0x8E4BFC)
    # 通道 B：修改器进程出现
    import ctypes.wintypes as _wt
    class _PE(ctypes.Structure):
        _fields_ = [('dwSize', _wt.DWORD), ('cntUsage', _wt.DWORD), ('th32ProcessID', _wt.DWORD),
                    ('th32DefaultHeapID', ctypes.POINTER(ctypes.c_ulong)), ('th32ModuleID', _wt.DWORD),
                    ('cntThreads', _wt.DWORD), ('th32ParentProcessID', _wt.DWORD),
                    ('pcPriClassBase', ctypes.c_long), ('dwFlags', _wt.DWORD),
                    ('szExeFile', ctypes.c_wchar * 260)]
    _snap = k32.CreateToolhelp32Snapshot(2, 0)
    _pe = _PE(); _pe.dwSize = ctypes.sizeof(_PE)
    _ok = k32.Process32FirstW(_snap, ctypes.byref(_pe))
    while _ok:
        if _pe.szExeFile == 'RA3MT.UI.exe':
            log('检测到修改器进程——请附加后点诊断采集，本脚本退出')
            k32.CloseHandle(_snap); out.close(); sys.exit(2)
        _ok = k32.Process32NextW(_snap, ctypes.byref(_pe))
    k32.CloseHandle(_snap)
    if root and root > 0x10000:
        cnt = ru32(root + 0x5C) or 0
        if cnt > 0:
            node = ru32(root + 0x50)
            for _ in range(min(cnt, 64)):
                if not node or node == root + 0x50 or node < 0x10000: break
                d = ru32(node + 8)
                if d and d > 0x10000:
                    b = ru32(d + 0x138)
                    if b and b > 0x10000: bodies.append(b)
                node = ru32(node)
            break
    time.sleep(0.5)
log(f"选中 {len(bodies)}: {[hex(b) for b in bodies[:6]]}")
if not bodies:
    log("超时未捕获选中"); out.close(); sys.exit(1)

# 2) 第一个 body → wrapper
body = bodies[0]
side = ru32(body + 0x418) or 0
trk = ru32(body + 0x3CC) or 0
w = ru32(trk + 4) if trk and trk > 0x10000 else 0
t = ru32(w + 0x14) if w and w > 0x10000 else 0
nm = ""
blk = rd(t - 0x100, 0x200)
if blk:
    m = re.search(rb'Name:([ -~]{4,40})', blk)
    if m: nm = m.group(1).decode()
log(f"body=0x{body:X} side=0x{side:X} tracker=0x{trk:X} wrapper=0x{w:X} template=0x{t:X} {nm}")
if not w or w < 0x10000:
    log("wrapper 无效"); out.close(); sys.exit(1)
PAGE = w & ~0xFFF

# 3) 排 5 兵（边栏 PostMessage 有效）
r = wt.RECT(); user32.GetWindowRect(GAME, ctypes.byref(r))
def click(rx, ry, wait=0.4):
    px, py = r.left + rx*(r.right-r.left)//1280, r.top + ry*(r.bottom-r.top)//720
    user32.SetCursorPos(px, py); time.sleep(0.15)
    lp = (py << 16) | (px & 0xFFFF)
    user32.PostMessageW(GAME, 0x201, 1, lp); time.sleep(0.06)
    user32.PostMessageW(GAME, 0x202, 0, lp); time.sleep(wait)
for _ in range(5):
    click(1165, 295)
log("已排 5 征召兵")

# 4) 守页抓写
old = wt.DWORD()
ok = k32.VirtualProtectEx(h, ctypes.c_void_p(PAGE), 0x1000, 0x104, ctypes.byref(old))
if not k32.DebugActiveProcess(PID):
    log("attach 失败"); out.close(); sys.exit(1)
ev = DEBUG_EVENT()
k32.VirtualProtectEx(h, ctypes.c_void_p(PAGE), 0x1000, 4, ctypes.byref(old))
for _ in range(150):
    if not k32.WaitForDebugEvent(ctypes.byref(ev), 200): break
    k32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, 0x00010002)
k32.VirtualProtectEx(h, ctypes.c_void_p(PAGE), 0x1000, 0x104, ctypes.byref(old))
log(f"守卫页 0x{PAGE:X}（wrapper 0x{w:X}）开始捕获 60s……")

def ctx_mod(tid, set_tf, clear_tf=False):
    th = k32.OpenThread(0x1FFFFF, False, tid)
    if not th: return 0
    k32.SuspendThread(th)
    ctx = CONTEXT(); ctx.ContextFlags = 0x00010007
    eip = esp = 0
    if k32.Wow64GetThreadContext(th, ctypes.byref(ctx)):
        eip, esp = ctx.Eip, ctx.Esp
        if set_tf: ctx.EFlags |= 0x100
        if clear_tf: ctx.EFlags &= ~0x100
        k32.Wow64SetThreadContext(th, ctypes.byref(ctx))
    k32.ResumeThread(th); k32.CloseHandle(th)
    return eip, esp

hits = []
t1 = time.time()
while time.time() - t1 < 60 and len(hits) < 20:
    if not k32.WaitForDebugEvent(ctypes.byref(ev), 40): continue
    c = ev.dwDebugEventCode
    cont = 0x00010002
    tid = ev.dwThreadId
    if c == 1:
        exc = struct.unpack_from('<I', ev.u, 0)[0]
        if exc == 0x80000001:
            i0 = struct.unpack_from('<I', ev.u, 20)[0]
            i1 = struct.unpack_from('<I', ev.u, 24)[0]
            eip, esp = ctx_mod(tid, set_tf=True)
            k32.VirtualProtectEx(h, ctypes.c_void_p(PAGE), 0x1000, 4, ctypes.byref(old))
            if i0 == 1 and w <= i1 < w + 0x100:   # 只记 wrapper 范围的写
                stack = rd(esp, 0x200) or b''
                rets = [struct.unpack_from('<I', stack, i)[0] for i in range(0, len(stack)-4, 4)]
                rets = [v for v in rets if TEXT_LO <= v < TEXT_HI]
                hits.append((eip, i1, rets[:24]))
                log(f"★写 0x{i1:X} EIP=0x{eip:X} (RVA 0x{eip-BASE:X}) 栈{len(rets)}")
        elif exc == 0x80000004:
            k32.VirtualProtectEx(h, ctypes.c_void_p(PAGE), 0x1000, 0x104, ctypes.byref(old))
            ctx_mod(tid, set_tf=False, clear_tf=True)
        else:
            cont = 0x80010001
    k32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, cont)
k32.VirtualProtectEx(h, ctypes.c_void_p(PAGE), 0x1000, 4, ctypes.byref(old))
k32.DebugActiveProcessStop(PID)
log(f"捕获完成：{len(hits)} 次写")
for i, (eip, addr, rets) in enumerate(hits):
    log(f"[{i}] 写=0x{addr:X} EIP=0x{eip:X} RVA=0x{eip-BASE:X}")
    log("    栈: " + " ".join(hex(x) for x in rets[:16]))
out.close()
k32.CloseHandle(h)
