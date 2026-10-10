# -*- coding: utf-8 -*-
"""Live probe: attach to the RUNNING RA3 process (read-only) and verify the
trainer's assumptions:
  1) detours installed (E9 at each hook site)
  2) player-root global: [root+0x28] = local player idx? money chain [root+0x3B0]
  3) selection vector: [sel+4]/[sel+8] begin/end — dump entries when count > 0
  4) watch selection changes for N seconds, dumping entry structure
"""
import ctypes, ctypes.wintypes as wt, struct, sys, time, re

k32 = ctypes.windll.kernel32
PROCESS_VM_READ = 0x10
PROCESS_QUERY_INFORMATION = 0x400

def find_pid():
    TH32CS_SNAPPROCESS = 2
    class PE(ctypes.Structure):
        _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD),
                    ("th32ProcessID", wt.DWORD), ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
                    ("th32ModuleID", wt.DWORD), ("cntThreads", wt.DWORD),
                    ("th32ParentProcessID", wt.DWORD), ("pcPriClassBase", ctypes.c_long),
                    ("dwFlags", wt.DWORD), ("szExeFile", ctypes.c_wchar * 260)]
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    pe = PE(); pe.dwSize = ctypes.sizeof(PE)
    ok = k32.Process32FirstW(snap, ctypes.byref(pe))
    out = []
    while ok:
        if pe.szExeFile.startswith("ra3_1."):
            out.append((pe.th32ProcessID, pe.szExeFile))
        ok = k32.Process32NextW(snap, ctypes.byref(pe))
    k32.CloseHandle(snap)
    return out

def module_base(pid, name):
    TH32CS_SNAPMODULE = 0x8
    TH32CS_SNAPMODULE32 = 0x10
    class ME(ctypes.Structure):
        _fields_ = [("dwSize", wt.DWORD), ("th32ModuleID", wt.DWORD),
                    ("th32ProcessID", wt.DWORD), ("GlblcntUsage", wt.DWORD),
                    ("ProccntUsage", wt.DWORD), ("modBaseAddr", ctypes.POINTER(ctypes.c_byte)),
                    ("modBaseSize", wt.DWORD), ("hModule", wt.HMODULE),
                    ("szModule", ctypes.c_wchar * 256), ("szExePath", ctypes.c_wchar * 260)]
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid)
    if snap == -1 or snap == 0:
        return None, None
    me = ME(); me.dwSize = ctypes.sizeof(ME)
    ok = k32.Module32FirstW(snap, ctypes.byref(me))
    while ok:
        if me.szModule.lower() == name.lower():
            base = ctypes.cast(me.modBaseAddr, ctypes.c_void_p).value
            k32.CloseHandle(snap)
            return base, me.modBaseSize
        ok = k32.Module32NextW(snap, ctypes.byref(me))
    k32.CloseHandle(snap)
    return None, None

procs = find_pid()
if not procs:
    print("!! 没有运行中的 ra3_1.x 进程"); sys.exit(1)
pid, name = procs[0]
print(f"进程: {name} pid={pid}")
h = k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
if not h:
    print("!! OpenProcess 失败（需要管理员）"); sys.exit(1)

def rd(addr, n):
    buf = ctypes.create_string_buffer(n)
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, n, ctypes.byref(got)):
        return None
    return buf.raw[:got.value]

def rdu32(addr):
    b = rd(addr, 4)
    return struct.unpack("<I", b)[0] if b and len(b) == 4 else None

def safe(addr, n=32):
    try:
        b = rd(addr, n)
        return b.hex(" ") if b else "<unreadable>"
    except Exception:
        return "<unreadable>"

base, size = module_base(pid, name)
print(f"模块基址: 0x{base:X} 大小 0x{size:X}")
mver = re.search(r"ra3_(1\.\d+)\.game", name)
ver = mver.group(1) if mver else "1.13"
V13 = ver == "1.13"

