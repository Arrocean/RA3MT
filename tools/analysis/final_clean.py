# -*- coding: utf-8 -*-
"""Clean final pass: purge similarity-pairing artifacts, re-resolve with a
sanitary anchor set, lock power_cool by context, and emit the definitive
hookdata.json."""
import json
import struct
import capstone
import pefile

P112 = r"D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data\ra3_1.12.game"
P113 = r"D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data\ra3_1.13.game"
IMG = 0x400000
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)


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


def read_rva(secs, rva, n):
    for name, va, buf in secs:
        if va <= rva < va + len(buf):
            return bytes(buf[rva - va:rva - va + n])
    return None


def find_all(secs, needle):
    hits = []
    for name, va, buf in secs:
        if name != ".text":
            continue
        start = 0
        while True:
            i = buf.find(needle, start)
            if i < 0:
                break
            hits.append(va + i)
            start = i + 1
    return hits


hookdata = json.load(open(r"D:\RiderProject\RA3MT\assets\hookdata.json", encoding="utf-8"))
hooks = hookdata["hooks"]

# purge artifacts of polluted similarity pairing
for hid in ("power", "money_h4"):
    hooks.pop(hid, None)

# rebuild hooks for the purged / still-missing ones
hooks.setdefault("power", {"displaced": "D986BC010000", "displacedLen": 6,
                           "asm112": "fld [esi+1BC]"})
hooks.setdefault("money_h4", {"displaced": "F30F104 72C".replace(" ", ""), "displacedLen": 5,
                              "asm112": "movss xmm0,[edi+2C]"})

print("== money_h4: money-block sibling prediction ==")
h3 = int(hooks["money_h3"]["rva113"], 16)
pred = h3 + (0x6CFEB5 - 0x6CFE6C)
exp = bytes.fromhex("F30F104 72C".replace(" ", ""))
for ver, secs in (("1.12", S12), ("1.13", S13)):
    a3 = int(hooks["money_h3"]["rva112" if ver == "1.12" else "rva113"], 16)
    p = a3 + (0x6CFEB5 - 0x6CFE6C)
    got = read_rva(secs, p, len(exp))
    print(f"  {ver}: 0x{p:X} = {got and got.hex(' ').upper()} {'OK' if got == exp else 'NO'}")
    if got == exp:
        hooks["money_h4"]["rva112" if ver == "1.12" else "rva113"] = hex(p)

print("== power: nearest clean-anchor candidate ==")
c12 = find_all(S12, bytes.fromhex("D986BC010000"))
c13 = find_all(S13, bytes.fromhex("D986BC010000"))
print(f"  1.12 cands: {[hex(x) for x in c12]}")
print(f"  1.13 cands: {[hex(x) for x in c13]}")
# prediction: EA 0x2F6CFF between build_power(0x2EBB69,+0x3E3B0/+0x291B0)
# and proto_a(0x30F38C,+0x3E3F0/+0x292A0)
p12 = 0x2F6CFF + 0x3E3D0
p13 = 0x2F6CFF + 0x29225
b12 = min(c12, key=lambda a: abs(a - p12))
b13 = min(c13, key=lambda a: abs(a - p13))
ba = read_rva(S12, b12 - 48, 96)
bb = read_rva(S13, b13 - 48, 96)
s = sum(1 for x, y in zip(ba, bb) if x == y) / 96
print(f"  chosen: 1.12=0x{b12:X} 1.13=0x{b13:X} sim={s:.2%}")
if s > 0.9:
    hooks["power"]["rva112"] = hex(b12)
    hooks["power"]["rva113"] = hex(b13)

print("== power_cool: context-locked ==")
print(f"  1.12 = 0x22B82D (movss [esi+44],xmm0 + je continuation, delta +0x3F060)")
hooks["power_cool"]["rva112"] = "0x22B82D"
# find 1.13: movss followed by jcc within +5, report all, nearest to family prediction
pred13 = 0x1EC7CD + 0x29200
found = []
for c in find_all(S13, bytes.fromhex("F30F114644")):
    tail = read_rva(S13, c + 5, 8)
    if tail and tail[0] in (0x74, 0x75):
        found.append(c)
print(f"  1.13 candidates (movss + jcc): {[hex(x) for x in found]}")
if found:
    b13 = min(found, key=lambda a: abs(a - pred13))
    ctx = read_rva(S13, b13, 24)
    print(f"  nearest to pred 0x{pred13:X}: 0x{b13:X} (delta +0x{b13-0x1EC7CD:X})")
    print("   ctx:", " | ".join(f"{x.mnemonic} {x.op_str}" for x in md.disasm(ctx, b13)))
    hooks["power_cool"]["rva113"] = hex(b13)

print("== sidebar_pts: accept similarity pair ==")
hooks["sidebar_pts"]["rva112"] = "0x348A06"
hooks["sidebar_pts"]["rva113"] = "0x333886"

print("== threatFn: region-consistency check ==")
# predicted from neighbours unit_lv(+0x3E350/+0x292A0) & build_hp(+0x3DF70/+0x293B0)
print(f"  EA 0x39ECB0 -> repack family pred 1.12≈{hex(0x39ECB0+0x3E160)} 1.13≈{hex(0x39ECB0+0x29300)}")
print(f"  current claim 1.12=0x39ECB0 1.13=0x39E3E0 (delta 0) -> OUT OF FAMILY, mark suspect")
hookdata["threatFn"] = {"rva112": "0x39ECB0", "rva113": "0x39E3E0",
                        "pattern": hookdata.get("threatFn", {}).get("pattern"),
                        "status": "suspect-region-delta-0; verify in game",
                        "note": "kill/destroy unit function; called with ecx=unit"}

print("\n== final table ==")
EA = {
    "zoom_unit_xp": 0x128735, "power_cool": 0x1EC7CD, "fast_build": 0x2D4933,
    "build_power": 0x2EBB69, "power": 0x2F6CFF, "sidebar_pts": 0x30A5F6,
    "proto_cool_a": 0x30F38C, "proto_cool_b": 0x30F42E, "unit_lv": 0x3C226C,
    "ammo": 0x438ED0, "build_hp_a": 0x43EC19, "build_hp_b": 0x43ECA6,
    "money_h1": 0x6CFD0D, "money_h2": 0x6CFDFE, "money_h3": 0x6CFE6C,
    "money_h4": 0x6CFEB5,
}
for hid, h in sorted(hooks.items()):
    r12, r13 = h.get("rva112"), h.get("rva113")
    if r12 and r13:
        extra = ""
        if hid in EA:
            extra = f" (d112 +0x{int(r12,16)-EA[hid]:X}, d113 +0x{int(r13,16)-EA[hid]:X})"
        print(f"  {hid:<14} 1.12={r12}  1.13={r13}{extra}")
    else:
        print(f"  {hid:<14} UNRESOLVED")

json.dump(hookdata, open(r"D:\RiderProject\RA3MT\assets\hookdata.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("saved")
