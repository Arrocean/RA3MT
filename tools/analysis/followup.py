# -*- coding: utf-8 -*-
"""Follow-up analysis:
A) disassemble the function containing hook 0x128735 (1.12) to find where the
   selection array (edx) is loaded from -> the real game global for the
   current selection.
B) dump PE section layout of both versions.
C) scan 1.12 .text for any code-referenced dword in the neighbourhood of the
   two .data globals (the exact dword may not appear; nearby struct base
   accesses do).
"""
import struct
import capstone
import pefile

P112 = r"D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data\ra3_1.12.game"
IMG_BASE = 0x400000
HOOK = 0x128735

data = open(P112, "rb").read()
pe = pefile.PE(P112, fast_load=True)

print("== sections (1.12 / 1.13) ==")
for path in (P112, P112.replace("1.12", "1.13")):
    p2 = pefile.PE(path, fast_load=True)
    print(" ", path.split("\\")[-1])
    for s in p2.sections:
        name = s.Name.decode(errors="replace").strip("\x00")
        print(f"    {name:<8} va=0x{s.VirtualAddress:06X} vsize=0x{s.Misc_VirtualSize:06X} raw=0x{s.SizeOfRawData:06X}")

secs = []
for s in pe.sections:
    name = s.Name.decode(errors="replace").strip("\x00")
    raw = data[s.PointerToRawData:s.PointerToRawData + max(s.Misc_VirtualSize, s.SizeOfRawData)]
    secs.append((name, s.VirtualAddress, raw))


def locate(rva):
    for name, va, buf in secs:
        if va <= rva < va + len(buf):
            return buf, rva - va


buf, site = locate(HOOK)

# find function start: walk back to the end of an int3 padding run
i = site
while i > 0:
    if buf[i] == 0xCC and buf[i - 1] != 0xCC:
        fstart = i + 1
        break
    i -= 1
else:
    fstart = 0
func_rva = HOOK - (site - fstart)
print(f"\n== function containing 0x{HOOK:X}: starts ~0x{func_rva:X} ==")

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
ins_list = list(md.disasm(buf[fstart:site + 24], func_rva))
idx = next(k for k, ins in enumerate(ins_list) if ins.address == HOOK)
print(f"   {len(ins_list)} instructions decoded up to hook site (idx {idx})")
print("   -- 34 instructions before hook:")
for ins in ins_list[max(0, idx - 34):idx + 4]:
    mark = " <<< HOOK" if ins.address == HOOK else ""
    print(f"   {ins.address:08X}  {ins.bytes.hex():<20} {ins.mnemonic} {ins.op_str}{mark}")

print("\n== dword refs near .data globals in 1.12 .text ==")
# search any dword in text within +/-0x100 of the globals
targets = {"player_mgr": 0x8E8C9C, "money_ptr": 0x8DB73C}
text_buf, text_off = locate(0x401000)
text_va = 0x401000
for gname, grva in targets.items():
    lo = IMG_BASE + grva - 0x100
    hi = IMG_BASE + grva + 0x100
    found = {}
    start = 0
    while True:
        j = text_buf.find(b"", start)  # placeholder
        break
    # brute scan
    n = len(text_buf) - 4
    hits = []
    for j in range(n):
        v = struct.unpack_from("<I", text_buf, j)[0]
        if lo <= v < hi:
            hits.append((text_va + j, v))
    print(f"  {gname} (rva 0x{grva:X}): {len(hits)} nearby dword refs in .text")
    for h in hits[:12]:
        print(f"    at 0x{h[0]:X} -> [0x{h[1] - IMG_BASE:X}]")
