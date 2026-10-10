# -*- coding: utf-8 -*-
"""Final resolution of remaining sites via multi-anchor delta interpolation.

Resolved sites give us (EA_rva -> repack_rva) delta samples; delta varies
smoothly within code regions.  For each ambiguous site, predict its repack
address by interpolating delta from the two nearest resolved anchors, then
pick the candidate nearest the prediction (requiring high byte-similarity
with its 1.13 counterpart).
"""
import json
import struct
import capstone
import pefile

P112 = r"D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data\ra3_1.12.game"
P113 = r"D:\Steam\steamapps\common\Command and Conquer Red Alert 3\Data\ra3_1.13.game"
IMG = 0x400000

EA_RVA = {  # old trainer's EA-1.12 addresses
    "zoom_unit_xp": 0x128735, "power_cool": 0x1EC7CD, "fast_build": 0x2D4933,
    "build_power": 0x2EBB69, "power": 0x2F6CFF, "sidebar_pts": 0x30A5F6,
    "proto_cool_a": 0x30F38C, "proto_cool_b": 0x30F42E, "threatFn": 0x39ECB0,
    "unit_lv": 0x3C226C, "ammo": 0x438ED0, "build_hp_a": 0x43EC19,
    "build_hp_b": 0x43ECA6, "money_h1": 0x6CFD0D, "money_h2": 0x6CFDFE,
    "money_h3": 0x6CFE6C, "money_h4": 0x6CFEB5,
}


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


def read_rva(secs, rva, n):
    _, buf, off = locate(secs, rva)
    return bytes(buf[off:off+n]) if buf else None


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


def sim(secs_a, a, secs_b, b, w=48):
    ba = read_rva(secs_a, a - w, 2 * w)
    bb = read_rva(secs_b, b - w, 2 * w)
    if not ba or not bb or len(ba) != len(bb):
        return -1
    return sum(1 for x, y in zip(ba, bb) if x == y) / len(ba)


hookdata = json.load(open(r"D:\RiderProject\RA3MT\assets\hookdata.json", encoding="utf-8"))
hooks = hookdata["hooks"]

# anchors: sites with confirmed (112, 113) and their EA addresses
anchors = []
for hid, h in hooks.items():
    if hid in EA_RVA and "rva112" in h and "rva113" in h:
        anchors.append((EA_RVA[hid], int(h["rva112"], 16), int(h["rva113"], 16), hid))
anchors.sort()
print("anchors:")
for ea, d12, d13, hid in anchors:
    print(f"  {hid:<14} EA=0x{ea:X} d112=+0x{d12-ea:X} d113=+0x{d13-ea:X}")


def predict(ea):
    """interpolate repack address from nearest EA anchors"""
    below = [a for a in anchors if a[0] <= ea]
    above = [a for a in anchors if a[0] > ea]
    if below and above:
        (ea0, r0, _, _), (ea1, r1, _, _) = below[-1], above[0]
        t = (ea - ea0) / (ea1 - ea0)
        p12 = r0 + t * (r1 - r0)
        p13 = r0 + t * (r1 - r0)
        # 1.13 via same interpolation but using 1.13 coords
        (_, _, q0, _), (_, _, q1, _) = below[-1], above[0]
        p13 = q0 + t * (q1 - q0)
        return p12, p13
    a = (below or above)[-1]
    return a[1] + (ea - a[0]), a[2] + (ea - a[0])


def resolve(hid, needle_hex, min_sim=0.85):
    needle = bytes.fromhex(needle_hex)
    c12 = find_all(S12, needle)
    c13 = find_all(S13, needle)
    if not c12 or not c13:
        print(f"  {hid}: no candidates")
        return
    p12, p13 = predict(EA_RVA[hid])
    best = None
    for a in c12:
        for b in c13:
            s = sim(S12, a, S13, b, 64)
            dist = abs(a - p12) + abs(b - p13)
            score = s * 1e9 - dist
            if best is None or score > best[0]:
                best = (score, s, a, b, dist)
    _, s, a, b, dist = best
    ok = s >= min_sim
    print(f"  {hid:<12} pred12=0x{int(p12):X} pred13=0x{int(p13):X} -> "
          f"1.12=0x{a:X}(+0x{a-int(p12):X}) 1.13=0x{b:X}(+0x{b-int(p13):X}) sim={s:.2%} {'OK' if ok else 'REJECT'}")
    if ok:
        hooks[hid]["rva112"] = hex(a)
        hooks[hid]["rva113"] = hex(b)


print("\n== resolve ==")
resolve("money_h4", "F30F104 72C".replace(" ", ""))
resolve("power", "D986BC010000")
resolve("build_power", "8B9818040000")
resolve("ammo", "8B8178120000")
resolve("sidebar_pts", "8B48503B4E20")

print("\n== power_cool: delta-window + disasm context ==")
lo, hi = 0x1EC7CD + 0x3C000, 0x1EC7CD + 0x43000
cands = [c for c in find_all(S12, bytes.fromhex("F30F114644")) if lo <= c <= hi]
print(f"  candidates in window: {[hex(c) for c in cands]}")
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
for c in cands:
    ctx = read_rva(S12, c, 40)
    ins = list(md.disasm(ctx, c))
    txt = " | ".join(f"{x.mnemonic} {x.op_str}" for x in ins[:8])
    print(f"    0x{c:X}: {txt}")

print("\n== threatFn sanity disasm (0x39ECB0 repack 1.12) ==")
ctx = read_rva(S12, 0x39ECB0, 80)
for x in list(md.disasm(ctx, 0x39ECB0))[:16]:
    print(f"    {x.address:08X}  {x.mnemonic} {x.op_str}")

json.dump(hookdata, open(r"D:\RiderProject\RA3MT\assets\hookdata.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("saved")
