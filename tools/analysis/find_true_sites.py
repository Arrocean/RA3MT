# -*- coding: utf-8 -*-
"""Rebuild the TRUE hook-site mapping for the repacked ra3_1.12.game /
ra3_1.13.game on this disk.

The old TMK trainer's script addresses refer to EA's original 1.12 build;
this disk's 1.12 (2024 Ultimate Collection repack) has shifted code.  Each
hook's [DISABLE] section names the displaced original instruction bytes, so:
  1) search 1.12 .text for those exact bytes  -> TRUE 1.12 site
  2) build a masked AOB around the true site, search 1.13 -> TRUE 1.13 site
Also: disassemble the function containing the selection-iteration site to
find where the selection array pointer comes from.
"""
import json
import struct

import capstone
import pefile

P112 = r"D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data\ra3_1.12.game"
P113 = r"D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data\ra3_1.13.game"
IMG = 0x400000


def load(path):
    data = open(path, "rb").read()
    pe = pefile.PE(path, fast_load=True)
    secs = []
    for s in pe.sections:
        name = s.Name.decode(errors="replace").strip("\x00")
        raw = data[s.PointerToRawData:s.PointerToRawData + max(s.Misc_VirtualSize, s.SizeOfRawData)]
        secs.append((name, s.VirtualAddress, raw))
    return secs


S12 = load(P112)
S13 = load(P113)


def locate(secs, rva):
    for name, va, buf in secs:
        if va <= rva < va + len(buf):
            return name, buf, rva - va
    return None, None, None


def scan(secs, pat, mask):
    import re
    rx = b"".join(__import__("re").escape(pat[i:i+1]) if mask[i] else b"." for i in range(len(pat)))
    hits = []
    for name, va, buf in secs:
        for m in __import__("re").finditer(rx, buf, __import__("re").DOTALL):
            hits.append(va + m.start())
    return hits


def base_mask(buf, off, length):
    length = min(length, len(buf) - off)
    pat = bytearray(buf[off:off+length])
    mask = bytearray(b"\x01" * length)
    i = 0
    while i < length - 5:
        b = buf[off+i]
        if b in (0xE8, 0xE9):
            for k in range(i+1, min(i+5, length)):
                mask[k] = 0
            i += 5
            continue
        if b == 0x0F and 0x80 <= buf[off+i+1] <= 0x8F:
            for k in range(i+2, min(i+6, length)):
                mask[k] = 0
            i += 6
            continue
        i += 1
    for j in range(length-4):
        if all(mask[j:j+4]):
            v = struct.unpack_from("<I", pat, j)[0]
            if IMG <= v < 0x980000:
                for k in range(j, j+4):
                    mask[k] = 0
    return pat, mask


def pat_str(pat, mask):
    return " ".join("%02X" % p if m else "??" for p, m in zip(pat, mask))


# id: (expected displaced bytes, displaced length the detour overwrites, note)
# displaced_len == length of the call(+nop) the old trainer wrote == what OUR
# detour will overwrite + replay in the stub.
SITES = {
    "money_h2":     ("0378048B11", 5, "add edi,[eax+4]; mov edx,[ecx]"),
    "money_h1":     ("8B40048B8EB0030000", 9, "mov eax,[eax+4]; mov ecx,[esi+3B0]"),
    "money_h3":     ("8B78348B4E3C", 6, "mov edi,[eax+34]; mov ecx,[esi+3C]"),
    "money_h4":     ("F30F104 72C".replace(" ", ""), 5, "movss xmm0,[edi+2C]"),
    "proto_cool_b": ("F30F2C461C", 5, "cvttss2si eax,[esi+1C]"),
    "proto_cool_a": ("D9461C89465C", 6, "fld [esi+1C]; mov [esi+5C],eax"),
    "power":        ("D986BC010000", 6, "fld [esi+1BC]"),
    "build_power":  ("8B9818040000", 6, "mov ebx,[eax+418]"),
    "build_hp_a":   ("8B70508B01", 5, "mov esi,[eax+50]; mov eax,[ecx]"),
    "build_hp_b":   ("8B51503B500C", 6, "mov edx,[ecx+50]; cmp edx,[eax+0C]"),
    "sidebar_pts":  ("8B48503B4E20", 6, "mov ecx,[eax+50]; cmp ecx,[esi+20]"),
    "unit_lv":      ("F30F118560020000", 8, "movss [ebp+260],xmm0"),
    "zoom_unit_xp": ("8B0CBA85C9", 5, "mov ecx,[edx+edi*4]; test ecx,ecx"),
    "ammo":         ("8B8178120000", 6, "mov eax,[ecx+1278]"),
    "fast_build":   ("8B40082B4114", 6, "mov eax,[eax+8]; sub eax,[ecx+14]"),
    "power_cool":   ("F30F114644", 5, "movss [esi+44],xmm0"),
}

