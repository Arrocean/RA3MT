# -*- coding: utf-8 -*-
"""python 版完整附加：等游戏 → 校验站点 → 分配块 → 装 15 个桩 → 就绪。
用法: python attach.py [--wait]
"""
import ctypes, ctypes.wintypes as wt, struct, sys, time, re, os

sys.path.insert(0, os.path.dirname(__file__))
import pystubs

k32 = ctypes.windll.kernel32
VM_READ, VM_WRITE, VM_OP = 0x10, 0x20, 0x8
PQI = 0x400
IMG = 0x400000

SITES_113 = {  # rva, displaced hex, stub id
    "zoom_unit_xp": (0x152115, "8B0CBA85C9", 5),
    "power_cool":   (0x216C7D, "F30F114644", 5),
    "build_power":  (0x314D19, "8B9818040000", 6),
    "power":        (0x31FEDF, "D986BC010000", 6),
    "sidebar_pts":  (0x333886, "8B48503B4E20", 6),
    "proto_cool_a": (0x33862C, "D9461C89465C", 6),
    "proto_cool_b": (0x3386CE, "F30F2C461C", 5),
    "unit_lv":      (0x3EB50C, "F30F118560020000", 8),
    "ammo":         (0x4622E0, "8B8178120000", 6),
    "ammo_2":       (0x4622C0, "8B8178120000", 6),
    "ammo_3":       (0x462300, "8B8178120000", 6),
    "ammo_4":       (0x4651B0, "8B8178120000", 6),
    "ammo_5":       (0x4651D0, "8B8178120000", 6),
    "ammo_6":       (0x4651F0, "8B8178120000", 6),
    "build_hp_a":   (0x467FC9, "8B70508B01", 5),
    "build_hp_b":   (0x468056, "8B51503B500C", 6),
    "money_h1":     (0x6698DD, "8B40048B8EB0030000", 9),
    "money_h2":     (0x6699CE, "0378048B11", 5),
    "money_h3":     (0x669A3C, "8B78348B4E3C", 6),
    "money_h4":     (0x669A85, "F30F104 72C".replace(" ", ""), 5),
}


def find_pid():
    TH32CS_SNAPPROCESS = 2
    class PE(ctypes.Structure):
        _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ProcessID", wt.DWORD),
                    ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)), ("th32ModuleID", wt.DWORD),
                    ("cntThreads", wt.DWORD), ("th32ParentProcessID", wt.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wt.DWORD),
                    ("szExeFile", ctypes.c_wchar * 260)]
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    pe = PE(); pe.dwSize = ctypes.sizeof(PE)
    ok = k32.Process32FirstW(snap, ctypes.byref(pe))
    while ok:
        if pe.szExeFile.startswith("ra3_1."):
            k32.CloseHandle(snap); return pe.th32ProcessID, pe.szExeFile
        ok = k32.Process32NextW(snap, ctypes.byref(pe))
    k32.CloseHandle(snap); return None, None


def module_base(pid, name):
    class ME(ctypes.Structure):
        _fields_ = [("dwSize", wt.DWORD), ("th32ModuleID", wt.DWORD), ("th32ProcessID", wt.DWORD),
                    ("GlblcntUsage", wt.DWORD), ("ProccntUsage", wt.DWORD),
                    ("modBaseAddr", ctypes.POINTER(ctypes.c_byte)), ("modBaseSize", wt.DWORD),
                    ("hModule", wt.HMODULE), ("szModule", ctypes.c_wchar * 256),
                    ("szExePath", ctypes.c_wchar * 260)]
    snap = k32.CreateToolhelp32Snapshot(0x8 | 0x10, pid)
    if snap in (0, -1): return None
    me = ME(); me.dwSize = ctypes.sizeof(ME)
    ok = k32.Module32FirstW(snap, ctypes.byref(me))
    while ok:
        if me.szModule.lower() == name.lower():
            k32.CloseHandle(snap)
            return ctypes.cast(me.modBaseAddr, ctypes.c_void_p).value
        ok = k32.Module32NextW(snap, ctypes.byref(me))
    k32.CloseHandle(snap); return None


def main():
    wait = "--wait" in sys.argv
    pid = None
    while True:
        pid, name = find_pid()
        if pid or not wait:
            break
        time.sleep(3)
    if not pid:
        print("游戏未运行"); return 1
    ver = re.search(r"ra3_(1\.\d+)\.game", name).group(1)
    if ver != "1.13":
        print(f"注意: 版本 {ver}（本脚本按 1.13 偏移安装）")
    h = k32.OpenProcess(VM_READ | VM_WRITE | VM_OP | PQI, False, pid)
    if not h:
        print("OpenProcess 失败（需要管理员）"); return 1
    base = module_base(pid, name)
    print(f"{name} pid={pid} base=0x{base:X}")

    def rd(addr, n):
        buf = ctypes.create_string_buffer(n); got = ctypes.c_size_t()
        if not k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, n, ctypes.byref(got)):
            return None
        return buf.raw[:got.value]

    def wr(addr, data):
        buf = ctypes.create_string_buffer(bytes(data), len(data)); got = ctypes.c_size_t()
        ok = k32.WriteProcessMemory(h, ctypes.c_void_p(addr), buf, len(data), ctypes.byref(got))
        if ok: k32.FlushInstructionCache(h, ctypes.c_void_p(addr), len(data))
        return ok

    # 1) 校验站点原始字节（已挂钩 E9 的跳过）
    bad = []
    for hid, (rva, disp, dlen) in SITES_113.items():
        got = rd(base + rva, dlen)
        if got is None:
            bad.append(hid); continue
        if got[0] == 0xE9:
            continue  # 已挂
        if got != bytes.fromhex(disp):
            bad.append(hid)
    if bad:
        print(f"站点字节校验失败: {bad} —— 版本不匹配？"); return 1
    print(f"20 站点字节校验通过")

    # 2) 每次全新分配块并全量重装（幂等：所有站点统一重指向新块；旧块泄漏 8KB 无害）
    block = k32.VirtualAllocEx(h, None, 0x2000, 0x3000, 0x40)  # RWX
    if not block:
        print("VirtualAllocEx 失败"); return 1
    wr(block, bytes(0x2000))
    print(f"MasterCode 块 = 0x{block:X}")

    # 3) 生成并写入桩（ammo 簇每个站点独立副本），补丁所有站点
    off = 0x40
    for sid, (rva, disp, dlen) in SITES_113.items():
        stub_id = "ammo" if sid.startswith("ammo") else sid
        site_va = base + rva
        code = pystubs.emit(stub_id, block + off, site_va + dlen, block, None)
        wr(block + off, code)
        patch = bytes([0xE9]) + struct.pack("<i", (block + off) - (site_va + 5)) + b"\x90" * (dlen - 5)
        wr(site_va, patch)
        print(f"  {sid:<14} site 0x{site_va:X} -> stub 0x{block+off:X} ({len(code)}B)")
        off += (len(code) + 15) & ~15
    print("全部安装完成 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