HOOKS = {
 "1.12": {"zoom_unit_xp":0x169D85,"power_cool":0x22B82D,"fast_build":0x312EB3,"build_power":0x329F19,
          "power":0x33511F,"sidebar_pts":0x348A06,"proto_a":0x34D77C,"proto_b":0x34D81E,"unit_lv":0x4005BC,
          "ammo":0x4770B0,"build_hp_a":0x47CB89,"build_hp_b":0x47CC16,"money_h1":0x664DAD,"money_h2":0x664E9E,
          "money_h3":0x664F0C,"money_h4":0x664F55},
 "1.13": {"zoom_unit_xp":0x152115,"power_cool":0x216C7D,"fast_build":0x2FDBB3,"build_power":0x314D19,
          "power":0x31FEDF,"sidebar_pts":0x333886,"proto_a":0x33862C,"proto_b":0x3386CE,"unit_lv":0x3EB50C,
          "ammo":0x462300,"build_hp_a":0x467FC9,"build_hp_b":0x468056,"money_h1":0x6698DD,"money_h2":0x6699CE,
          "money_h3":0x669A3C,"money_h4":0x669A85},
}[ "1.13" if V13 else "1.12" ]
ROOT_RVA  = 0x8E21A4 if V13 else 0x8DDE84
SEL_RVA   = 0x8E4C60 if V13 else 0x8E0940

print("\n== 1) 挂钩安装检查（首字节应为 E9） ==")
for hid, rva in HOOKS.items():
    b = rd(base + rva, 5)
    tag = "已挂钩" if b and b[0] == 0xE9 else ("原始" if b else "<不可读>")
    if hid in ("zoom_unit_xp","ammo","unit_lv","build_power","fast_build","power_cool") or b and b[0]==0xE9:
        print(f"  {hid:<14} 0x{base+rva:X}: {b.hex(' ') if b else '?'} [{tag}]")

print("\n== 2) 玩家上下文 root ==")
root = rdu32(base + ROOT_RVA)
print(f"  root = [0x{base+ROOT_RVA:X}] = 0x{root:X}" if root else "  root 不可读")
if root:
    print(f"  [root+0x28] (本地玩家idx?) = {rdu32(root+0x28)}")
    print(f"  [root+0x1BC] (电力float?)  = {struct.unpack('<f', struct.pack('<I', rdu32(root+0x1BC)))[0] if rdu32(root+0x1BC) else '?'}")
    money = rdu32(root + 0x3B0)
    print(f"  [root+0x3B0] (资金对象?)   = 0x{money:X}" if money else "  [root+0x3B0] 空")
    if money:
        m, p = rdu32(money+4), rdu32(money+8)
        print(f"    [money+0x4] = {m}   [money+0x8] = {p}")

print("\n== 3) 选中列表向量 ==")
selroot = rdu32(base + SEL_RVA)
print(f"  selroot = [0x{base+SEL_RVA:X}] = 0x{selroot:X}" if selroot else "  selroot 不可读")
def dump_sel():
    s = rdu32(base + SEL_RVA)
    if not s: return
    begin, end = rdu32(s+4), rdu32(s+8)
    if begin is None or end is None or end < begin:
        print(f"    selroot 0x{s:X}: begin/end 不可读"); return
    n = (end - begin) // 4
    print(f"    selroot 0x{s:X}: begin=0x{begin:X} end=0x{end:X} count={n}")
    for i in range(min(n, 10)):
        e = rdu32(begin + 4*i)
        if not e: continue
        print(f"      entry[{i}] = 0x{e:X}")
        print(f"        +00: {safe(e, 0x40)}")
        o8 = rdu32(e + 8)
        if o8:
            print(f"        [+8]=0x{o8:X}  [+8]: {safe(o8, 0x20)}")
            u = rdu32(o8 + 0x138)
            print(f"        [+8]+0x138 = 0x{u:X}" if u else "        [+8]+0x138 不可读")
            if u:
                for off, label in ((0x33C,"hp?"),(0x374,"move?"),(0x37C,"speednode?"),(0x3CC,"lv?"),(0x418,"owner?")):
                    v = rdu32(u + off)
                    print(f"          unit+{label:<10} = 0x{v:X}" if v else f"          unit+{label} 不可读")

dump_sel()
print("\n== 4) 监视选中变化 60 秒（请在游戏里切换选中单位） ==")
last = None
t0 = time.time()
while time.time() - t0 < 60:
    s = rdu32(base + SEL_RVA)
    if s:
        begin, end = rdu32(s+4) or 0, rdu32(s+8) or 0
        n = (end - begin)//4 if end >= begin else -1
        if n != last:
            print(f"  [{time.time()-t0:4.1f}s] 选中数 = {n}")
            if n and n > 0:
                dump_sel()
            last = n
    time.sleep(0.5)
print("probe done")