out = {}
print("== step 1: locate true 1.12 sites by displaced-byte search ==")
true112 = {}
for hid, (hexbytes, dlen, asm) in SITES.items():
    needle = bytes.fromhex(hexbytes)
    hits = []
    for name, va, buf in S12:
        start = 0
        while True:
            i = buf.find(needle, start)
            if i < 0:
                break
            hits.append(va + i)
            start = i + 1
    true112[hid] = hits
    tag = "OK " if len(hits) == 1 else ("MULTI" if len(hits) > 1 else "NONE")
    hs = ",".join(hex(h) for h in hits[:5])
    print(f"  {tag:<5} {hid:<14} {len(hits)} hit(s): {hs}   ; {asm}")
    out[hid] = {"asm112": asm, "displaced": hexbytes, "displacedLen": dlen,
                "candidates112": [hex(h) for h in hits]}

print("\n== step 2: match each true site into 1.13 ==")
final = {}
for hid, hits in true112.items():
    if len(hits) != 1:
        continue
    site = hits[0]
    _, b12, o12 = locate(S12, site)
    best = None
    for pre in (12, 16, 20, 24, 32, 40, 48, 64):
        if o12 < pre:
            continue
        for ln in (48, 64, 80, 96, 112, 128, 160, 192):
            pat, mask = base_mask(b12, o12 - pre, ln)
            if sum(mask) < 20:
                continue
            h12 = scan(S12, pat, mask)
            h13 = scan(S13, pat, mask)
            if len(h12) == 1 and h12[0] + pre == site and len(h13) == 1:
                score = sum(mask) * 1000 - ln
                if best is None or score > best[0]:
                    best = (score, pat, mask, pre, ln, h13[0] + pre)
        if best:
            break
    if best:
        _, pat, mask, pre, ln, site13 = best
        final[hid] = {
            "asm112": out[hid]["asm112"], "displaced": out[hid]["displaced"],
            "displacedLen": out[hid]["displacedLen"],
            "rva112": hex(site), "rva113": hex(site13),
            "pattern": pat_str(pat, mask), "siteOffset": pre, "patternLen": ln,
        }
        print(f"  OK  {hid:<14} 1.12=0x{site:X}  1.13=0x{site13:X}  pre={pre} len={ln}")
    else:
        print(f"  FAIL {hid:<14} 1.12=0x{site:X} no unique 1.13 match")

# threat function (call target, not patched): use prologue sig from 1.12
print("\n== threat/kill function (call target) ==")
tf = None
for pre, ln in ((0, 64), (0, 96), (0, 48)):
    _, b12, o12 = locate(S12, 0x39ECB0)
    pat, mask = base_mask(b12, o12, ln)
    h12 = scan(S12, pat, mask)
    h13 = scan(S13, pat, mask)
    if len(h12) == 1 and len(h13) == 1 and h12[0] == 0x39ECB0:
        tf = (h13[0], pat_str(pat, mask))
        print(f"  threat fn: 1.12=0x39ECB0 1.13={hex(h13[0])}")
        break
if not tf:
    print("  threat fn: no unique match from 0x39ECB0")

# selection array source: function containing zoom site (true 1.12 site)
print("\n== selection array source (function of zoom site) ==")
import capstone
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
zsite = true112["zoom_unit_xp"][0] if true112["zoom_unit_xp"] else 0x169D85
_, b12, o12 = locate(S12, zsite)
i = o12
while i > 0:
    if b12[i] == 0xCC and b12[i-1] != 0xCC:
        fstart = i + 1
        break
    i -= 1
else:
    fstart = 0
func_rva = zsite - (o12 - fstart)
print(f"  zoom site 0x{zsite:X}, function start ~0x{func_rva:X}")
ins = list(md.disasm(b12[fstart:o12 + 16], func_rva))
idx = next((k for k, x in enumerate(ins) if x.address == zsite), None)
ctx = ins[max(0, idx - 40):idx + 3] if idx else ins[-40:]
for x in ctx:
    mark = "   <<< SITE" if x.address == zsite else ""
    print(f"    {x.address:08X}  {x.mnemonic} {x.op_str}{mark}")

json.dump({"hooks": final, "threatFn": tf and {"rva112": "0x39ECB0", "rva113": hex(tf[0]), "pattern": tf[1]},
           "zoomFnStart112": hex(func_rva)},
          open(r"D:\RiderProject\RA3MT\assets\hookdata.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("\nsaved assets/hookdata.json")
