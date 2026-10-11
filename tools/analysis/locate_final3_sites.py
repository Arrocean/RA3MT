# -*- coding: utf-8 -*-
"""在重打包 1.12/1.13 二进制中定位 FINAL3 剩余未移植站点的真实 RVA。

方法：用 FINAL3 [DISABLE] 段记录的 EA 原始被替换字节做全 .text 搜索，
配合 NOTES 区域偏移表预测窗口消歧，输出候选及其上下文反汇编供人工裁决。
只读文件，不触碰游戏进程。用法: python locate_final3_sites.py
"""
from pathlib import Path
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

DATA = Path(r'D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data')
md = Cs(CS_ARCH_X86, CS_MODE_32)

# EA 1.12 锚点 → 重打包预测窗口（RVA，宽松 ±0x3000；来自 docs/NOTES.md 区域偏移表）
SITES = [
    # (名称, EA RVA, displaced 十六进制, 1.12 预测中心, 1.13 预测中心)
    ("oremine",      0x2D4933, "8B40082B4114",        0x2D4933 + 0x3E4C0, 0x2D4933 + 0x29220),
    ("enemycantbuild", 0x30F530, "0350043BD7",        0x30F530 + 0x3E4C0, 0x30F530 + 0x29270),
    ("godmode",      0x12EEDF, "8B503C8BCE",          0x12EEDF + 0x40F00, 0x12EEDF + 0x29B00),
    ("onekill",      0x3651AE, "F30F114604",          None,               None),  # 区域未知，全域搜索
    ("onekilldata",  0x3FE714, "8B8E3C030000",        0x3FE714 + 0x3DF70, 0x3FE714 + 0x29340),
    ("onekilldata2", 0x2E24E3, "8B893C030000",        0x2E24E3 + 0x3E4C0, 0x2E24E3 + 0x29270),
]
WINDOW = 0x3000


def load_text(path):
    image = pefile.PE(data=path.read_bytes())
    mapped = image.get_memory_mapped_image()
    for s in image.sections:
        if s.Name.rstrip(b'\0') == b'.text':
            start = s.VirtualAddress
            return mapped, start, start + s.Misc_VirtualSize
    raise RuntimeError('.text not found')


def search(mapped, lo, hi, pattern):
    out, i = [], 0
    region = mapped[lo:hi]
    while True:
        i = region.find(pattern, i)
        if i < 0:
            return out
        out.append(lo + i)
        i += 1


def ctx(mapped, rva, before=0x16, after=0x20):
    s = max(0, rva - before)
    chunk = bytes(mapped[s:rva + after])
    lines = []
    for ins in md.disasm(chunk, s):
        mark = ' <<<' if ins.address == rva else ''
        lines.append(f"    {ins.address:08X}: {ins.mnemonic} {ins.op_str}{mark}")
    return '\n'.join(lines)


for name, ea_rva, hexpat, p112, p113 in SITES:
    pat = bytes.fromhex(hexpat)
    print(f"\n{'='*72}\n{name}  EA=0x{ea_rva:X}  displaced={hexpat.upper()}")
    for ver, pred in (("1.12", p112), ("1.13", p113)):
        mapped, lo, hi = load_text(DATA / f'ra3_{ver}.game')
        hits = search(mapped, lo, hi, pat)
        inwin = [h for h in hits if pred is None or abs(h - pred) <= WINDOW]
        label = "全域" if pred is None else f"预测 0x{pred:X}±{WINDOW:#x}"
        print(f"  [{ver}] 全 .text 命中 {len(hits)} 处；{label} 内 {len(inwin)} 处")
        for h in (inwin if inwin else hits[:4]):
            tag = "窗口内" if h in inwin else "窗口外候选"
            print(f"  [{ver}] 候选 RVA 0x{h:X} ({tag})  (EA→重打包 Δ={h - ea_rva:+#x})")
            print(ctx(mapped, h))
