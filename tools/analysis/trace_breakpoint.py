"""INT3 breakpoint tracer: catch the real call chain when the user kills a unit
(mode kill) or attempts a building placement (mode place). 64-bit Python on the
32-bit game; uses Wow64Get/SetThreadContext. Must run as admin.

Hard lessons baked in (each one killed the game once):
  * Plant the INT3 only while every thread is suspended, attach afterwards.
    A raw int3 with no debugger listening terminates the process
    (event log 0x4000001f @0x3513F0).
  * WOW64 surfaces a 32-bit int3 as STATUS_WX86_BREAKPOINT (0x4000001f), not
    0x80000003; pass anything else back unhandled and the game dies.
  * DebugSetProcessKillOnExit(False): if this tracer dies for any reason the
    game must survive.

Usage: py tools/analysis/trace_breakpoint.py kill|place [seconds] [max_samples] [pid]
"""
import ctypes
import ctypes.wintypes as wt
import struct
import sys
import time

k32 = ctypes.windll.kernel32

DBG_CONTINUE = 0x00010002
DBG_EXCEPTION_NOT_HANDLED = 0x80010001
EXCEPTION_BREAKPOINT = 0x80000003
EXCEPTION_SINGLE_STEP = 0x80000004
WX86_BREAKPOINT = 0x4000001F
WX86_SINGLE_STEP = 0x4000001E

TEXT_LO, TEXT_HI = 0x401000, 0xBD0000

# 1.13 targets (VA = RVA + 0x400000)
TARGETS = {
    'kill': [(0x7513F0, 'death-marker 0x3513F0')],
    'place': [(0x511E00, 'placement-grid check 0x111E00')],
}


class CONTEXT32(ctypes.Structure):
    _pack_ = 16
    _fields_ = [
        ("ContextFlags", ctypes.c_uint32),
        ("Dr0", ctypes.c_uint32), ("Dr1", ctypes.c_uint32),
        ("Dr2", ctypes.c_uint32), ("Dr3", ctypes.c_uint32),
        ("Dr6", ctypes.c_uint32), ("Dr7", ctypes.c_uint32),
        ("FloatSave", ctypes.c_uint8 * 112),
        ("SegGs", ctypes.c_uint32), ("SegFs", ctypes.c_uint32),
        ("SegEs", ctypes.c_uint32), ("SegDs", ctypes.c_uint32),
        ("Edi", ctypes.c_uint32), ("Esi", ctypes.c_uint32), ("Ebx", ctypes.c_uint32),
        ("Edx", ctypes.c_uint32), ("Ecx", ctypes.c_uint32), ("Eax", ctypes.c_uint32),
        ("Ebp", ctypes.c_uint32), ("Eip", ctypes.c_uint32), ("SegCs", ctypes.c_uint32),
        ("EFlags", ctypes.c_uint32), ("Esp", ctypes.c_uint32), ("SegSs", ctypes.c_uint32),
        ("ExtendedRegisters", ctypes.c_uint8 * 416),
    ]


class DEBUG_EVENT(ctypes.Structure):
    _fields_ = [
        ("dwDebugEventCode", ctypes.c_uint32),
        ("dwProcessId", ctypes.c_uint32),
        ("dwThreadId", ctypes.c_uint32),
        ("u", ctypes.c_uint8 * 176),
    ]


def read_mem(h, addr, size):
    buf = ctypes.create_string_buffer(size)
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, size, ctypes.byref(got)):
        return None
    return buf.raw[:got.value]


def write_mem(h, addr, data):
    old = ctypes.c_uint32()
    if not k32.VirtualProtectEx(h, ctypes.c_void_p(addr), len(data), 0x40, ctypes.byref(old)):
        return False
    ok = k32.WriteProcessMemory(h, ctypes.c_void_p(addr), data, len(data), None)
    k32.VirtualProtectEx(h, ctypes.c_void_p(addr), len(data), old, None)
    return ok


