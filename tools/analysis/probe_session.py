# -*- coding: utf-8 -*-
"""只读探针：反推 C# 修改器的 MasterCode 块 → 读诊断槽 + 选中列表全局。
不写任何内存。用法: python probe_session.py"""
import ctypes, ctypes.wintypes as wt, struct, sys

k32 = ctypes.windll.kernel32
VM_READ, VM_WRITE, VM_OP = 0x10, 0x20, 0x8
PQI = 0x400
PID = 43776
IMG = 0x400000

h = k32.OpenProcess(VM_READ | VM_WRITE | VM_OP | PQI, False, PID)
assert h, "OpenProcess 失败"


def rd(addr, n):
    buf = ctypes.create_string_buffer(n)
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, n, ctypes.byref(got)):
        return None
    return buf.raw[:got.value]


def u32(addr):
    b = rd(addr, 4)
    return struct.unpack("<I", b)[0] if b and len(b) == 4 else 0


# 模块基址
def module_base(pid, name):
    class ME(ctypes.Structure):
        _fields_ = [("dwSize", wt.DWORD), ("th32ModuleID", wt.DWORD), ("th32ProcessID", wt.DWORD),
                    ("GlblcntUsage", wt.DWORD), ("ProccntUsage", wt.DWORD),
                    ("modBaseAddr", ctypes.POINTER(ctypes.c_byte)), ("modBaseSize", wt.DWORD),
                    ("hModule", wt.HMODULE), ("szModule", ctypes.c_wchar * 256),
                    ("szExePath", ctypes.c_wchar * 260)]
    snap = k32.CreateToolhelp32Snapshot(0x8 | 0x10, pid)
    me = ME(); me.dwSize = ctypes.sizeof(ME)
    ok = k32.Module32FirstW(snap, ctypes.byref(me))
    while ok:
        if me.szModule.lower() == name.lower():
            return ctypes.cast(me.modBaseAddr, ctypes.c_void_p).value
        ok = k32.Module32NextW(snap, ctypes.byref(me))
    return None


base = module_base(PID, "ra3_1.13.game")
print(f"base = 0x{base:X}")

# --- 1) 从多个站点反推 MasterCode 块（E9 rel32 → 桩 → 桩按 16 对齐、从 0x40 排布）---
SITES = {"zoom_unit_xp": 0x152115, "build_power": 0x314D19, "money_h1": 0x6698DD,
         "ammo": 0x4622E0, "power_cool": 0x216C7D}
block_guess = {}
for hid, rva in SITES.items():
    b = rd(base + rva, 5)
    if b is None:
        print(f"{hid}: 不可读"); continue
    if b[0] != 0xE9:
        print(f"{hid}: 未挂钩，字节 {b.hex().upper()}")
        continue
    rel = struct.unpack("<i", b[1:5])[0]
    stub = base + rva + 5 + rel
    # 桩是独立 alloc 的块，块基址 = 桩地址向下对齐不好反推 → 直接读桩首字节找 jmp 回跳前 Payne:
    # 更可靠：读桩开头若干字节，匹配已知桩序列头（money_h1 桩以 9C(推标志) 开头）
    print(f"{hid}: site 0x{base+rva:X} -> stub 0x{stub:X} (首字节 {rd(stub,4).hex().upper()})")
    block_guess[hid] = stub

