# -*- coding: utf-8 -*-
"""Python port of RA3MT.Core's stub emitter (StubGen) — byte-compatible.
Only what the overnight test harness needs: full 16-stub set with the v5
semantics (money cap, esi+0x1188 owner check, capture array, diag captures)."""
import struct

# 块内布局（与 C# MasterCode 一致）
FLAGS = {
    "money": 0x00, "power": 0x01, "scpoints": 0x02, "allproto": 0x03,
    "fastbuild": 0x04, "instantready": 0x05, "freezeenemy": 0x06,
    "zoom": 0x07, "revealmap": 0x08, "xp999": 0x09, "ammo": 0x0A,
    "capture_sel": 0x0C,
}
DIAG = {"player": 0x10, "prodEax": 0x14, "prodEsi": 0x18, "owner": 0x1C,
        "selEntry": 0x20, "selArr": 0x24, "selIdx": 0x28, "weapon": 0x2C}
CAPTURE_COUNT = 0xFFC
CAPTURE_ARRAY = 0x1000
SIDE_OFF = 0x1188

R = {"eax": 0, "ecx": 1, "edx": 2, "ebx": 3, "esp": 4, "ebp": 5, "esi": 6, "edi": 7}


def modrm(mod, reg, rm):
    return (mod << 6) | (reg << 3) | rm


class Asm:
    def __init__(self):
        self.b = bytearray()
        self.rel8 = []      # (pos, label)
        self.rel32 = []     # (pos, target_va)
        self.labels = {}

    def db(self, *bs):
        self.b += bytes(bs)

    def d32(self, v):
        self.b += struct.pack("<I", v & 0xFFFFFFFF)

    # 跳转
    def label(self, i):
        self.labels[i] = len(self.b)

    def _jcc8(self, op, lbl):
        self.db(op)
        self.rel8.append((len(self.b), lbl))
        self.db(0)

    def je(self, l): self._jcc8(0x74, l)
    def jne(self, l): self._jcc8(0x75, l)
    def jae(self, l): self._jcc8(0x73, l)
    def jmp_short(self, l): self._jcc8(0xEB, l)
    def jmp_to(self, va):
        self.db(0xE9); self.rel32.append((len(self.b), va)); self.d32(0)

    # 保留/栈
    def pushfd(self): self.db(0x9C)
    def popfd(self): self.db(0x9D)
    def pushad(self): self.db(0x60)
    def popad(self): self.db(0x61)
    def push_r(self, r): self.db(0x50 + R[r])
    def push8(self, i): self.db(0x6A, i)
    def add_esp8(self, i): self.db(0x83, 0xC4, i)
    def inc_r(self, r): self.db(0xFF, 0xC0 + R[r])
    def ret(self): self.db(0xC3)

    # mov/cmp/add
    def cmp_m8_abs(self, addr, imm): self.db(0x80, 0x3D); self.d32(addr); self.db(imm)
    def mov_m8_abs(self, addr, imm): self.db(0xC6, 0x05); self.d32(addr); self.db(imm)
    def mov_m32_abs_imm(self, addr, imm): self.db(0xC7, 0x05); self.d32(addr); self.d32(imm)
    def mov_m32_r_disp8_imm32(self, r, disp, imm):
        self.db(0xC7, modrm(1, 0, R[r])); self.db(disp); self.d32(imm)
    def mov_m32_r_disp32_imm32(self, r, disp, imm):
        self.db(0xC7, modrm(2, 0, R[r])); self.d32(disp); self.d32(imm)
    def add_m32_r_disp8_imm32(self, r, disp, imm):
        self.db(0x81, modrm(1, 0, R[r])); self.db(disp); self.d32(imm)
    def add_m32_r_disp8_imm8(self, r, disp, imm):
        self.db(0x83, modrm(1, 0, R[r])); self.db(disp, imm)
    def cmp_m32_r_disp8_imm32(self, r, disp, imm):
        self.db(0x81, modrm(1, 7, R[r])); self.db(disp); self.d32(imm)
    def cmp_r_imm32(self, r, imm):
        self.db(0x81, modrm(3, 7, R[r])); self.d32(imm)
    def mov_r_abs(self, r, addr):
        if R[r] == 0: self.db(0xA1); self.d32(addr)
        else: self.db(0x8B, modrm(0, R[r], R["ebp"])); self.d32(addr)
    def mov_m32_abs_r(self, r, addr):
        self.db(0x89, modrm(0, R[r], R["ebp"])); self.d32(addr)
    def mov_r_r_disp8(self, dst, src, disp):
        self.db(0x8B, modrm(1, R[dst], R[src])); self.db(disp)
    def mov_r_r_disp32(self, dst, src, disp):
        self.db(0x8B, modrm(2, R[dst], R[src])); self.d32(disp)
    def mov_r_esp_disp32(self, dst, disp):
        self.db(0x8B, modrm(2, R[dst], R["esp"]), 0x24); self.d32(disp)
    def mov_r_r_ind(self, dst, src):
        assert R[src] != R["ebp"]
        self.db(0x8B, modrm(0, R[dst], R[src]))
    def cmp_r_m_r_disp32(self, reg, rm, disp):
        self.db(0x3B, modrm(2, R[reg], R[rm])); self.d32(disp)
    def cmp_r_m_esp_disp32(self, reg, disp):
        self.db(0x3B, modrm(2, R[reg], R["esp"]), 0x24); self.d32(disp)
    def test_rr(self, a, b): self.db(0x85, modrm(3, R[a], R[b]))
    def mov_m_scaled_idx(self, idx, base, src):
        sib = (2 << 6) | (R[idx] << 3) | 5
        self.db(0x89, modrm(0, R[src], R["esp"]), sib); self.d32(base)
    def inc_m32_abs(self, addr):
        self.db(0xFF, 0x05); self.d32(addr)

    def build(self, base_va):
        out = bytearray(self.b)
        for pos, lbl in self.rel8:
            out[pos] = (self.labels[lbl] - (pos + 1)) & 0xFF
        for pos, tgt in self.rel32:
            struct.pack_into("<i", out, pos, tgt - (base_va + pos + 4))
        return bytes(out)