def get_ctx(th):
    ctx = CONTEXT32()
    ctx.ContextFlags = 0x00110007
    if not k32.Wow64GetThreadContext(th, ctypes.byref(ctx)):
        return None
    return ctx


def set_ctx(th, ctx):
    return k32.Wow64SetThreadContext(th, ctypes.byref(ctx))


def threads_of(pid):
    class TE(ctypes.Structure):
        _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ThreadID", wt.DWORD),
                    ("th32OwnerProcessID", wt.DWORD), ("tpBasePri", ctypes.c_long),
                    ("tpDeltaPri", ctypes.c_long), ("dwFlags", wt.DWORD)]
    snap = k32.CreateToolhelp32Snapshot(0x4, pid)
    te = TE()
    te.dwSize = ctypes.sizeof(TE)
    out = []
    ok = k32.Thread32First(snap, ctypes.byref(te))
    while ok:
        if te.th32OwnerProcessID == pid:
            out.append(te.th32ThreadID)
        ok = k32.Thread32Next(snap, ctypes.byref(te))
    k32.CloseHandle(snap)
    return out


def suspend_all(pid):
    handles = []
    for tid in threads_of(pid):
        th = k32.OpenThread(0x0002 | 0x0004 | 0x0001, False, tid)  # SUSPEND_RESUME
        if th:
            k32.SuspendThread(th)
            handles.append(th)
    return handles


def resume_all(handles):
    for th in handles:
        k32.ResumeThread(th)
        k32.CloseHandle(th)


