# -*- coding: utf-8 -*-
"""Byte-level verification of all 17 hook sites in 1.12, plus a search for the
real selection-iteration site (mov ecx,[edx+edi*4]; test ecx,ecx)."""
import struct

P112 = r"D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data\ra3_1.12.game"
IMG = 0x400000

data = open(P112, "rb").read()
import pefile
pe = pefile.PE(P112, fast_load=True)
secs = []
for s in pe.sections:
    name = s.Name.decode(errors="replace").strip("\x00")
    raw = data[s.PointerToRawData:s.PointerToRawData + max(s.Misc_VirtualSize, s.SizeOfRawData)]
    secs.append((name, s.VirtualAddress, raw))


def read_rva(rva, n):
    for name, va, buf in secs:
        if va <= rva < va + len(buf):
            return buf[rva - va:rva - va + n]
    return None


SITES = {
    "money_h2":   (0x6CFDFE, "03 78 04 8B 11"),
    "money_h1":   (0x6CFD0D, "8B 40 04 8B 8E B0 03 00 00"),
    "money_h3":   (0x6CFE6C, "8B 78 34 8B 4E 3C"),
    "money_h4":   (0x6CFEB5, "F3 0F 10 47 2C"),
    "proto_cool_b": (0x30F42E, "F3 0F 2C 46 1C"),
    "proto_cool_a": (0x30F38C, "D9 46 1C 89 46 5C"),
    "power":      (0x2F6CFF, "D9 86 BC 01 00 00"),
    "build_power": (0x2EBB69, "8B 98 18 04 00 00"),
    "build_hp_a": (0x43EC19, "8B 70 50 8B 01"),
    "build_hp_b": (0x43ECA6, "8B 51 50 3B 50 0C"),
    "sidebar_pts": (0x30A5F6, "8B 48 50 3B 4E 20"),
    "unit_lv":    (0x3C226C, "F3 0F 11 85 60 02 00 00"),
    "zoom_unit_xp": (0x128735, "8B 0C BA 85 C9"),
    "ammo":       (0x438ED0, "8B 81 78 12 00 00"),
    "fast_build": (0x2D4933, "8B 40 08 2B 41 14"),
    "power_cool": (0x1EC7CD, "F3 0F 11 46 44"),
}

print("== verify original bytes at hook sites (1.12) ==")
bad = []
for hid, (rva, expect_hex) in SITES.items():
    expect = bytes.fromhex(expect_hex.replace(" ", ""))
    got = read_rva(rva, len(expect))
    ok = got == expect
    if not ok:
        bad.append(hid)
    print(f"  {'OK ' if ok else 'BAD'} {hid:<14} @0x{rva:X} got={got.hex(' ').upper()}")

# search for the real zoom/xp iteration bytes
print("\n== occurrences of '8B 0C BA 85 C9' in 1.12 .text ==")
name, va, tbuf = next((n, v, b) for n, v, b in secs if n == ".text")
needle = bytes.fromhex("8B0CBA85C9")
start = 0
while True:
    i = tbuf.find(needle, start)
    if i < 0:
        break
    print(f"  at RVA 0x{va + i:X}")
    start = i + 1

# also verify the threat function entry prologue
print("\nbytes at threat fn 0x39ECB0:", read_rva(0x39ECB0, 16).hex(" ").upper())