def emit(stub_id, stub_va, site_end, block, root_esi_slot):
    """root_esi_slot = block + DIAG['player']（敌我判定锚）"""
    def flag(a, name): a.cmp_m8_abs(block + FLAGS[name], 1)

    c = {"va": stub_va, "end": site_end}

    def fin(a):
        a.jmp_to(site_end)
        return a.build(stub_va)

    if stub_id == "money_h2":
        a = Asm(); a.pushfd(); flag(a, "money"); a.jne(1)
        a.cmp_m32_r_disp8_imm32("eax", 0x04, 10000000); a.jae(6)
        a.add_m32_r_disp8_imm32("eax", 0x04, 100000); a.label(6)
        a.mov_m32_r_disp8_imm32("eax", 0x08, 0x05F5E0FF)
        a.label(1); a.popfd()
        a.db(0x03, 0x78, 0x04, 0x8B, 0x11)
        return fin(a)

    if stub_id == "money_h1":
        a = Asm(); a.pushfd()
        a.mov_m32_abs_r("esi", block + DIAG["player"])     # 诊断+敌我锚
        flag(a, "power"); a.jne(1)
        a.mov_m32_r_disp8_imm32("eax", 0x04, 100000)
        a.mov_m32_r_disp8_imm32("eax", 0x08, 0)
        a.label(1); a.popfd()
        a.db(0x8B, 0x40, 0x04, 0x8B, 0x8E, 0xB0, 0x03, 0x00, 0x00)
        return fin(a)

    if stub_id == "money_h3":
        a = Asm(); a.pushfd(); flag(a, "scpoints"); a.jne(1)
        a.mov_m32_r_disp8_imm32("eax", 0x34, 99)
        a.label(1); a.popfd()
        a.db(0x8B, 0x78, 0x34, 0x8B, 0x4E, 0x3C)
        return fin(a)

    if stub_id == "money_h4":
        a = Asm(); a.pushfd(); flag(a, "allproto"); a.jne(1)
        a.mov_m32_r_disp8_imm32("edi", 0x2C, 0x43C78000)
        a.label(1); a.popfd()
        a.db(0xF3, 0x0F, 0x10, 0x47, 0x2C)
        return fin(a)

    if stub_id == "proto_cool_a":
        a = Asm(); a.pushfd(); flag(a, "fastbuild"); a.jne(1)
        a.mov_m32_r_disp8_imm32("esi", 0x1C, 0x42C80000)
        a.label(1); a.popfd()
        a.db(0xD9, 0x46, 0x1C, 0x89, 0x46, 0x5C)
        return fin(a)

    if stub_id == "proto_cool_b":
        a = Asm(); a.pushfd(); flag(a, "fastbuild"); a.jne(1)
        a.mov_m32_r_disp8_imm32("esi", 0x1C, 0x42C80000)
        a.label(1); a.popfd()
        a.db(0xF3, 0x0F, 0x2C, 0x46, 0x1C)
        return fin(a)

    if stub_id == "power":
        a = Asm(); a.pushfd(); flag(a, "fastbuild"); a.jne(1)
        a.db(0x83, 0xFD, 0x01); a.je(1)
        a.pushad()
        a.mov_r_r_disp8("eax", "edi", 0x3C); a.inc_r("eax")
        a.db(0x89, 0x47, 0x14)
        a.popad(); a.label(1); a.popfd()
        a.db(0xD9, 0x86, 0xBC, 0x01, 0x00, 0x00)
        return fin(a)

    if stub_id == "build_power":
        a = Asm(); a.pushfd(); a.pushad()
        # 诊断捕获
        a.mov_m32_abs_r("eax", block + DIAG["prodEax"])
        a.mov_m32_abs_r("esi", block + DIAG["prodEsi"])
        a.mov_r_r_disp32("edx", "eax", 0x418)
        a.mov_m32_abs_r("edx", block + DIAG["owner"])
        # [06] 属主==己方 → 归零
        flag(a, "instantready"); a.jne(2)
        a.mov_r_abs("ebx", block + DIAG["player"]); a.test_rr("ebx", "ebx"); a.je(2)
        a.mov_r_r_disp32("ecx", "ebx", SIDE_OFF)
        a.cmp_r_m_r_disp32("ecx", "eax", 0x418); a.jne(2)
        a.mov_m32_r_disp8_imm32("esi", 0x20, 0)
        # [07] 属主!=己方 → +1
        a.label(2); flag(a, "freezeenemy"); a.jne(3)
        a.mov_r_abs("ebx", block + DIAG["player"]); a.test_rr("ebx", "ebx"); a.je(3)
        a.mov_r_r_disp32("ecx", "ebx", SIDE_OFF)
        a.cmp_r_m_r_disp32("ecx", "eax", 0x418); a.je(3)
        a.add_m32_r_disp8_imm8("esi", 0x20, 1)
        a.label(3); a.popad(); a.popfd()
        a.db(0x8B, 0x98, 0x18, 0x04, 0x00, 0x00)   # 重放 mov ebx,[eax+418]
        return fin(a)

    if stub_id == "build_hp_a":
        a = Asm()
        a.db(0x8B, 0x70, 0x50, 0x8B, 0x01)          # 先重放 mov esi,[eax+50]; mov eax,[ecx]
        a.pushfd(); a.pushad()
        # [06] 属主==己方 → 归零（eax 已是 [ecx]）
        flag(a, "instantready"); a.jne(2)
        a.mov_r_abs("ebx", block + DIAG["player"]); a.test_rr("ebx", "ebx"); a.je(2)
        a.mov_r_r_disp32("ecx", "ebx", SIDE_OFF)
        a.cmp_r_m_esp_disp32("ecx", 0x2C); a.jne(2)
        a.mov_m32_r_disp8_imm32("eax", 0x0C, 0)
        a.mov_r_r_ind("eax", "eax")
        a.mov_m32_r_disp8_imm32("eax", 0x0C, 0)
        # [07] 属主!=己方 → +1 两次
        a.label(2); flag(a, "freezeenemy"); a.jne(3)
        a.mov_r_abs("ebx", block + DIAG["player"]); a.test_rr("ebx", "ebx"); a.je(3)
        a.mov_r_r_disp32("ecx", "ebx", SIDE_OFF)
        a.cmp_r_m_esp_disp32("ecx", 0x2C); a.je(3)
        a.add_m32_r_disp8_imm8("eax", 0x0C, 1)
        a.mov_r_r_ind("eax", "eax")
        a.add_m32_r_disp8_imm8("eax", 0x0C, 1)
        a.label(3); a.popad(); a.popfd()
        return fin(a)

    if stub_id == "build_hp_b":
        a = Asm()
        a.db(0x8B, 0x51, 0x50, 0x3B, 0x50, 0x0C)
        a.pushfd(); a.pushad()
        flag(a, "freezeenemy"); a.jne(3)
        a.add_m32_r_disp8_imm8("eax", 0x0C, 1)
        a.mov_r_r_ind("eax", "eax")
        a.add_m32_r_disp8_imm8("eax", 0x0C, 1)
        a.label(3); a.popad(); a.popfd()
        return fin(a)

    if stub_id == "sidebar_pts":
        a = Asm()
        a.db(0x8B, 0x48, 0x50, 0x3B, 0x4E, 0x20)
        a.pushfd(); a.pushad()
        flag(a, "freezeenemy"); a.jne(3)
        a.add_m32_r_disp8_imm8("esi", 0x20, 1)
        a.label(3); a.popad(); a.popfd()
        return fin(a)

    if stub_id == "power_cool":
        a = Asm(); a.pushfd()
        a.db(0xF3, 0x0F, 0x11, 0x46, 0x44)
        flag(a, "zoom"); a.je(1)
        a.popfd(); a.jmp_to(site_end)
        a.label(1); a.add_esp8(4); a.push8(0); a.popfd()
        a.jmp_to(site_end)
        return a.build(stub_va)

    if stub_id == "unit_lv":
        a = Asm(); a.pushfd(); flag(a, "revealmap"); a.jne(1)
        a.mov_m32_r_disp32_imm32("ebp", 0x260, 0x47C35000)
        a.popfd(); a.jmp_to(site_end)
        a.label(1); a.popfd()
        a.db(0xF3, 0x0F, 0x11, 0x85, 0x60, 0x02, 0x00, 0x00)
        return fin(a)

    if stub_id == "zoom_unit_xp":
        a = Asm()
        a.db(0x8B, 0x0C, 0xBA, 0x85, 0xC9)
        a.mov_m32_abs_r("ecx", block + DIAG["selEntry"])
        a.mov_m32_abs_r("edx", block + DIAG["selArr"])
        a.mov_m32_abs_r("edi", block + DIAG["selIdx"])
        a.cmp_m8_abs(block + FLAGS["capture_sel"], 1); a.jne(5)
        a.pushad()
        a.mov_r_abs("edx", block + CAPTURE_COUNT)
        a.cmp_r_imm32("edx", 64); a.jae(6)
        a.mov_m_scaled_idx("edx", block + CAPTURE_ARRAY, "ecx")
        a.inc_m32_abs(block + CAPTURE_COUNT)
        a.label(6); a.popad(); a.label(5)
        a.pushfd(); flag(a, "xp999"); a.jne(2)
        a.mov_m32_r_disp8_imm32("ecx", 0x1C, 0x3E7)
        a.label(2); a.popfd()
        return fin(a)

    if stub_id == "ammo":
        a = Asm()
        a.db(0x8B, 0x81, 0x78, 0x12, 0x00, 0x00)
        a.mov_m32_abs_r("eax", block + DIAG["weapon"])
        a.pushfd(); flag(a, "ammo"); a.jne(3)
        a.test_rr("eax", "eax"); a.je(3)
        a.mov_m32_r_disp8_imm32("eax", 0x08, 50000)
        a.label(3); a.popfd()
        return fin(a)

    raise NotImplementedError(stub_id)


STUB_ORDER = sorted([
    "money_h2", "money_h1", "money_h3", "money_h4",
    "proto_cool_a", "proto_cool_b", "power",
    "build_power", "build_hp_a", "build_hp_b", "sidebar_pts",
    "power_cool", "unit_lv", "zoom_unit_xp", "ammo",
])