def find_game():
    class PE(ctypes.Structure):
        _fields_ = [('dwSize', ctypes.c_ulong), ('cntUsage', ctypes.c_ulong),
                    ('th32ProcessID', ctypes.c_ulong), ('th32ModuleID', ctypes.c_ulong),
                    ('cntThreads', ctypes.c_ulong), ('th32ParentProcessID', ctypes.c_ulong),
                    ('pcPriClassBase', ctypes.c_long), ('dwFlags', ctypes.c_ulong),
                    ('szExeFile', ctypes.c_char * 260)]
    procs = []
    lppe = PE()
    lppe.dwSize = ctypes.sizeof(PE)
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)
    if k32.Process32First(snap, ctypes.byref(lppe)):
        while k32.Process32Next(snap, ctypes.byref(lppe)):
            if lppe.szExeFile.decode().startswith('ra3_1.1'):
                procs.append(lppe.th32ProcessID)
    k32.CloseHandle(snap)
    return procs[0] if procs else None


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'kill'
    duration = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    max_samples = int(sys.argv[3]) if len(sys.argv) > 3 else 8
    targets = TARGETS[mode]
    pid = int(sys.argv[4], 0) if len(sys.argv) > 4 else find_game()
    if not pid:
        raise SystemExit('game not running')
    print(f'game PID {pid}; mode {mode}; {duration}s / {max_samples} samples', flush=True)
    print('targets: ' + ', '.join(f'0x{a:X}({n})' for a, n in targets), flush=True)

    h = k32.OpenProcess(0x1F0FFF, False, pid)
    if not h:
        raise SystemExit('OpenProcess failed (admin?)')

    # CRITICAL ORDER: attach FIRST, then plant. A raw int3 with no debugger
    # listening terminates the process (event log 0x4000001f @0x3513F0, four
    # crashes). Suspending threads cannot close that window: SuspendThread is
    # asynchronous and the thread may still run a few instructions afterwards.
    # With the debugger attached, an int3 always surfaces as a debug event.
    originals = {}
    if not k32.DebugActiveProcess(pid):
        raise SystemExit('DebugActiveProcess failed')
    k32.DebugSetProcessKillOnExit(False)   # a dead tracer must never kill the game

    samples = []
    pending = {}   # tid -> addr (single-stepping over a replanted breakpoint)
    try:
        ev = DEBUG_EVENT()
        # absorb attach events; the game stays paused until these are continued
        for _ in range(2000):
            if not k32.WaitForDebugEvent(ctypes.byref(ev), 30):
                break
            k32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, DBG_CONTINUE)
        print('attached; planting INT3 with the debugger present', flush=True)
        for addr, name in targets:
            head = read_mem(h, addr, 1)
            if head is None or head[0] == 0xCC:
                raise SystemExit(f'0x{addr:X} unreadable or already CC')
            originals[addr] = head[0]
            if not write_mem(h, addr, b'\xCC'):
                raise SystemExit(f'cannot plant at 0x{addr:X}')
        print('INT3 planted - waiting for events (play normally)...', flush=True)
        t0 = time.time()
        while time.time() - t0 < duration and len(samples) < max_samples:
            if not k32.WaitForDebugEvent(ctypes.byref(ev), 50):
                continue
            cont = DBG_CONTINUE
            if ev.dwDebugEventCode == 1:  # EXCEPTION_DEBUG_EVENT
                exc_code = struct.unpack_from('<I', ev.u, 0)[0]
                tid = ev.dwThreadId
                if exc_code in (EXCEPTION_BREAKPOINT, WX86_BREAKPOINT):
                    th = k32.OpenThread(0x1FFFFF, False, tid)
                    ctx = get_ctx(th)
                    if ctx and ctx.Eip - 1 in originals:
                        addr = ctx.Eip - 1
                        write_mem(h, addr, bytes([originals[addr]]))
                        ctx.Eip = addr
                        ctx.EFlags |= 0x100
                        set_ctx(th, ctx)
                        pending[tid] = addr
                        esp = ctx.Esp
                        stack = read_mem(h, esp, 0x120) or b''
                        rets = [struct.unpack_from('<I', stack, i)[0]
                                for i in range(0, len(stack) - 4, 4)]
                        rets = [v for v in rets if TEXT_LO <= v < TEXT_HI]
                        arg1 = struct.unpack_from('<I', stack, 4)[0] if len(stack) >= 8 else 0
                        samples.append({
                            'site': addr, 'eax': ctx.Eax, 'ecx': ctx.Ecx, 'edx': ctx.Edx,
                            'esi': ctx.Esi, 'edi': ctx.Edi, 'esp': esp,
                            'arg1': arg1, 'rets': rets[:20],
                        })
                        print(f'* hit 0x{addr:X} tid {tid} arg1=0x{arg1:X} '
                              f'rets={[hex(r) for r in rets[:6]]}', flush=True)
                    else:
                        cont = DBG_EXCEPTION_NOT_HANDLED
                    if th:
                        k32.CloseHandle(th)
                elif exc_code in (EXCEPTION_SINGLE_STEP, WX86_SINGLE_STEP):
                    th = k32.OpenThread(0x1FFFFF, False, tid)
                    ctx = get_ctx(th)
                    if ctx and tid in pending:
                        addr = pending.pop(tid)
                        write_mem(h, addr, b'\xCC')   # re-arm
                        ctx.EFlags &= ~0x100
                        set_ctx(th, ctx)
                    else:
                        cont = DBG_EXCEPTION_NOT_HANDLED
                    if th:
                        k32.CloseHandle(th)
                else:
                    cont = DBG_EXCEPTION_NOT_HANDLED
            k32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, cont)
    finally:
        # restore bytes while the debugger is still attached (same safety rule)
        for addr, byte in originals.items():
            write_mem(h, addr, bytes([byte]))
        k32.DebugActiveProcessStop(pid)
        print(f'detached; {len(samples)} samples', flush=True)

    print('==== samples ====', flush=True)
    for s in samples:
        print(f"site 0x{s['site']:X} arg1=0x{s['arg1']:X} eax=0x{s['eax']:X} "
              f"ecx=0x{s['ecx']:X} esi=0x{s['esi']:X}")
        print('  ret chain: ' + ' '.join(hex(r) for r in s['rets']))
    if not samples:
        print('(no hits - was the action performed while attached?)')


if __name__ == '__main__':
    main()
