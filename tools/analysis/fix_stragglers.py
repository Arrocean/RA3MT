# -*- coding: utf-8 -*-
"""Resolve the remaining ambiguous hook sites.

Strategies:
  A) extended-context: displaced bytes + the instructions that follow at the
     site (known from the old stub's replay sequence) -> unique search.
  B) sibling-distance: same-function sites keep their relative offsets between
     EA-1.12 and this repack (verified on the money chain); predict, verify.
  C) similarity-pairing: for sites whose displaced bytes occur multiple times
     in both versions, score every (cand12, cand13) pair by how many bytes
     match in a +/- window; the true pair is near-identical.
Then build runtime cross-version AOB signatures for every resolved site
(falling back to displaced-byte search + sibling anchor where no unique sig
exists).
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
B12 = {n: (v, b) for n, v, b in S12}


def locate(secs, rva):
    for name, va, buf in secs:
        if va <= rva < va + len(buf):
            return name, buf, rva - va
    return None, None, None


def read_rva(secs, rva, n):
    _, buf, off = locate(secs, rva)
    return bytes(buf[off:off+n]) if buf else None


def find_all(secs, needle, only=".text"):
    hits = []
    for name, va, buf in secs:
        if only and name != only:
            continue
        start = 0
        while True:
            i = buf.find(needle, start)
            if i < 0:
                break
            hits.append(va + i)
            start = i + 1
    return hits


def sim_score(secs_a, a, secs_b, b, w=48):
    ba = read_rva(secs_a, a - w, 2 * w)
    bb = read_rva(secs_b, b - w, 2 * w)
    if ba is None or bb is None or len(ba) != len(bb):
        return -1
    return sum(1 for x, y in zip(ba, bb) if x == y) / len(ba)


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


def find_all_masked(secs, pat, mask):
    import re
    rx = b"".join(re.escape(pat[i:i+1]) if mask[i] else b"." for i in range(len(pat)))
    hits = []
    for name, va, buf in secs:
        for m in re.finditer(rx, buf, re.DOTALL):
            hits.append(va + m.start())
    return hits


def cross_sig(secs_a, site_a, secs_b, site_b, pres=(12, 16, 24, 32, 48, 64), lens=(48, 64, 80, 96, 112, 128, 160)):
    """Unique masked sig around site_a hitting exactly site_b in version B."""
    _, ba, oa = locate(secs_a, site_a)
    for pre in pres:
        if oa < pre:
            continue
        for ln in lens:
            pat, mask = base_mask(ba, oa - pre, ln)
            if sum(mask) < 20:
                continue
            ha = find_all_masked(secs_a, pat, mask)
            hb = find_all_masked(secs_b, pat, mask)
            if len(ha) == 1 and ha[0] + pre == site_a and len(hb) == 1 and hb[0] + pre == site_b:
                return pat_str(pat, mask), pre, ln
    return None


hookdata = json.load(open(r"D:\RiderProject\RA3MT\assets\hookdata.json", encoding="utf-8"))
hooks = hookdata["hooks"]

# backfill sites that were unique in 1.12 but unmatched into 1.13 in the
# previous pass (find_true_sites.py step 2 FAIL)
KNOWN112 = {
    "money_h3": ("0x664F0C", "8B78348B4E3C", 6),
    "build_hp_a": ("0x47CB89", "8B70508B01", 5),
    "sidebar_pts": ("0x348A06", "8B48503B4E20", 6),
    "unit_lv": ("0x4005BC", "F30F118560020000", 8),
    "fast_build": ("0x312EB3", "8B40082B4114", 6),
}
for hid, (rva, disp, dl) in KNOWN112.items():
    hooks.setdefault(hid, {})
    hooks[hid].setdefault("rva112", rva)
    hooks[hid].update(displaced=disp, displacedLen=dl)
hooks.setdefault("power_cool", {}).setdefault("rva112", None)
hooks["power_cool"].update(displaced="F30F114644", displacedLen=5)

print("== A) power_cool: context-filtered candidate scan ==")
cands = find_all(S12, bytes.fromhex("F30F114644"))
resolved12 = []
for c in cands:
    tail = read_rva(S12, c + 5, 16)
    if tail and (b"\xd9\x66\x44" in tail or b"\xd9\x5e\x44" in tail):
        resolved12.append(c)
print(f"  1.12 candidates with fsub/fstp nearby: {[hex(x) for x in resolved12]}")
cands13 = find_all(S13, bytes.fromhex("F30F114644"))
resolved13 = []
for c in cands13:
    tail = read_rva(S13, c + 5, 16)
    if tail and (b"\xd9\x66\x44" in tail or b"\xd9\x5e\x44" in tail):
        resolved13.append(c)
print(f"  1.13 candidates: {[hex(x) for x in resolved13]}")
if len(resolved12) == 1 and len(resolved13) == 1:
    hooks["power_cool"]["rva112"] = hex(resolved12[0])
    hooks["power_cool"]["rva113"] = hex(resolved13[0])
    print(f"  power_cool resolved: 1.12=0x{resolved12[0]:X} 1.13=0x{resolved13[0]:X}")

print("== B) sibling-distance prediction ==")
SIB = {  # hid: (anchor hid, delta112 = EA_site - EA_anchor, expected bytes at 1.13 pred)
    "money_h3":   ("money_h2", 0x6CFE6C - 0x6CFDFE, "8B78348B4E3C"),
    "build_hp_a": ("build_hp_b", 0x43EC19 - 0x43ECA6, "8B70508B01"),
    "sidebar_pts": ("proto_cool_a", 0x30A5F6 - 0x30F38C, "8B48503B4E20"),
}
for hid, (anchor, delta, exp) in SIB.items():
    if anchor not in hooks:
        print(f"  {hid}: anchor {anchor} missing, skip")
        continue
    a13 = int(hooks[anchor]["rva113"], 16)
    pred13 = a13 + delta
    got = read_rva(S13, pred13, len(bytes.fromhex(exp)))
    ok = got == bytes.fromhex(exp)
    print(f"  {hid}: pred 1.13=0x{pred13:X} bytes={got and got.hex(' ').upper()} {'OK' if ok else 'MISMATCH'}")
    if ok:
        # verify the 1.12 candidate is the recorded one
        if hid in hooks and "rva112" in hooks[hid]:
            pass
        hooks[hid]["rva113"] = hex(pred13)

print("== B2) free byte search in 1.13 for remaining uniques ==")
for hid in ("unit_lv", "fast_build"):
    exp = hooks[hid]["displaced"]
    nb13 = find_all(S13, bytes.fromhex(exp))
    print(f"  {hid}: 1.13 hits={[hex(x) for x in nb13]}")
    if len(nb13) == 1:
        hooks[hid]["rva113"] = hex(nb13[0])

print("== C) similarity-pairing ==")
PAIRS = {
    "money_h4":   "F30F104 72C".replace(" ", ""),
    "power":      "D986BC010000",
    "build_power": "8B9818040000",
    "ammo":       "8B8178120000",
}
for hid, exp in PAIRS.items():
    c12 = find_all(S12, bytes.fromhex(exp))
    c13 = find_all(S13, bytes.fromhex(exp))
    best = None
    for a in c12:
        for b in c13:
            s = sim_score(S12, a, S13, b, 64)
            if best is None or s > best[0]:
                best = (s, a, b)
    s, a, b = best
    print(f"  {hid}: best pair 1.12=0x{a:X} 1.13=0x{b:X} similarity={s:.2%} "
          f"(cand12={len(c12)}, cand13={len(c13)})")
    if s > 0.85:
        hooks[hid] = {"rva112": hex(a), "rva113": hex(b),
                      "displaced": exp, "displacedLen": len(bytes.fromhex(exp))}

# ------------------------------------------------- runtime sigs for everything
print("\n== runtime cross-version signatures ==")
for hid, h in sorted(hooks.items()):
    if hid == "threatFn":
        continue
    if "rva112" not in h or "rva113" not in h:
        print(f"  {hid}: STILL UNRESOLVED")
        continue
    a, b = int(h["rva112"], 16), int(h["rva113"], 16)
    got = read_rva(S12, a, h["displacedLen"])
    if got != bytes.fromhex(h["displaced"]):
        print(f"  {hid}: !! 1.12 displaced-byte verify FAILED at 0x{a:X}")
        continue
    sig = cross_sig(S12, a, S13, b)
    if sig:
        h["pattern"], h["siteOffset"], h["patternLen"] = sig
        print(f"  {hid:<14} 0x{a:X} -> 0x{b:X}  sig ok (pre={sig[1]}, len={sig[2]})")
    else:
        h.pop("pattern", None)
        print(f"  {hid:<14} 0x{a:X} -> 0x{b:X}  no unique sig (will use displaced-byte fallback)")

json.dump(hookdata, open(r"D:\RiderProject\RA3MT\assets\hookdata.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("\nsaved assets/hookdata.json")