# MasterCode 块与桩不同分配：C# 里 Block 是独立 alloc，桩写在 Block+0x40 起
# → stub_va - 0x40 = Block（第一个站点按字典序 ammo）。校验：块 0x0C 处 = capture flag 等。
if "ammo" in block_guess:
    cand = block_guess["ammo"] - 0x40
    tail = rd(cand + 0xFF0, 16)
    print(f"\n候选 Block = 0x{cand:X}  尾部 16B = {tail.hex().upper() if tail else '?'}")
    for off, nm in [(0x00, "money"), (0x01, "power"), (0x04, "fastbuild"), (0x05, "instantready"),
                    (0x06, "freezeenemy"), (0x07, "zoom"), (0x08, "revealmap"),
                    (0x09, "xp999"), (0x0A, "ammo"), (0x0C, "capture_sel")]:
        v = rd(cand + off, 1)
        print(f"  flag[{nm:<12}] = {v[0] if v else '?'}")
    diag = rd(cand + 0x10, 0x20)
    if diag:
        esi, prodEax, prodEsi, owner, selEntry, selArr, selIdx, weapon = struct.unpack("<8I", diag)
        print(f"  diag: playerEsi=0x{esi:X} prodEax=0x{prodEax:X} prodEsi=0x{prodEsi:X} "
              f"owner=0x{owner:X}")
        print(f"        selEntry=0x{selEntry:X} selArr=0x{selArr:X} selIdx={selIdx} weapon=0x{weapon:X}")
        if esi > 0x10000:
            side = u32(esi + 0x1188)
            print(f"        [playerEsi+0x1188] = 0x{side:X}")
            if prodEax > 0x10000:
                print(f"        [prodEax+0x418] = 0x{u32(prodEax + 0x418):X}  (owner 槽现值)")
                print(f"        [prodEax+0x20] = {struct.unpack('<f', rd(prodEax+0x20,4))[0]:.2f} / 0x{u32(prodEax+0x20):X}")
        if weapon > 0x10000:
            print(f"        weapon [+4]={u32(weapon+4)} [+8]={u32(weapon+8)} "
                  f"[+0xC]={u32(weapon+0xC)} [+0x1C]byte={rd(weapon+0x1C,1)[0]}")
        if selEntry > 0x10000:
            print(f"        selEntry vtable=0x{u32(selEntry):X} [+8]=0x{u32(selEntry+8):X} [+0xC]=0x{u32(selEntry+0xC):X} [+0x1C]={u32(selEntry+0x1C)}")
            a = u32(selEntry + 8)
            if a > 0x10000:
                body = u32(a + 0x10)
                print(f"        entry+8 -> A=0x{a:X} (vtable 0x{u32(a):X})  A+0x10 -> body=0x{body:X} (vtable 0x{u32(body):X})")
                if body > 0x10000:
                    hp = u32(body + 0x33C)
                    print(f"        body+0x33C -> hpObj=0x{hp:X}" + (f"  hp={struct.unpack('<f', rd(hp+4,4))[0]:.0f}/{struct.unpack('<f', rd(hp+0xC,4))[0]:.0f}/{struct.unpack('<f', rd(hp+0x10,4))[0]:.0f}" if hp > 0x10000 else ""))
                    print(f"        body+0x418 = 0x{u32(body+0x418):X}")

# --- 2) 选中列表全局 ---
SEL = base + 0x8E4C60
root = u32(SEL)
print(f"\n选中列表全局 [0x{SEL:X}] = 0x{root:X}")
if root > 0x10000:
    beg, end = u32(root + 4), u32(root + 8)
    print(f"  root=0x{root:X} vtable=0x{u32(root):X} begin=0x{beg:X} end=0x{end:X} count={(end-beg)//4}")
    for i in range(min((end - beg) // 4, 16)):
        e = u32(beg + i * 4)
        if e < 0x10000:
            print(f"  [{i}] entry=0x{e:X} (空)"); continue
        a = u32(e + 8)
        body = u32(a + 0x10) if a > 0x10000 else 0
        line = f"  [{i}] entry=0x{e:X} vtbl=0x{u32(e):X} +8->0x{a:X}"
        if body > 0x10000:
            hp = u32(body + 0x33C)
            hpv = struct.unpack('<f', rd(hp + 4, 4))[0] if hp > 0x10000 else -1
            line += f" body=0x{body:X} vtbl=0x{u32(body):X} hp={hpv:.0f} owner=0x{u32(body+0x418):X} lv(+3CC)={u32(body+0x3CC)}"
        print(line)
else:
    print("  root 无效（可能未在对局或未选中）")
    inner = u32(SEL)
    if inner:
        print(f"  [SEL]=0x{inner:X} [+4]=0x{u32(SEL+4):X} [+8]=0x{u32(SEL+8):X}")

# --- 3) playerRoot 全局 ---
PR = base + 0x8E21A4
pr = u32(PR)
print(f"\nplayerRoot [0x{PR:X}] = 0x{pr:X}" + (f"  [+0x28]={u32(pr+0x28)}" if pr > 0x10000 else ""))

k32.CloseHandle(h)
