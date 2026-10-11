# -*- coding: utf-8 -*-
"""PAGE_GUARD 写监视追踪器（Wow64 兼容，不用 DR 寄存器）。
目标页加 GUARD → 写触发 EXCEPTION_GUARD_PAGE（含被写地址）→ 摘 GUARD + 置 TF
→ 单步异常恢复 GUARD。记录 EIP/被写地址/栈内 .text 返回地址。
用法: python watch_guard.py <页基址hex> <秒> [最大命中]
"""
import ctypes, ctypes.wintypes as wt, struct, sys, time

k32 = ctypes.windll.kernel32
user32 = ctypes.windll.user32
user32.SetProcessDPIAware()
PID = 35364
BASE = 0x400000
TEXT_LO, TEXT_HI = BASE + 0x1000, BASE + 0x7D0000

DBG_CONTINUE = 0x00010002
EXCEPTION_DEBUG_EVENT = 1
GUARD = 0x80000001
SINGLE_STEP = 0x80000004
PAGE_RW = 0x04
PAGE_RW_GUARD = 0x104

src = open(r"D:\RiderProject\RA3MT\tools\analysis\watch_spawn.py", encoding="utf-8").read()
ns = {}
exec(src.split("def main")[0], ns)
CONTEXT, DEBUG_EVENT, threads_of = ns["CONTEXT"], ns["DEBUG_EVENT"], ns["threads_of"]

def read_mem(h, a, n):
    b = ctypes.create_string_buffer(n); g = ctypes.c_size_t()
    ok = k32.ReadProcessMemory(h, ctypes.c_void_p(a), b, n, ctypes.byref(g))
    return b.raw[:g.value] if ok else None

def protect(h, page, prot):
    old = wt.DWORD()
    ok = k32.VirtualProtectEx(h, ctypes.c_void_p(page), 0x1000, prot, ctypes.byref(old))
    return ok, old.value

def get_set_tf(h, tid, on):
    th = k32.OpenThread(0x1FFFFF, False, tid)
    if not th: return None
    ctx = CONTEXT(); ctx.ContextFlags = 0x00010007   # i386|CONTROL|INTEGER
    ok = k32.Wow64GetThreadContext(th, ctypes.byref(ctx))
    eip = ctx.Eip; esp = ctx.Esp
    if ok:
        if on: ctx.EFlags |= 0x100
        else:  ctx.EFlags &= ~0x100
        k32.Wow64SetThreadContext(th, ctypes.byref(ctx))
    k32.CloseHandle(th)
    return (eip, esp) if ok else None

def main():
    page = int(sys.argv[1], 16) & ~0xFFF
    duration = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    max_hits = int(sys.argv[3]) if len(sys.argv) > 3 else 12
    h = k32.OpenProcess(0x1F0FFF, False, PID)
    ok, old = protect(h, page, PAGE_RW_GUARD)
    if not ok:
        print("VirtualProtectEx 失败"); return 1
    print(f"页 0x{page:X} 已加 GUARD（原保护 {old:#x}）")
    if not k32.DebugActiveProcess(PID):
        print("attach 失败"); return 1
    ev = DEBUG_EVENT()
    # 附加初潮（注意：先 attach 再 protect 顺序问题——初潮里的写会带 GUARD 异常，先吸掉再重加）
    protect(h, page, PAGE_RW)
    for _ in range(150):
        if not k32.WaitForDebugEvent(ctypes.byref(ev), 200): break
        k32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, DBG_CONTINUE)
    protect(h, page, PAGE_RW_GUARD)

    hits = []
    t0 = time.time()
    while time.time() - t0 < duration and len(hits) < max_hits:
        if not k32.WaitForDebugEvent(ctypes.byref(ev), 40): continue
        c = ev.dwDebugEventCode
        cont = DBG_CONTINUE
        if c == EXCEPTION_DEBUG_EVENT:
            exc = struct.unpack_from('<I', ev.u, 0)[0]
            tid = ev.dwThreadId
            if exc == GUARD:
                # 异常记录：Code/Flags/Record/Address/NumParams/Info[0..]
                nparams = struct.unpack_from('<I', ev.u, 16)[0]
                info0 = struct.unpack_from('<I', ev.u, 20)[0]
                info1 = struct.unpack_from('<I', ev.u, 24)[0]
                snap = get_set_tf(h, tid, True)
                protect(h, page, PAGE_RW)
                if snap and info0 == 1:   # 写访问
                    eip, esp = snap
                    stack = read_mem(h, esp, 0x200) or b''
                    rets = [struct.unpack_from('<I', stack, i)[0] for i in range(0, len(stack)-4, 4)]
                    rets = [v for v in rets if TEXT_LO <= v < TEXT_HI]
                    hits.append((eip, info1, rets[:20]))
                    print(f"★ 写 0x{info1:X} @EIP 0x{eip:X} (RVA 0x{eip-BASE:X}) 栈返回 {len(rets)}")
            elif exc == SINGLE_STEP:
                protect(h, page, PAGE_RW_GUARD)
                get_set_tf(h, tid, False)
            else:
                cont = 0x80010001
        k32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, cont)
    # 清理
    protect(h, page, PAGE_RW)
    time.sleep(0.05)
    k32.DebugActiveProcessStop(PID)
    print(f"命中 {len(hits)}，已脱离")
    for i, (eip, addr, rets) in enumerate(hits):
        print(f"\n[{i}] 被写=0x{addr:X} EIP=0x{eip:X} (RVA 0x{eip-BASE:X})")
        print("   栈:", " ".join(hex(r) for r in rets[:14]))
    k32.CloseHandle(h)
    return 0

if __name__ == "__main__":
    sys.exit(main())
